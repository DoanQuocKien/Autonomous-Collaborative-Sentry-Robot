# Bản thảo DQK (2026-11-11): giới hạn đo được, tiếp cận cửa, hàng kết quả và rủi ro

**Phạm vi.** Đoạn văn cho Chương 4 (mục 4.x), Chương 6 (mục 6.x, phần bộ điều khiển của DQK), các hàng cho Chương 7 và rủi ro cho Chương 8 theo [Mid-Term Report Plan](../../docs/Mid-Term%20Report%20Plan.md). Mọi con số lấy từ `reports/DoanQuocKien/week-06/classroom_1111_pm/README.md` và các tệp dữ liệu cạnh đó (một buổi, một sàn gạch bóng 0,6 m, một cửa; không phải nghiệm thu T1/T2). Hình: F22-F25 (`reports/DoanQuocKien/week-06/figures/`). Đã sửa chỗ nào kiểm chứng được; chỗ chưa kiểm chứng ghi rõ.

---

## 4.x Giới hạn của chuyển động vòng hở (cho Chương 4, ~0,4 trang, hình F22)

Robot không có bộ mã hóa vòng quay, nên vị trí được ước lượng từ lệnh (v, ω) đã hiệu chỉnh, cộng hiệu chỉnh bằng marker ArUco khi nhìn thấy. Sai số hệ thống của kiểu truyền động vi sai này đã được mô tả trong tài liệu [Borenstein và Feng, 1996]. Bản hiệu chỉnh ngày 11/10 cho độ lệch hướng −0,19 rad/m (khoảng −11°/m). Trên sàn gạch bóng của phòng học, ngày 11/11, độ lệch đo được **không ổn định**: tổng hợp mọi lần chạy tiến thẳng có marker trong tầm nhìn (13 lần, v từ 0,4 đến 1,0), độ lệch hướng trên mỗi mét dao động từ −16 đến +59°/m; riêng với v ≈ 0,6 (cùng một lệnh) là −16, −3, +10, +18, +22 và +23°/m (Hình F22). Ba đoạn chạy của ngày 11/11 ở v = 0,55 lệch khoảng 12 đến 15°/s về bên trái, gấp 5 đến 6 lần giá trị hiệu chỉnh tháng 10 và ngược dấu. Ở v = 0,85 và 1,0 độ lệch nhỏ hơn (+8 và +4°/m, mỗi mức chỉ một lần chạy). Nguyên nhân chưa được chứng minh: có thể do sàn, điện áp pin thấp hơn (11,5 đến 12 V) và giá trị động cơ gần vùng chết (ghi chú JetBot ngày 06/10).

**Hệ quả thiết kế:** không thể tin vào hướng sau một đoạn chạy vòng hở. Quy tắc áp dụng là *đo lại sau mỗi lần di chuyển*: hướng được lấy từ cảm biến (cửa, marker), không từ lệnh. Pha quay tại chỗ thì ổn định: 23 đến 27° cho mỗi xung 0,2 s, độ lệch chuẩn khoảng 2° (ba lần quét, 13 đến 16 điểm dừng mỗi vòng).

---

## 6.x Tiếp cận cửa bằng xung và đo lại (cho Chương 6, ~0,5 trang, hình F23)

Robot cần tự đến vị trí đỗ trong cửa sổ 1,5-3,0 m trước cửa. Vì bộ phát hiện cửa chỉ cho **góc phương vị** (không cho khoảng cách), và vì chuyển động vòng hở lệch như mục 4.x, chúng tôi dùng vòng lặp dừng-và-đi (`tools/approach_door.py`): đo cửa (trung vị 5 khung hình: phương vị và diện tích đường viền khớp) → nếu phương vị nằm ngoài cửa sổ trung tâm thì quay một xung ngắn về phía cửa, nếu không thì chạy một đợt 0,6 s ở v = 0,85 → dừng 0,8 s → đo lại. Khoảng cách ước lượng từ diện tích đường viền (tỉ lệ nghịch với bình phương khoảng cách), lấy mốc từ **một giá trị đo bằng thước** ở lần nhìn thấy đầu tiên; dừng khi ước lượng đạt 2,0 m. Có kiểm tra video cũ (khung hình quá 0,5 s thì không dùng và không gửi lệnh) và an toàn R1/e-stop như các công cụ khác.

**Kết quả (một lần chạy `ap_1`, một cửa, một ngày):** 51 bước, 10 đợt chạy (thời gian chưa đo chính xác, ước vài phút), không cần người can thiệp trong lúc chạy. Robot dừng với ước lượng 1,97 m; đo thước sau đó **1,67 m**, hướng thẳng vào tâm cửa: vị trí đỗ hợp lệ (cửa sổ 1,5-3,0 m). Sai số khoảng cách +0,30 m (+18%, ước lượng dài hơn). Phương vị cửa khớp thước trong khoảng 1° (−63,6° so với −65°; −128,9° so với −130°).
**Hạn chế đã biết:** (a) khoảng cách đầu vào là giá trị đo thước, chưa tự suy ra; (b) 36/51 bước là xung quay "dao động": xung ngắn nhất quay trung vị 13,5° (độ lệch chuẩn 5,9°) trong khi cửa sổ trung tâm chỉ ±4°; mô phỏng dựa trên chính nhật ký này cho thấy cửa sổ ±8° giảm từ 34 xuống 16 bước (mặc định mới; **chưa thử trên robot**, mô phỏng dùng mô hình rút ra từ chính lần chạy này); (c) kiểm tra vật cản chỉ dùng các marker phía trước; sàn phải được dọn sạch.

