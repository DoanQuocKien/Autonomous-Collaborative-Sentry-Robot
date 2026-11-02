# Chương 5 — Nhận thức thị giác, tối ưu và triển khai

**Bản thảo HNHL, 2026-11-01.** Ngân sách chung chương khoảng 3,5 trang sau dàn trang; KR bổ sung nhận diện cửa, DQK hoàn thiện phần Jetson. Đây chưa phải bản nộp: các vị trí thiếu hình hoặc chưa đo được giữ trạng thái rõ ràng. Hình và số liệu chốt trước 16/11 theo kế hoạch nhóm.

## 5.1 Luồng xử lý và hệ tọa độ

Hệ thống mặc định chạy perception trên laptop: video JetBot phục vụ vật cản, vị trí cửa và người được bám; ESP32 tại cửa phục vụ whitelist và appearance handoff. YOLO tạo bbox; các nhánh sau xử lý khoảng cách, face embedding, appearance embedding hoặc track association. Module perception trả kết quả có timestamp; quyết định chuyển trạng thái và điều khiển motor thuộc tầng ứng dụng. Các thí nghiệm offline trong chương không tự gửi lệnh motor.

Ảnh camera JetBot có méo fisheye nên phép chiếu xuống sàn dùng intrinsics đã hiệu chuẩn, undistort và pose theo session. Không dùng lại góc camera của ngày trước khi mount đã dịch chuyển. Các kết quả RTX5060 Laptop của HNHL được tách khỏi target RTX4050 6GB và Jetson Nano.

## 5.2 Vật cản và khoảng cách mặt sàn

Điểm tiếp xúc với sàn được chiếu theo chiều cao lens H và pitch/roll. Khi roll bằng 0, forward distance có dạng `Z = H / tan(pitch + atan((v-cy)/fy))`; nhánh tổng quát dùng ray hình học. Tape truth của DQK là forward Z từ điểm dưới lens, khác planar range dùng cho repulsion. Không ghép detection với ground truth bằng khoảng cách dự đoán gần nhất vì sẽ làm sai số lạc quan.

Sàn glossy phản chiếu làm bbox bottom nằm thấp hơn điểm tiếp xúc thật. Bộ xử lý thử reflection symmetry, semantic/contact edge và backend YOLO-World tùy chọn; khi thiếu evidence thì abstain. Thử nghiệm ghế có distance ở 8/9 vị trí, median/p90 error 5,34%/20,91% trên các ID có estimate; p90 toàn subset chưa đạt 20%. Riêng ba vị trí chairs_c held out đạt 5,37%/17,11%, nhưng không thay full T1 có ≥20 IDs và các floor conditions. Các phương án hybrid còn chậm và không bật mặc định. [Bằng chứng issue43](ISSUE-43-HNHL.md).

D5 gồm 397 ảnh của một phòng, một session sàn bóng. Sau sửa nhãn chân người nền, đã train lại YOLOv8n ở 320/416/640, 30 epochs, batch8, seed42; split 307 train/90 dev-val giữ whole distance groups. Quyết định nhóm cho phép split cùng session trong tuần4 vì chưa có batch matte; điều này không tạo độc lập về phòng, ánh sáng hoặc background.

| Input | mAP50 | mAP50–95 | Leg recall | Wire recall tại validation operating point |
| --: | --: | --: | --: | --: |
| 320 | 0,759 | 0,626 | 0,920 | 0,000 |
| 416 | 0,753 | 0,622 | 0,920 | 0,000 |
| 640 | 0,810 | 0,656 | 0,960 | 0,000 |

640 được chọn làm development candidate, chưa là cấu hình triển khai robot. Wire chưa đạt recall80%; geometric fallback còn nhầm đường ron sàn. 12 wire masks là annotation pilot, chưa phải segmentation model đã được nghiệm thu. [Kết quả/class metrics](week-04.md), [JSON](week-04/d5_corrected_validation.json).

**F10:** cần chèn scatter sai số/tape từ các cặp prediction–truth đã review, hiển thị cả missed IDs. **F11:** cần map/vantage trên sweep có pose và tọa độ cửa/vật thật; hình declared/synthetic nếu dùng phải ghi rõ, không mô tả là bản đồ đã tự khám phá.

## 5.3 Nhận diện cửa — phối hợp KR/DQK

XFeat ghép local features của robot-eye reference với frame hiện tại, kiểm tra homography RANSAC và phân bố inliers. DINOv2 dùng descriptor toàn ảnh cho reference khác camera, như ảnh điện thoại. Ngưỡng được hiệu chuẩn bằng negative sweep theo cửa; homography hỗ trợ bearing, không tự cung cấp door range. Giả định dự án là một cửa vào mỗi phòng. KR/DQK bổ sung F12 và số liệu của cửa demo chính từ evidence của họ; không dùng workload timing ở mục5.6 làm accuracy cửa.

## 5.4 Face verification và re-ID

