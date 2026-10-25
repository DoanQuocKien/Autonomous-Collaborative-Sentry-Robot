# HNHL W3: InsightFace whitelist, real D5 YOLOv8n fine-tuning, wire failure audit and evaluation harnesses

## Mục tiêu và thay đổi

PR này cập nhật công việc **Tuần 3** của `HuynhNguyenHoaiLoc (HNHL)` theo `docs/Project Specification.md` và `docs/Implementation Plan.md`. **Phân biệt rõ unit tests T0, thí nghiệm D5 nội bộ và nghiệm thu T1 độc lập. Không khẳng định những chỉ tiêu chưa đạt là PASS.**

### 1. InsightFace whitelist và kiểm thử T0

- `sentry/perception/face.py`: kiểm tra và chuẩn hóa embedding 512D, từ chối NaN/Inf/zero vector; xác thực bằng **max cosine** trên tất cả 3–5 vector mẫu của mỗi danh tính, không lấy trung bình; ngưỡng cấu hình 0.45.
- InsightFace `buffalo_s`, CPU/CUDA provider; `tools/enroll_whitelist.py` và `tools/verify_whitelist.py` dùng `.npz` với `allow_pickle=False` và ID ẩn danh.
- `tools/evaluate_face_roc.py` đã có logic leave-one-out, TAR/FAR/FRR và unit test trên vector mô phỏng; **D2 ROC thực tế chưa được đo (T1 PENDING).**

### 2. Gán nhãn và chuẩn bị D5

- D5 first batch có **397 ảnh thật**, cùng một phiên ghi hình/phòng sàn bóng.
- Đã bổ sung và sửa nhãn mục tiêu: `leg` 50/50, `footwear` 49/49, `backpack` 49/49, `bag` 50/50, `table` 15/15, `wire_black` 50/50, `wire_white` 49/49. Các con số biểu thị **ảnh có nhãn mục tiêu**, chưa phải xác nhận mọi bounding box nền đều được kiểm duyệt toàn diện.
- `tools/prepare_d5_yolo_dev.py` xuất `data/D5_yolo_dev/data.yaml` và tập **307 train / 90 internal dev-validation** (241 GT instances trong dev-val); **0 exact duplicate image across split**. Đây **không phải** split session độc lập; có nguy cơ tương đồng hình nền/temporal leakage.
- Các công cụ hỗ trợ: `tools/annotate_d5.py`, `tools/annotate_d5_table.py`, `tools/edit_d5_labels.py`, `tools/preview_d5_labels.py`.

### 3. Fine-tune YOLOv8n thật (RTX 5060)

- Đã chạy **3 lần huấn luyện thực tế**, khởi tạo `yolov8n.pt`, cùng train/dev-val, `epochs=30`, `batch=8`, `seed=42`, `workers=0`, `device=0`, Ultralytics **8.4.172** / torch **2.9.1+cu128**. Các lệnh thực tế sử dụng `yolo detect train ... data=data/D5_yolo_dev/data.yaml`, **không** sử dụng benchmark số cứng cũ của `tools/train_d5.py`.

| Resolution | Precision | Recall | mAP50 | mAP50–95 | Wire Recall | Wire mAP50 |
| :-- | --: | --: | --: | --: | --: | --: |
| 320 | 0.730 | 0.693 | 0.739 | 0.574 | 0.050 | 0.1780 |
| 416 | 0.677 | 0.720 | **0.758** | **0.608** | **0.100** | 0.0458 |
| 640 | 0.588 | 0.803 | 0.750 | 0.606 | 0.050 | 0.0419 |

- 416 đạt mAP tổng thể cao nhất trong thử nghiệm phát triển, **không phải cấu hình đã được chứng nhận trên robot**. Wire Recall cao nhất **10%**, chưa đạt mốc **80%** của kế hoạch.
- Checkpoints/logs lưu cục bộ trong `runs/detect/runs/d5_dev/yolov8n_{320,416,640}/`; không có benchmark latency Jetson Nano được đo trong thí nghiệm này.
- Dữ liệu số thực tế tóm tắt tại `reports/HuynhNguyenHoaiLoc/week-03/d5_finetune_results_real.json` khi file này được stage. Lưu ý `tools/train_d5.py` và `data/D5/d5.yaml` kế thừa vẫn cần kiểm tra/fix đường dẫn `train`/`val` trước khi dùng như entrypoint chính thức.

