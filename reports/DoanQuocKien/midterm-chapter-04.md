# Chương 4 — Nền tảng robot và hiệu chỉnh

**Bản thảo DQK (2026-11-12), ngân sách 1,5 trang; phần định vị ArUco/dead reckoning do KR phụ trách cùng.** Số liệu: `calib/`, `reports/DoanQuocKien/week-02/`, `week-06/classroom_1111_pm/README.md`. Hình: F4 (lỗi fisheye), F5 (góc nghiêng camera theo buổi), F6 (mô hình chuyển động), F22 (độ lệch khi chạy thẳng).

---

## 4.1 Camera fisheye

Camera IMX219 góc 160° gắn thấp (ống kính cách sàn **0,100 m**, cố định theo thước, không bao giờ được "khớp" từ dữ liệu). Chúng tôi hiệu chỉnh bằng mô hình **fisheye đẳng khoảng cách** của OpenCV (Kannala và Brandt, 2006) ngày 11/10 từ 52 ảnh bàn cờ (ô 25 mm): **RMS 0,83 px** (lần khớp đầu 1,39 px trên mọi ảnh, sau khi loại các ảnh lỗi), đạt ngưỡng 1,0 px (F4). Ảnh luôn được **hiệu chỉnh méo trước** khi tính khoảng cách mặt đất.

## 4.2 Tư thế camera và khoảng cách trên mặt đất

Khoảng cách tới một điểm trên sàn tính từ hàng ảnh với độ cao ống kính 0,100 m và góc nghiêng camera. Giá đỡ camera **có thể nghiêng** và dịch chuyển mỗi khi robot bị cầm: góc nghiêng đo được −4,1° đến −4,7° ở hầu hết các ngày, nhưng −0,64° và −13,9° trong hai lần khác, và −9,0° đến −10,4° ngày 12/11 sau khi nhấc robot và sau một cú va nhẹ; ngày 13/11 đo −9,12° ở lớp học và −3,30° ở ký túc xá sau khi robot được nhấc và chuyển chỗ (trang marker dựng thẳng đứng theo xác nhận của người vận hành, chân trang ở sàn; một góc nghiêng 1° của trang làm lệch kết quả 1°) (F5). Vì sai 1° làm lệch khoảng 15 % khoảng cách ở 1 m, **mọi buổi chạy bắt đầu bằng `self_pose`**: đo góc từ một marker ArUco dựng đứng (45 khung, độ lệch chuẩn 0,01–0,10°) và ghi tệp tư thế mới; hai lần đo liên tiếp có thể chênh khoảng 0,6° (−10,43° so với −9,79°), nên coi tư thế chính xác tới khoảng ±0,5°.

**Giới hạn đã đo:** một pixel tương ứng d² × 0,0033 / 0,100 m, tức khoảng 0,1 m ở 1,8 m và 0,2 m ở 2,4 m; đáy hộp phát hiện nằm thấp hơn chân 3–7 px, nên khoảng cách theo hàng chân chỉ dùng được tới khoảng 1,2–1,5 m. Với ba người đứng ở 1,2 / 1,8 / 2,4 m, bù 3,5 px cho sai lệch trong khoảng 0,1–0,2 m so với kỳ vọng; không bù thì thiếu 0,25–0,55 m. Cách đo bằng chiều dài thân (vai–hông, giá trị tiên nghiệm 0,50 m) không cần bù và sai trong khoảng ±0,2 m, nhưng mới là hướng thử (mỗi điểm 12 khung hình, độ lệch thấu kính 0,2–0,26 m chưa đo).

## 4.3 Mô hình chuyển động và giới hạn của chuyển động vòng hở (F6, F22)

Robot không có bộ mã hóa vòng quay (MPU6050 đã gắn ngày 1/11 nhưng hỏng, tạm hoãn). Mô hình bánh xe hiệu chỉnh ngày 15/10: tốc độ bánh = 1,64 × (|giá trị động cơ| − 0,038) m/s, khoảng cách hai bánh 0,137 m, vùng chết `min_pwm` 0,12; hệ số v là 0,4135 m/s trên đơn vị lệnh và hệ số ω là 6,48 rad/s trên đơn vị lệnh; độ lệch hướng hiệu chỉnh **−0,19 rad/m** (khoảng −11°/m, ngày 11/10).

