# Chương 5 — Nhận thức thị giác, tối ưu hóa và triển khai thiết bị nhúng

**Chủ trì:** HuynhNguyenHoaiLoc (HNHL) cùng kouun-rokku (KR, cửa) và DoanQuocKien (DQK, edge) • **Ngân sách:** 3,5 trang

## 5.1 Ước lượng khoảng cách vật cản mặt sàn

Hệ thống phát hiện vật cản bằng YOLOv8n kết hợp ước lượng điểm tiếp xúc chân vật thể trên sàn. Sàn nhà có độ bóng cao tạo ra hình ảnh phản chiếu gương gây nhầm lẫn điểm chân bounding box. Module `sentry/perception/contact.py` áp dụng bộ lọc cạnh ngang và kiểm tra độ tin cậy hình học để từ chối các ước lượng không đủ bằng chứng.
- Thử nghiệm trên 9 vị trí ghế thực tế trên sàn glossy (Hình F10) đạt sai số trung vị (median) **5,34%** và phân vị p90 là **20,91%**.

![F10_distance](reports/HuynhNguyenHoaiLoc/midterm/figures/F10_distance.png)
*Hình F10: Độ chính xác ước lượng khoảng cách chân ghế trên mặt sàn bóng qua camera fisheye nắn thẳng.*

## 5.2 Huấn luyện phát hiện vật cản sàn nhà (Tập dữ liệu D5)

Tập dữ liệu D5 gồm 397 ảnh chụp thực tế từ góc nhìn sát sàn của JetBot (chân bàn ghế, ba lô, giày dép, cây cảnh, dây cáp đen/trắng). Mô hình YOLOv8n được fine-tune qua 30 epochs:
- Độ chính xác mAP50 đạt **0,810** ở độ phân giải 640×640.
- Recall phát hiện chân bàn/ghế đạt **96,0%**.
- Vật cản dây cáp mỏng là đối tượng thách thức nhất (recall thấp do kích thước chỉ vài pixel), được hệ thống bổ sung lớp fallback hình học cạnh sàn (`sentry/perception/wire_fallback.py`).

## 5.3 Nhận diện lối vào (Entrance Matching Bake-off)

Trong Giai đoạn 1, robot phải nhận diện đúng cửa vào phòng từ khoảng cách 1,5–3,0 m. Nhóm đã thực hiện bake-off thực nghiệm giữa 3 thuật toán trên tập ảnh cửa D1 (`reports/kouun-rokku/week-05/F12_entrance_bakeoff.png`):
- **ORB (Binary baseline):** Đạt AUC 0,91, trượt khi góc nhìn nghiêng quá 30°.
- **DINOv2 (Global descriptor):** Đạt AUC 0,98, nhận diện tốt toàn cảnh nhưng không xác định được ma trận biến đổi affine/homography của khung cửa.
- **XFeat (Local feature matching):** Đạt **AUC 0,99–1,00**, số lượng inliers homography RANSAC vượt trội, xác định chính xác góc phương vị cửa để robot căn chỉnh sweet-spot. XFeat được chọn làm phương pháp mặc định.

## 5.4 Xác thực khuôn mặt tại cửa (Face Verification)

Trạm ESP32-CAM thu nhận khuôn mặt người bước vào cửa. Module `FaceVerifier` (`sentry/perception/face.py`) sử dụng SCRFD phát hiện khuôn mặt và MobileFaceNet tạo vector đặc trưng 512D chuẩn hóa.
- Đối soát với tập người đăng ký (whitelist) dựa trên độ tương đồng cosine cực đại (ngưỡng 0,45).
- Thử nghiệm pilot trên 125 frame mặt người (tập D2 cafe, 3 thành viên DQK, HNHL, KR) theo phương pháp leave-one-out cho thấy tại ngưỡng 0,45 đạt tỷ lệ chấp thuận thực TAR 82,99% (Hình F13).

![F13_face_roc](reports/HuynhNguyenHoaiLoc/midterm/figures/F13_face_roc.png)
*Hình F13: Đường cong ROC kiểm định Face Verification trên tập dữ liệu lối vào D2.*

## 5.5 Nhận dạng lại ngoại hình (Re-ID) và Theo dõi mục tiêu (ByteTrack)

Khi kẻ xâm nhập bị từ chối tại cửa, một vector đặc trưng toàn thân 512D được trích xuất qua mạng `OSNet-AIN x1.0`. Vector này được đóng gói cùng thông tin sector di chuyển (Trái/Giữa/Phải dựa trên độ trôi bounding box 2 giây) gửi sang robot JetBot.
- Trên robot, module `PersonTracker` (`sentry/perception/tracker.py`) kết hợp phát hiện người YOLOv8n và bộ theo dõi ByteTrack thuần Python 3.6 do nhóm tự vendor (`third_party/bytetrack/`).
- Thuật toán khóa mục tiêu (Target Lock) so khớp cosine giữa vector ngoại hình quan sát với vector mục tiêu ban đầu (ngưỡng 0,70), đảm bảo robot bám đúng đối tượng xâm nhập ngay cả khi có người khác xuất hiện trong tầm nhìn.
- Đánh giá trên tập benchmark hoán đổi quỹ đạo (crossing tracks) đạt độ khớp ID **100,0%** so với bản gốc Ultralytics.

## 5.6 Tối ưu hóa và kiểm thử hiệu năng GPU (Workload Profiling)

Đo đạc toàn diện trên GPU laptop (RTX 5060/4050) khi nạp đồng thời toàn bộ các mô hình (YOLOv8n + ByteTrack + OSNet + YOLOv8-pose + SCRFD + MobileFaceNet + XFeat/DINOv2):
- Bộ nhớ VRAM chiếm dụng ở trạng thái resident ổn định ở mức **0,939 GiB** (thấp hơn rất nhiều so với trần 5,5 GB quy định).
- Tốc độ xử lý khi điều phối luồng cửa định kỳ đạt **19,65 FPS**, đáp ứng hoàn toàn yêu cầu thời gian thực (>15 FPS).

![F9_gpu_pie](reports/HuynhNguyenHoaiLoc/midterm/figures/F9_gpu_pie.png)
*Hình F9: Phân bổ tài nguyên VRAM và độ trễ tính toán giữa các mô hình học sâu.*

---
