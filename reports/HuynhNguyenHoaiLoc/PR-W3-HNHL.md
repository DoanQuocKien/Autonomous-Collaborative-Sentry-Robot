# HNHL W3: InsightFace whitelist enrollment and verification

## Mục tiêu và thay đổi

Triển khai pipeline nhận diện khuôn mặt và xác thực danh sách trắng (whitelist) cho Giai đoạn 2 (giám sát cửa ra vào qua ESP32-CAM) theo đúng đặc tả `docs/Project Specification.md` §4.3 và `docs/Implementation Plan.md`:

- **Chuẩn hóa vector đặc trưng (`sentry/perception/face.py`):**
  - Hàm `normalize_embedding()` kiểm tra kích thước 512D, loại bỏ vector chứa `NaN`/`Inf` hoặc vector 0, chuẩn hóa về độ dài L2 bằng 1.0.
- **Xác thực danh sách trắng (`FaceVerifier`):**
  - So khớp vector truy vấn với **toàn bộ** các vector mẫu đã đăng ký của từng đối tượng (sử dụng độ đo cosine lớn nhất `max_similarity`, tuyệt đối không lấy trung bình vector theo đúng quy định của spec).
  - Ngưỡng xác thực đọc từ `config.toml` (`[thresholds].whitelist_cosine = 0.45`), có thể cấu hình linh hoạt.
  - Trả về `(person_id, score, authorized)`: chỉ gán danh tính khi `best_score >= threshold`, trường hợp không vượt ngưỡng sẽ từ chối (`authorized = False`).
- **Trích xuất đặc trưng với InsightFace (`InsightFaceEncoder`):**
  - Tích hợp bộ mô hình `buffalo_s` (SCRFD phát hiện khuôn mặt + MobileFaceNet trích xuất 512D).
  - Hỗ trợ cả `cuda` (`CUDAExecutionProvider`) và `cpu` (`CPUExecutionProvider`), có kiểm tra provider thực tế để tránh chạy fallback ngầm sang CPU khi chỉ định CUDA.
  - Kiểm tra đầu vào ảnh BGR định dạng uint8 `(H, W, 3)`.
- **Lưu trữ an toàn (`load_whitelist`):**
  - Đọc file `.npz` với cờ `allow_pickle=False` để bảo mật, kiểm tra cấu trúc dữ liệu bắt buộc phải có mảng `embeddings` kích thước `(N, 512)` với `3 <= N <= 5`.
- **Công cụ dòng lệnh (`tools/enroll_whitelist.py`, `tools/verify_whitelist.py`):**
  - `tools/enroll_whitelist.py`: Đăng ký 3–5 ảnh chân dung ẩn danh (`^[A-Za-z0-9_-]+$`), trích xuất và nén thành file `<person_id>.npz`.
  - `tools/verify_whitelist.py`: Kiểm tra nhanh một ảnh đối soát với thư mục whitelist đã đăng ký.
- **Xuất interface (`sentry/perception/__init__.py`):**
  - Bổ sung `FaceVerifier`, `InsightFaceEncoder`, `load_whitelist`, `normalize_embedding` vào package exports.

## Kiểm chứng — 2026-10-25

Kiểm thử tự động trên môi trường `.venv` (Python 3.12.15, pytest-9.1.1):

```powershell
.venv\Scripts\python.exe -m pytest tests/test_face.py tests/test_enroll_whitelist.py -v --basetemp=data/pytest-w3 -p no:cacheprovider
```

- **10/10 tests passed (4,67 s)**:
  - `test_normalize_embedding`: Chuẩn hóa vector 512D đạt L2 norm = 1.0.
  - `test_known_face`: Nhận diện chính xác người trong whitelist với điểm số khớp tối đa.
  - `test_unknown_face`: Từ chối người lạ dưới ngưỡng cấu hình.
  - `test_invalid_embedding`: Bắt lỗi vector 0 và vector sai kích thước.
  - `test_extract_face_with_fake_backend`: Kiểm tra contract trích xuất và confidence score.
  - `test_extract_rejects_invalid_image`: Từ chối ảnh sai định dạng/kích thước.
  - `test_enroll_keeps_all_embeddings`: Đảm bảo lưu độc lập toàn bộ các vector mẫu (không lấy trung bình).
  - `test_rejects_insufficient_photos`: Bắt buộc cung cấp từ 3 đến 5 ảnh mẫu.
  - `test_saved_enrollment_can_be_verified`: Kiểm thử luồng round-trip: Đăng ký $\rightarrow$ Lưu file $\rightarrow$ Đọc whitelist $\rightarrow$ Xác thực thành công.
  - `test_rejects_invalid_whitelist_shape`: Bắt lỗi file whitelist không hợp lệ hoặc sai cấu trúc.
- **Regression test perception:** 53 passed trong `test_obstacle.py`, `test_gridmap.py`, `test_vantage.py`.

Bằng chứng kiểm thử lưu tại: [pytest.log](week-03/pytest.log), [Báo cáo tuần 3](week-03.md).

## Giới hạn và nghiệm thu tiếp theo

- **T1 ROC trên tập D2:** Chờ buổi họp thực nghiệm Chủ Nhật (2026-10-25) để thu thập bộ dữ liệu D2 (ESP32 doorway entries của 3 thành viên theo cơ chế leave-one-out) nhằm tính đường cong ROC thực tế và nghiệm thu tiêu chí $\text{TAR} \ge 95\%$ tại $\text{FAR} \le 1\%$.
- **Vật cản sát sàn (D5):** Đã nhận lô 1 từ DQK (397 ảnh, PR #59); tiếp tục phối hợp gán nhãn và tinh chỉnh YOLOv8n.
- **Edge Conversion Parity:** Phối hợp cùng DQK kiểm thử độ tương đồng giữa ONNX Runtime và TensorRT FP16 trên Jetson Nano.

Branch: `HuynhNguyenHoaiLoc/w03-perception`  
Base: `origin/main`  
Reviewer: **DoanQuocKien** (DQK)
