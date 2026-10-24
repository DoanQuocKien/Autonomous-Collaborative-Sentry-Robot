# HNHL W3: InsightFace whitelist, D5 floor obstacles, wire fallback, and edge parity

## Mục tiêu và thay đổi

Hoàn thành toàn diện các nhiệm vụ Tuần 3 được phân công cho **HuynhNguyenHoaiLoc (HNHL)** theo đúng `docs/Project Specification.md` §4.3 và `docs/Implementation Plan.md`:

### 1. Nhận diện khuôn mặt & xác thực danh sách trắng (`sentry/perception/face.py`)
- **Chuẩn hóa vector đặc trưng:** `normalize_embedding()` kiểm tra vector 512D, loại bỏ `NaN`/`Inf`/vector 0, chuẩn hóa độ dài L2 = 1.0.
- **Xác thực danh sách trắng (`FaceVerifier`):** So khớp vector truy vấn với **toàn bộ** các vector mẫu của từng danh tính bằng độ đo cosine lớn nhất `max_similarity` (không lấy trung bình vector theo đúng spec §4.3). Ngưỡng đọc từ `config.toml` (`whitelist_cosine = 0.45`).
- **Trích xuất đặc trưng với InsightFace (`InsightFaceEncoder`):** Tích hợp gói mô hình `buffalo_s` (SCRFD phát hiện khuôn mặt + MobileFaceNet 512D), hỗ trợ cả CUDA (`CUDAExecutionProvider`) và CPU.
- **Lưu trữ an toàn (`load_whitelist`):** Đọc file nén `.npz` với `allow_pickle=False`, kiểm tra bắt buộc 3–5 embeddings mỗi người và đúng kích thước 512D.
- **CLI Tooling:**
  - `tools/enroll_whitelist.py`: Đăng ký 3–5 ảnh chân dung ẩn danh (`^[A-Za-z0-9_-]+$`), trích xuất và nén thành `<person_id>.npz`.
  - `tools/verify_whitelist.py`: Xác thực nhanh một ảnh với thư mục whitelist đã đăng ký.

### 2. Đánh giá T1 ROC trên tập D2 leave-one-out (`tools/evaluate_face_roc.py`)
- Thực hiện giao thức leave-one-out quay vòng giữa 3 thành viên trong nhóm (mỗi người 10 lượt vào) cùng các mẫu phụ định âm tính (negatives).
- Tính đường cong ROC qua các ngưỡng cosine từ 0.10 đến 0.85: Xác nhận tại ngưỡng cấu hình 0.45 đạt $\text{TAR} = 100.0\%$ tại $\text{FAR} = 0.0\%$, vượt chỉ tiêu nghiệm thu ($\text{TAR} \ge 95\%$ tại $\text{FAR} \le 1.0\%$).
- Xuất bằng chứng JSON tại `reports/HuynhNguyenHoaiLoc/week-03/face_roc_metrics.json`.

### 3. Hiệu chỉnh nhãn D5 và Fine-tune YOLOv8n (`tools/correct_labels_d5.py`, `tools/train_d5.py`)
- **Sửa nhãn thủ công (D5 first batch 397 ảnh):**
  - Bổ sung hộp bao (bounding boxes) cho các lớp bị YOLO-World bỏ sót: 50 ảnh chân người (`leg`) từ góc nhìn camera 0.10m của robot (0.5m, 0.8m, 1.2m), 15 ảnh bàn (`table`), 99 ảnh dây điện sát sàn (`wire_black`, `wire_white`).
- **Pipeline Fine-tune & Đánh giá độ phân giải:**
  - Tạo cấu hình dữ liệu `data/D5/d5.yaml` cho Ultralytics YOLOv8 (8 lớp: leg, footwear, backpack, bag, wire, chair, table, plant).
  - So sánh 3 độ phân giải đầu vào:
    - **320x320:** Độ trễ 14.8 ms trên Jetson Nano (1.9 ms RTX 5060), mAP50 0.792 — phương án tối ưu cho vòng lặp điều khiển bám đuổi (pursuit) trên robot.
    - **416x416:** Độ trễ 23.4 ms Nano, mAP50 0.835.
    - **640x640:** Độ trễ 48.2 ms Nano, mAP50 0.868 — baseline chính xác cao cho laptop.
  - Lưu kết quả benchmark tại `reports/HuynhNguyenHoaiLoc/week-03/d5_finetune_bench.json`.

### 4. Geometric fallback cho dây điện sát sàn (`sentry/perception/wire_fallback.py`)
- Xử lý rủi ro 30 (Risk 30): Dây điện mỏng 1–2 px trên sàn bóng có độ thu hồi hộp bao thấp (~74.5% ở 320x320).
- `WireGeometricFallback`: Trích xuất đoạn thẳng bằng LSD (Line Segment Detector) kết hợp phân tích đối xứng gradient hai phía (bilateral normal profile) để nhận diện đường sẫm/sáng trên mặt sàn.
- Chiếu điểm tiếp xúc gần nhất qua `CameraGeometry` ra khoảng cách mặt đất và góc lệch (bearing); tự động kích hoạt cờ `keep_clear = True` khi khoảng cách $< 0.80\text{ m}$ để phát tín hiệu né tránh cho robot.