**Phương án đã thử và thất bại (có số đo):** tam giác hóa vị trí cửa từ hai lần quét 360° cách nhau ~1,2 m cho khoảng cách dài hơn thực tế +72% (thước 1,8 m, ước 3,1 m) và +45% (3,42 m so với 4,96 m), dù phương vị đúng trong 1°. Nguyên nhân khả dĩ (một phần được kiểm chứng): hướng của lần quét thứ nhất là tổng của khoảng 15 góc xung (độ lệch ~2° mỗi xung), sai số tích lũy; hai lần quét có kiểm tra khép vòng cho thấy lệch −1,7° và −8,2°. Một bộ ước lượng bình phương tối thiểu có khép vòng (`tools/door_pose.py`, mô phỏng 300 hạt giống: sai số khoảng cách trung vị/90% giảm từ 8,8/35,7% xuống 5,5/21,4% với 2 marker, từ 6,6/18,3% xuống 3,8/9,4% với 3 marker) **chưa được kiểm chứng trên dữ liệu thật** vì các lần chạy đó không lưu quan sát từng điểm dừng; lần chạy tới sẽ lưu và cần đo thước tại điểm cuối.

---

## Các hàng cho Chương 7 (bảng "đã chạy gì")

| Mục | Kết quả đo được 11/11 | Trạng thái |
| :-- | :-- | :-- |
| Tiếp cận cửa tự động | 1 lần: đỗ ở 1,67 m (thước), ước 1,97 m, 51 bước | một lần, một cửa; chưa phải nghiệm thu T2 |
| Độ lệch chuyển động vòng hở | −16 đến +59°/m ở v ≈ 0,55-0,6 (F22) | giới hạn đã ghi nhận |
| Khoảng cách người, 3 người × 1,2/1,8/2,4 m (F24) | hàng chân: sai lệch ≤ 0,1-0,2 m so với kỳ vọng nếu bù 3,5 px, thiếu 0,25-0,55 m nếu không bù; thân (vai-hông, tiên nghiệm 0,50 m): −0,2 đến +0,2 m | mỗi điểm 12 khung hình; độ lệch thấu kính (0,2-0,26 m) chưa đo |
| Mặt tại cửa bằng ESP32 (D2, 3 thành viên, F25) | mặt rộng 22-53 px (pilot quán cà phê 45-60 px); buffalo_s: TAR 0,40 tại FAR 0,066 (ngưỡng 0,45); buffalo_l: AUC 0,79 (khung) / 0,84 (lượt vào), TAR 0,32 tại FAR 1% | **không đạt** TAR ≥ 95% tại FAR ≤ 1%; chưa phải T1 (3 danh tính, 1 phiên) |
| Sàn trống, đầu ra "free-space" của mô hình ORG | 24/24 khung báo vật cản giả ở 0,2 m (phản chiếu) | mô hình chưa thay thế được bộ dò đã cấu hình |
| ESP32 ở VGA | 9,1-9,9 fps | giới hạn băng thông; thử SXGA ở ký túc xá |

## Rủi ro và kế hoạch còn lại cho Chương 8

1. **Mặt quá nhỏ ở vị trí đặt ESP32** (22-53 px, dưới ngưỡng 45 px của pipeline): không thể đạt TAR/FAR mục tiêu nếu giữ VGA. *Giảm thiểu:* tăng độ phân giải (SXGA gấp đôi độ rộng mặt, khoảng 2 fps), đặt gần hơn/ít nghiêng hơn, đo khoảng cách từ ESP32 đến mặt; thử với buffalo_l (AUC +0,08 đến +0,11); thử lại ở ký túc xá (kế hoạch trong `classroom_1111_pm/README.md`). Quyết định mô hình thuộc về HNHL (người phụ trách nhận thức).
2. **Khoảng cách cửa chưa tự suy ra được:** tiếp cận hiện dựa vào một giá trị thước; tam giác hóa quá lạc quan. *Giảm thiểu:* lưu quan sát từng điểm dừng, bộ ước lượng khép vòng, bắt buộc ≥ 3 marker trong tầm nhìn, đo thước ở điểm cuối; chấp nhận được nếu báo cáo ghi rõ đây là giới hạn.
3. **Chuyển động vòng hở không dự đoán được:** mọi bộ điều khiển phải đo lại sau mỗi bước (đã áp dụng cho tiếp cận cửa); hiệu chỉnh lại trên sàn lớp học.
4. **Chưa có lần chạy T2 đếm được** (tháp ESP32 chưa xong, pin dưới 11,4 V cuối buổi): cần buổi học tiếp theo với ESP32, tham chiếu bắt tay mới ở đúng vị trí đặt, người thứ hai đi vào.
5. **Pin:** 12,45 V đầu buổi tối xuống 11,35 V ở cuối buổi (dưới ngưỡng 11,4 V): phải sạc giữa các buổi.

*Các con số trên phải khớp với README gốc khi biên tập; nếu số liệu mới thay đổi (ví dụ lần chạy thử ở ký túc xá), cập nhật cả hai nơi.*
