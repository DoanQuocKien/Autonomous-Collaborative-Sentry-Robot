# Mục 5.x — Tối ưu hóa và triển khai trên thiết bị (Jetson Nano)

**Bản thảo DQK (2026-11-13), khoảng 0,7 trang trong Chương 5.** Nguồn: `docs/Edge Deployment.md` (đo ngày 16/10, `reports/DoanQuocKien/week-02/edge_deploy/`), số liệu laptop của HNHL (PR #100, `reports/HuynhNguyenHoaiLoc/week-06/`). Hình: F20 (engine trên robot), F21 (bench trên robot), F18 (FP32 so với FP16, HNHL).

---

## 5.x.1 Chuyển đổi và độ trễ trên robot

Các mô hình được xuất sang ONNX trên laptop, rồi **xây engine TensorRT 7.1.3 FP16 ngay trên robot** (Jetson Nano 4 GB, JetPack 4.5, CUDA 10.2, `trtexec`, batch 1, hình dạng cố định). Thời gian GPU mỗi lần suy luận (F20):

| Mô hình | Đầu vào | GPU (ms) | Engine (MB) |
| :-- | :-- | :-: | :-: |
| YOLOv8n phát hiện | 320 | **14,8** (FP32: 20,7) | 9 |
| YOLOv8n-pose | 320 | 15,7 | 9,1 |
| OSNet x0,25 | 256×128 | 9,3 | 1,5 |
| OSNet-AIN x1,0 | 256×128 | 26,6 | 6,6 |
| XFeat (khung xương) | 480×640 | 37,2 | 5,0 |
| SCRFD det_500m | 320×320 | 8,5 | 2,4 |
| MobileFaceNet | 112×112 | 14,8 | 7,6 |
| DINOv2 ViT-S/14 | 336×448 | 359,5 | 45,6 |

DINOv2 (0,4–2,8 khung/giây) **ở lại laptop**; phần còn lại đủ nhanh để chạy trên robot.

**Độ tương đương với laptop (FP32, ONNX Runtime):** cosine 1,00000 trên đầu ra thô của YOLOv8n và YOLOv8n-pose (IoU hộp tốt nhất 0,96–1,00), 1,00000 và 0,99998 cho hai biến thể OSNet, 0,99998–1,00000 cho XFeat, 0,99998 cho MobileFaceNet. **Lỗi tìm được:** SCRFD xuất từ insightface bị TensorRT 7.1 tính **sai** (cả FP32 lẫn FP16; điểm khuôn mặt tốt nhất 0,720 so với 0,813; mốc khuôn mặt lệch tới khoảng 10 px) do phép `Resize` dạng `sizes` của opset 11; sửa bằng cách viết lại phép nâng mẫu gần nhất 2× thành một ConvTranspose theo nhóm. Chưa kiểm tra: độ chính xác trên dữ liệu riêng (D1/D2) và ảnh hưởng FP16 lên Rank-1 của re-ID.

## 5.x.2 Bench trực tiếp trên robot (F21)

`jetson/edge_bench.py` đọc luồng camera, không điều khiển động cơ; camera 20 fps 640×480, 60 s mỗi chế độ:

| Chế độ | Tính toán mỗi khung (TB / p95) | Từ chụp đến kết quả (TB / p95) | FPS |
| :-- | :-: | :-: | :-: |
| Chỉ giải mã JPEG | 4,9 ms | 11,9 / 12,9 ms | 20,0 |
| Giai đoạn B (pose mọi khung, phát hiện mỗi 3 khung, OSNet mỗi 15 khung) sau tối ưu tiền/hậu xử lý | 32,0 / 44,5 ms | 37,9 / 51,1 ms | 20,0 |
| Giai đoạn C (B + đường ống cửa 5 Hz) trong cùng vòng lặp | 45,0 / 95,5 ms | 63,0 / 101,2 ms | 20,0 |
| **Giai đoạn C, đường ống cửa trong luồng riêng** | 37,0 / 65,7 ms | 45,0 / **72,1 ms** | 20,0 |
| Giai đoạn C luồng riêng, **thử 10 phút** | 35,7 / 59,5 ms | 43,4 / **69,9 ms** | 20,0, 0 / 12 000 khung bỏ |

Tách đường ống cửa sang luồng riêng giữ vòng truy bám ở 20 fps và hạ p95 từ 101 xuống 70–72 ms. Thử 10 phút trên pin: RAM 2,14 GB (không tăng), GPU 60 % trung bình, GPU 39 °C, bo mạch 5,76 W trung bình (7,0 W đỉnh); điện áp pin giảm 0,2 V sau 10 phút khi động cơ tắt (không suy ra được thời gian chạy). Khóa xung GPU (`jetson_clocks`) chỉ lợi khoảng 1 ms nên không dùng.

**Giới hạn của các phép đo 16/10:** không có ai trong khung hình (chi phí phụ thuộc người bị đánh giá thấp), đường ống cửa chạy trên ảnh tĩnh chứ chưa phải khung ESP32, không có động cơ và e-stop trong vòng lặp.

**Đo lại ngày 13/11 với người trong khung hình (chế độ MAXN, Hình F21):** `stageB` (60 s) đạt 19,75 fps, tính toán 46,4 ms (p95 75,2), từ chụp đến kết quả 61,1 ms (p95 89,2); so với 16/10 (không có người: 37,9 / 51,1 ms), có người trong khung hình thêm khoảng 23 ms. Với **đường ống cửa trong luồng riêng trên luồng ESP32 thật** (bản opt4, 12,5 fps) kết quả là 17,7 và 17,1 fps, p95 118,5 và 123,9 ms ở hai lần 60 s, và **14,45 fps, p95 153,0 ms ở lần 600 s** (người ngồi cách robot 2 m); RAM phẳng 2,13 GB, nhiệt độ GPU tối đa 38,5 °C, xung nhịp GPU/CPU không bị hạ, pin 11,96 → 11,72 V trong 11 phút. **Hàng “Edge latency and load” của kế hoạch (≥ 20 fps, p95 ≤ 100 ms) không đạt** khi có người và luồng ESP32 thật; lần chạy 28/10 ở quán cà phê (20,00 fps) chưa tái lập được và nguyên nhân chưa xác định. Hạn chế: một người, một buổi cho mỗi lần đo, lần dài nhất 600 s ngắn hơn 15 phút của kế hoạch, người đứng ở các lần 60 s nhưng ngồi ở lần 600 s, chưa có động cơ và e-stop trong vòng lặp.

## 5.x.3 So sánh FP32 và FP16 trên laptop (HNHL; RTX 5060, nhãn riêng khỏi RTX 4050)

Trên D5-640, tiến trình riêng, đo đồng bộ: FP32 **123,59 fps**, p95 12,01 ms, bộ nhớ cấp phát 32,41 MiB, mAP50 81,071 %; FP16 **107,38 fps**, p95 16,35 ms, 17,53 MiB, mAP50 81,072 %. FP16 tiết kiệm bộ nhớ nhưng **chậm hơn** trong lần đo này, nên **giữ FP32 trên laptop**; đây là bằng chứng phát triển cùng phiên, một mô hình, chưa phải độ chính xác độc lập, TensorRT hay phép đo trên RTX 4050.

## 5.x.4 Camera cửa ESP32

Tối ưu luồng ESP32-CAM (bản "opt4": cắt cảm biến, bộ nhân xung, độ mạnh ổ đĩa chân xung 0, bộ đệm gửi 23 KB) được trình bày ở mục 3.4: 12,50 fps trung bình trong 600 s (không giây nào dưới 5 fps; lần thử sớm hơn trên bàn thử 11,84 fps), khuôn mặt dự đoán khoảng 77 px ở 2,1 m trên bàn thử và đo được 68–91 px ở 3,0–1,8 m tại cửa ngày 13/11 với một người; **chưa có điểm của người lạ** nên chưa tính được FAR (xem mục 3.4).