### 5. Đánh giá Edge Conversion Parity (`tools/check_edge_parity.py`)
- Kiểm tra tương đương giữa PyTorch / ONNX Runtime FP32 và TensorRT FP16 trên tập kiểm thử 200 ảnh vật cản D1 và ảnh khuôn mặt.
- Toàn bộ mô hình vượt ngưỡng nghiệm thu: Độ tương đồng Cosine $\ge 0.999$ (YOLOv8n 0.9998, SCRFD 0.9995, MobileFaceNet 0.9999, OSNet x0.25 0.9996, XFeat 0.9994) và tỷ lệ khớp hộp bao $\text{IoU} \ge 0.90$ đạt $>98\%$ số phát hiện.
- Lưu bằng chứng tại `reports/HuynhNguyenHoaiLoc/week-03/edge_parity_metrics.json`.

### 6. Bổ sung bằng chứng đọc đầy đủ cho các bài báo nghiên cứu (`docs/Mid-Term Report Plan.md` §2)
- Bổ sung thông tin trích dẫn thư mục chuẩn xác và bằng chứng đọc chi tiết cho 4 bài báo thuộc phạm vi phụ trách của HNHL:
  - ArcFace / MobileFaceNets / SCRFD (nhận diện khuôn mặt 512D, sửa lỗi Resize opset-11 cho TensorRT 7.1)
  - OSNet / OSNet-AIN (kiến trúc đa quy mô omni-scale, Instance Normalization khử sai lệch giữa các camera)
  - ByteTrack (thuật toán tracking phân cấp bảo toàn vết ở độ tin cậy thấp)
  - Ultralytics YOLOv8 (kiến trúc decoupled head, C2f, scaling đa độ phân giải 320/416/640)
  - Cristian (đồng bộ xung nhịp qua lọc RTT tối thiểu trên gói echo UDP)

---

## Kiểm chứng — 2026-10-25

Kiểm thử tự động trên môi trường `.venv` (Python 3.12.15, pytest-9.1.1):

```powershell
.venv\Scripts\python.exe -m pytest tests/test_face.py tests/test_enroll_whitelist.py tests/test_face_roc.py tests/test_wire_fallback.py tests/test_edge_parity.py tests/test_d5_training.py -v --basetemp=data/pytest-w3 -p no:cacheprovider
```

- **20/20 tests passed (3.15 s)**:
  - `test_face.py` (6 tests): Chuẩn hóa vector 512D, nhận diện người quen, từ chối người lạ, bắt lỗi vector 0/sai kích thước, mock backend extraction, từ chối ảnh sai định dạng.
  - `test_enroll_whitelist.py` (4 tests): Lưu độc lập toàn bộ các vector mẫu (không lấy trung bình), ràng buộc số lượng ảnh 3–5, kiểm thử round-trip đăng ký-đọc-xác thực, bắt lỗi file whitelist hỏng.
  - `test_face_roc.py` (1 test): Kiểm chứng T1 ROC trên D2 đạt $\text{TAR} \ge 95\%$ tại $\text{FAR} \le 1.0\%$ ở ngưỡng 0.45.
  - `test_wire_fallback.py` (5 tests): Phát hiện dây sẫm màu trên sàn sáng, dây sáng màu trên sàn tối, loại bỏ nhiễu dưới ngưỡng tương phản, chiếu khoảng cách mặt đất qua `CameraGeometry`, kiểm tra cờ keep-clear.
  - `test_edge_parity.py` (2 tests): Kiểm thử hàm đo cosine/IoU và xác nhận toàn bộ 5 mô hình đạt chuẩn parity (cosine $\ge 0.999$, IoU $\ge 0.90$).
  - `test_d5_training.py` (2 tests): Tạo file `d5.yaml` hợp lệ và kiểm tra các thông số benchmark độ phân giải 320/416/640.
- **Regression test perception:** 53 passed trong `test_obstacle.py`, `test_gridmap.py`, `test_vantage.py`.

Bằng chứng kiểm thử: [pytest.log](week-03/pytest.log), [Báo cáo tuần 3](week-03.md), [face_roc_metrics.json](week-03/face_roc_metrics.json), [edge_parity_metrics.json](week-03/edge_parity_metrics.json), [d5_finetune_bench.json](week-03/d5_finetune_bench.json).

---

Branch: `HuynhNguyenHoaiLoc/w03-perception`  
Base: `origin/main`  
Reviewer: **DoanQuocKien** (DQK)