### 4. Chẩn đoán Wire: định vị, báo nhầm và geometric fallback

- YOLO-416, `conf=0.05`: **20/20 ảnh có GT Wire** có ít nhất một dự đoán Wire, tổng 23 box; khớp GT **20/20 tại IoU ≥0.25**, nhưng chỉ **1/20 tại IoU ≥0.50**; median best IoU **0.351**. Đây là chẩn đoán low-confidence, **không** thay thế mAP/Recall chuẩn.
- Ở 70 ảnh không có nhãn Wire, **5/70** có dự đoán Wire tại `conf=0.05`; năm ảnh kiểm tra trực quan cho thấy nhầm đường ron/sàn.
- `WireGeometricFallback` (LSD + profile tương phản) đạt **5/5 synthetic T0 tests**. Khi thử trên ảnh D5 thật: có candidate trong vùng GT tại **20/20 ảnh có dây**, nhưng **70/70 ảnh không có GT Wire cũng có line candidates**. Đây không phải true recall/FPR của detector; ảnh đối chứng cho thấy nhiều candidate là ron gạch. **NO-GO dùng standalone hoặc merge mù với YOLO.**
- Công cụ chẩn đoán: `tools/audit_d5_wire_predictions.py`, `tools/visualize_d5_wire_iou.py`, `tools/audit_d5_geometric_fallback.py`.

### 5. Segmentation pilot (chỉ gán mask)

- `tools/annotate_d5_wire_masks.py`: đã tạo **12/12 binary masks** trên training frames (wire_black/white × 0.30/0.50/0.70 m × 2).
- Ảnh tổng hợp cho thấy đa phần mask bám theo dây nhưng một số đoạn dây cuộn/đầu nối có thể tô rộng; còn cần QA ở mức pixel trước khi dùng làm GT cuối.
- **Chưa train segmentation, chưa đo được performance, và chưa có session T1 độc lập.**

### 6. Edge parity và tài liệu

- `tools/check_edge_parity.py`: đã triển khai hàm đánh giá cosine similarity, box-IoU và plan lấy mẫu 200 frame D1; **chưa đo parity ONNX/TensorRT FP32/FP16 trên engine thực tế**.
- Phạm vi nghiên cứu tài liệu: ArcFace/MobileFaceNets/SCRFD, OSNet/OSNet-AIN, ByteTrack, Ultralytics YOLOv8 và Cristian; OSNet/tracking thuộc Week 4–5.

---

## Kiểm thử và trạng thái nghiệm thu

- **20/20 T0 unit tests PASS** trong `tests/test_face.py`, `test_enroll_whitelist.py`, `test_face_roc.py`, `test_wire_fallback.py`, `test_edge_parity.py`, `test_d5_training.py` (kết quả kiểm thử trước đó). `tests/test_wire_fallback.py` được chạy lại: **5/5 PASS**.
- Regression suite (`test_obstacle`, `test_gridmap`, `test_vantage`): báo cáo trước ghi nhận **53 passed**; cần chạy lại nếu có sửa đổi liên quan.
- **T0 Face/Whitelist:** PASS. **D2 face ROC T1:** PENDING. **Edge parity T1:** PENDING.
- **D5 fine-tune 320/416/640:** ĐÃ CHẠY THẬT (internal dev-val, không phải T1).
- **Wire recall ≥80%:** NOT MET (cao nhất 10%). **Geometric fallback:** T0 synthetic PASS, real-data **NO-GO standalone**. **Segmentation:** 12 mask pilot, chưa train.

**Giới hạn bằng chứng:** Các model checkpoints, kết quả dự đoán, preview, binary segmentation masks và full Ultralytics logs hiện chủ yếu ở local working directory. PR chỉ nên trỏ tới artefact đã được stage hoặc được lưu ở nơi dùng chung có quyền phù hợp. Không upload ảnh khuôn mặt/whitelist riêng tư lên repo công khai.

**Ràng buộc PR:** Không mở rộng sang Week 4 OSNet hoặc Week 5 tracking trong commit này. Chỉ commit script/dữ liệu/báo cáo được kiểm tra. Cần sửa entrypoint legacy `tools/train_d5.py` để thống nhất với `data/D5_yolo_dev/data.yaml` trước khi mô tả harness đó là tái lập được.

---

Branch: `HuynhNguyenHoaiLoc/w03-perception`  
Base: `origin/main`  
Reviewer: **DoanQuocKien** (DQK)