Whitelist dùng SCRFD/MobileFaceNet trong buffalo_s: embedding512D được L2-normalize, mỗi query so với tất cả reference và lấy maximum cosine. Threshold hiện tại0,45. Pilot D2 cafe có125 walker-face frames/21 entries/3 người, nhãn largest-face và entry segmentation tự động. Leave-one-member-out, enrollment chỉ từ entry đầu, cho194 genuine/125 impostor queries: TAR82,99%, FAR46,40% ở threshold0,45. Đây là kết quả chưa đạt, cần review walker/bystander labels và ảnh mờ trước khi kết luận khả năng nhận diện. Không chọn threshold mới trên chính pilot để tạo PASS. [F13 pilot](week-04/F13_d2_face_roc_pilot.png), [metrics](week-04/d2_pilot.json).

Person re-ID dùng crop YOLO → OSNet-AIN x1.0 hoặc OSNet x0.25 với weights đã train re-ID, không thay bằng ImageNet pretraining. Hai model đều tạo vector512D nhưng thuộc các embedding spaces khác nhau; handoff phải cùng model/hash và preprocessing. Trên125 frame D2 chỉ ghép được23 body crops không mơ hồ; thiếu gallery crop ở2/3 người nên chưa có rank-1/CMC hợp lệ hoặc model thắng. **F14 còn chờ gallery toàn thân, D3/cross-camera và protocol đủ danh tính.**

## 5.5 Tracking và khóa mục tiêu

Tuần5 bổ sung Ultralytics ByteTrack: association theo chuyển động/IoU dùng cả detection confidence thấp để nối track qua các frame khó. OSNet kiểm tra appearance của từng track đang quan sát; track ID không phải danh tính. Khóa mục tiêu yêu cầu cosine và separation margin, xác nhận qua hai frame; thiếu hoặc mơ hồ thì không trả target. Sau che khuất hoặc tái sử dụng ID phải xác nhận lại. Seq reset/gap được tách bằng epoch. Reference target không tự cập nhật bằng query để giảm identity drift. Record simulated của replay không được dùng để lock người thật.

Đã có CPU/synthetic tests, GPU runtime và replay822 frame D2 không gán body IDs. Đây chưa phải đánh giá ID switches: D3 cảnh hai người có reviewed IDs/visibility và timestamps còn thiếu. Mục tiêu ≤1 ID switch/phút được giữ để nghiệm thu sau; không đếm track IDs tự sinh rồi gọi đó là ground truth. [Triển khai, tests và giới hạn](week-05.md).

## 5.6 GPU workload và triển khai thiết bị — phối hợp DQK

HNHL đo model resident cùng GPU, gồm YOLOv8n, OSNet-AIN, YOLOv8n-pose, SCRFD/MobileFaceNet, XFeat và DINOv2-B. Benchmark100 iterations sau5 warmup; DINO FP16 theo backend hiện có, các Torch model còn lại FP32. Body/face workloads được pad ít nhất2 crop nếu thiếu detections, được ghi riêng là synthetic. Một nguồn ảnh dùng cho các nhánh thay cho hai camera thật; không gồm transport/map/control.

| Workload trên RTX5060 | FPS | p95 (ms/frame) | Peak device-used (GiB) |
| :-- | --: | --: | --: |
| Tất cả stage mỗi frame | 12,719 | 90,751 | 0,939 |
| XFeat, không DINO, mỗi frame | 14,245 | 82,986 | 0,622 |
| Đủ model resident, face/entrance theo lịch yêu cầu5Hz | 19,652 | 87,621 | 0,939 |

Run scheduled thực tế đạt4,520 door updates/s; scheduler hiện chỉ nằm trong profiler. Hai run mỗi-frame chưa đạt15FPS; run scheduled đạt budget cho workload trên máy này, chưa xác nhận target RTX4050. NVML device-used bao gồm Torch/ORT/driver/process khác và có thể bỏ lỡ spike ngắn giữa mẫu20ms; không đồng nhất với PyTorch allocator. Nguồn AC/battery chưa được xác nhận. [F9](week-05/F9_pipeline_gpu.png), [JSON từng cấu hình](week-05.md).

Model D5 custom đã export ONNX opset11 fixed-shape; laptop PyTorch/ONNX parity trên90 ảnh có90/90 cùng số bbox,294 boxes ghép đủ ở IoU≥0,9. Đây không phải TensorRT accuracy. DQK bổ sung quy trình build trên Nano, workaround SCRFD Resize và F20/F21 từ evidence thực tế. Parity stock edge models của DQK có cosine≥0,999, nhưng YOLOv8n chỉ cùng count205/208 frames; không dùng kết quả này để chứng nhận detector D5 custom hay OSNet-AIN handoff. [D5 parity](week-04/d5_onnx_real_parity.json), [DQK edge parity](../DoanQuocKien/week-04/edge_parity/README.md).

Các thử nghiệm còn lại gồm D3 ID-switch/re-lock, GPU budget RTX4050/dual-stream, FP32–FP16 accuracy comparison, map/vantage bằng dữ liệu thật và Wire. Chúng được ghi là đang thực hiện, không phải kết quả đã đạt. Danh mục tài liệu nền và phân công tham khảo: [Mid-Term Report Plan](../../docs/Mid-Term%20Report%20Plan.md), gồm OSNet, ByteTrack, SCRFD/MobileFaceNets/ArcFace, YOLOv8 và Cristian.