Sai số hệ thống của truyền động vi sai đã được mô tả trong tài liệu [Borenstein và Feng, 1996]. Trên sàn gạch bóng của phòng học, ngày 11/11–12/11, độ lệch **không ổn định**: tổng hợp 13 lần chạy tiến thẳng có marker trong tầm nhìn, độ lệch hướng trên mỗi mét dao động từ **−16 đến +59°/m**; ở cùng v ≈ 0,6 là −16, −3, +10, +18, +22 và +23°/m (Hình F22). Ba đoạn chạy ở v = 0,55 lệch khoảng 12–15°/s về bên trái, gấp 5–6 lần giá trị hiệu chỉnh tháng 10 và ngược dấu; ở v = 0,85 và 1,0 độ lệch nhỏ hơn (+8 và +4°/m, mỗi mức chỉ một lần). Nguyên nhân chưa chứng minh được (sàn, pin 11,5–12 V, giá trị động cơ gần vùng chết). Tốc độ tiến cũng thay đổi theo pin và sàn: 0,21 m/s ở một lần chạy và 0,34 m/s ở lần khác (v = 0,85).

**Hệ quả thiết kế:** không tin hướng sau một đoạn chạy vòng hở; hướng được **đo lại sau mỗi lần di chuyển** từ cảm biến (cửa, marker). Pha quay tại chỗ thì ổn định: 23–27° cho mỗi xung 0,2 s, độ lệch chuẩn khoảng 2° (ba lần quét, 13–16 điểm dừng một vòng).

## 4.4 Marker ArUco và tìm cửa

Marker ArUco `DICT_4X4_50` cạnh 150 mm được phát hiện bằng bộ giải PnP vuông phân tích `SOLVEPNP_IPPE_SQUARE` (Collins và Bartoli, 2014; Garrido-Jurado và cộng sự, 2014). Từ 2–3 m trở ra marker 150 mm cho vị trí nhiễu (độ trải 0,1–0,3 m trong các lần quét). Robot quay tại chỗ từng xung nhỏ, lấy phương vị các marker (đã biết cố định) để đo góc quay của từng xung và ghi vị trí marker trong hệ tọa độ xuất phát; vì hướng là **tổng khoảng 15 góc xung**, sai số tích lũy và khép vòng cho thấy lệch −1,7° và −8,2° ở hai lần quét kiểm tra được.

Bộ phát hiện cửa chỉ cho **phương vị** (chính xác khoảng 1° so với thước), không cho khoảng cách. Tam giác hóa từ hai lần quét cách nhau khoảng 1 m cho khoảng cách dài hơn thực tế 45–72 % khi dùng trung vị phương vị. Bộ ước lượng bình phương tối thiểu có khép vòng (`tools/door_pose.py`) trong mô phỏng 300 hạt giống giảm sai số trung vị/90 % từ 8,8/35,7 % xuống 5,5/21,4 % với 2 marker, từ 6,6/18,3 % xuống 3,8/9,4 % với 3 marker. Hai lần chạy thật hình học yếu (đường nền ngắn hoặc dọc tia nhìn): sai +11 % và +15 % so với +30 % và +193 % của cách cũ, khoảng ước lượng chứa giá trị thước; **chưa có lần chạy hình học tốt** (đường nền ≥ 1,5 m vuông góc) để nêu độ chính xác.

Tiếp cận cửa dùng cách khác, không cần khoảng cách đã biết trước ngoài một giá trị thước ở lần nhìn đầu: lặp "đo cửa → quay một xung ngắn hoặc chạy một đợt 0,6 s → dừng đo lại"; khoảng cách ước lượng từ diện tích đường viền cửa theo luật lũy thừa với số mũ 1,6 (không phải 2, vì đường viền bị khung hình cắt khi cửa chiếm đầy). Kết quả thật ngày 11–12/11: bốn lần chạy, số bước 51 → 15 → 6 → 5 sau khi nới cửa sổ căn tâm từ ±4° lên ±8°; sai số khoảng cách so với thước +0,05, +0,02, **0,00 và +0,05 m** (hai lần sau là kiểm tra ngoài mẫu từ điểm xuất phát khác; cùng một cửa, một sàn).
