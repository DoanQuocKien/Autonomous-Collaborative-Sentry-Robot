# Chương 2 — Kiến thức và phương pháp đã nghiên cứu

## 2.1 Phương pháp được dùng trong hệ thống

| Công trình | Kiến thức áp dụng | Vị trí trong dự án |
| :-- | :-- | :-- |
| Kannala & Brandt, TPAMI 2006 | Mô hình camera fisheye | Hiệu chuẩn/undistort trước chiếu tia mặt sàn |
| Garrido-Jurado et al., Pattern Recognition 2014 | Mốc ArUco | Tư thế camera và hiệu chỉnh định vị |
| Collins & Bartoli, IJCV 2014 | IPPE cho mặt phẳng | PnP marker vuông, loại nghiệm sai |
| Siegwart et al., MIT Press 2011 | Động học robot vi sai | Unicycle, dead reckoning, sai số odometry |
| Fischler & Bolles, CACM 1981 | RANSAC | Homography, kiểm tra hình học cửa |
| Potje et al., CVPR 2024 | XFeat | Đặc trưng cục bộ để ghép cửa |
| Oquab et al., TMLR 2024 | DINOv2 | Descriptor cửa khi khác camera tham chiếu |
| Deng et al., CVPR 2019; Chen et al., CCBR 2018 | ArcFace / MobileFaceNets | Face embedding và so whitelist |
| Zhou et al., ICCV 2019 / TPAMI 2021 | OSNet / OSNet-AIN | Re-ID giữa góc cửa và robot |
| Zhang et al., ECCV 2022 | ByteTrack | Liên kết detection confidence cao/thấp |
| Cristian, Distributed Computing 1989 | Clock synchronization | Echo RTT, so timestamp video |
| Hart et al., IEEE TSSC 1968 | A* | Nối viewpoint trên occupancy grid; phần robot còn dự kiến |

## 2.2 Lựa chọn và giới hạn

ORB được dùng làm baseline của bài so nhận diện cửa trước khi chọn XFeat. Homography cung cấp kiểm tra hình học và bearing nhưng không tự cho khoảng cách cửa khi thiếu tỷ lệ metric. DINOv2 hỗ trợ tham chiếu khác camera, với chi phí tính toán lớn hơn.

YOLOv8 là công cụ phần mềm phát hiện đối tượng; fine-tune D5 điều chỉnh cho góc nhìn thấp, nhưng không loại được phản chiếu sàn. SegFormer-B0/ORG là thí nghiệm phát hiện tiếp xúc/free-space, chưa được nhận làm detector mặc định. Những lựa chọn này được đánh giá bằng dữ liệu và các thất bại cụ thể trong chương 5.

ByteTrack ID biểu diễn track, không đồng nghĩa danh tính người. Tính tương đương backend trên quỹ đạo tổng hợp khác với re-ID rank-1 hoặc số ID-switch/phút trên video người thật. Định vị cũng tách kiểm thử hình học với sai số vật lý do sàn, pin và gá camera.

**Thư mục tham khảo đã đối chiếu:** [Mid-Term Report Plan, mục 2](../../docs/Mid-Term%20Report%20Plan.md), [phương pháp HNHL](../HuynhNguyenHoaiLoc/midterm/chapter-05-current.md) và các bản thảo nguồn trong [registry editor](week-07/editor-sources.md). Tên công trình ở bảng giữ đúng phạm vi đã đọc và áp dụng; coverage/A* chưa được trình bày như kết quả robot.
