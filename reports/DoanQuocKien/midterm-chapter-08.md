# Chương 8 — Kết quả kỳ vọng và kế hoạch còn lại

**Bản thảo DQK (2026-11-13), ngân sách 1 trang.** Nguồn: `docs/Implementation Plan.md` (mục 4.3 ngưỡng nghiệm thu, mục 5 các tuần 8–13, mục 7 rủi ro 31–34), `reports/DoanQuocKien/week-06/classroom_1111_pm/README.md`. Con số trong chương đều là một buổi đo (chưa phải nghiệm thu), trừ khi ghi khác.

---

## 8.1 Trạng thái so với ngưỡng nghiệm thu (tới 14/11)

| Hạng mục | Ngưỡng (mục 4.3) | Hiện có | Kết luận |
| :-- | :-- | :-- | :-- |
| Xác minh khuôn mặt (D2) | TAR ≥ 95 % tại FAR ≤ 1 % | clip D2 cũ (khuôn mặt 22–53 px): TAR 0,40 tại FAR 0,066 (buffalo_s, ngưỡng 0,45). Ngày 14/11 tại cửa, camera ESP32 (bản opt4), ba người (DQK, HNHL, KR) đăng ký có hướng dẫn, đứng ở 1,8 / 2,4 / 3,0 m, nhìn thẳng và quay đi sang hai bên: **TAR gộp 0,937** (822/877 khung hình nhìn thẳng; DQK 0,930, HNHL 0,983, KR 0,896), **FAR 0 trên 1754 điểm** của người lạ (0 trên 5254 khi tính cả khung hình quay đi), điểm người lạ cao nhất 0,336, ngưỡng 0,45 | **một phần**: FAR đạt, TAR 93,7 % thấp hơn ngưỡng 95 %. Điểm của người đúng và của người lạ tách nhau: ngưỡng 0,40 cho TAR 0,990 tại FAR 0/5254 (0,35: 0,998; 0,30: 1,000 tại FAR 0,27 %). Chỉ ba người, một buổi, một camera, nên đây là ứng viên chứ chưa phải kiểm chứng; ngưỡng trong mã giữ 0,45 và quyết định thuộc về HNHL. Lỗi không do kích thước mặt, góc quay đầu, khoảng cách hay phần đầu clip (chưa rõ nguyên nhân; nghi ngờ ảnh đăng ký từ webcam, chưa kiểm tra) |
| Triển khai camera cửa (T2) | tới vị trí đỗ trước cửa (1,5–3,0 m), bắt tay xác minh, lùi về STANDBY, không va chạm; 5 lần tính điểm | 6 lần tính điểm (4 lần ngày 30/10, 2 lần ngày 14/11). Ngày 14/11 cả hai lần đạt mọi tiêu chí: bắt tay 109/109 và 163/163 khung hình trong tầm nhìn, STANDBY sau 18 s và 26,6 s, khoảng cách tới cửa 2,94 m (thước), tầm nhìn thông, tường cách 0,30 và 0,45 m, 0 va chạm. Hai lần dừng cách bảng 1,55 và 1,61 m (đích 1,33 m), lệch nhau khoảng 6 cm | **đạt** (một cửa, một phòng; khoảng cách tới cửa 2,94 m gần mép trên của dải; điểm xuất phát phải cách bảng không quá khoảng 3,35 m) |
| Né vật cản trên sàn bóng | khoảng cách tới vật cản có giá trị | ghế bị phát hiện (độ tin cậy 0,95) nhưng **không có khoảng cách** (`reflection_unresolved`) trên gạch bóng, như đo 15/10 và 9/11; công cụ `explore_live` từ chối xuất phát; chưa có lần chạy né vật cản trên robot | **chưa đạt**; thử bù bằng chiều rộng hộp: một ghế, sai tối đa 0,05 m (bỏ một), 7 trên 9 ghế khác trong ±0,16 m |
| Bắt tay ESP32 | 10/10 chấp nhận, 10/10 từ chối | hai lần đạt 10/10 và 10/10, nhưng lần gần nhất chưa có biến thiên khi đặt lại camera | một phần |
| Truy bám PD | 1,2 ± 0,2 m, căn tâm ± 10 % trong 80 % thời gian | các lần chạy có giám sát đầu tiên, 43–54 % thời gian trong dải, không tính nghiệm thu | chưa đánh giá |
| Tiếp cận cửa tự động | tới vị trí đỗ 1,5–3,0 m trước cửa | 4 lần chạy tới 1,6–1,9 m (thước), 51 / 15 / 6 / 5 bước (sau khi sửa cửa sổ căn tâm), sai khoảng cách ≤ 0,05 m với số mũ 1,6 | một cửa, một ngày |
| Ước lượng vị trí cửa tự động | — | sai +11 % và +15 % (hình học yếu) | chưa có lần chạy hình học tốt |
| Cắt động cơ khi thả R1 / nút khác | dừng ngay | trung vị 7 ms (cắt), robot từ chối lệnh sau đó | chưa đo cơ học |
| Độ trễ và tải trên robot (phần mở rộng) | ≥ 20 fps, p95 ≤ 100 ms, RAM < 3 GB, GPU < 80 °C, pin ≥ 11,1 V (15 phút, có người, luồng ESP32 thật) | 13/11, có người và luồng ESP32 thật: 17,7 và 17,1 fps (60 s), 14,45 fps với p95 153 ms (600 s, người ngồi); RAM 2,13 GB, GPU tối đa 38,5 °C, pin tối thiểu 11,71 V. Không có người (16/10): 20,0 fps, p95 51–101 ms | **không đạt** (fps và p95); RAM, nhiệt độ và pin đạt; chưa chạy đủ 15 phút |

## 8.2 Kế hoạch tới hết kỳ (mỗi mục có cổng riêng, không làm gấp)

- **Tuần 7 (16–22/11):** đóng thí nghiệm giữa kỳ và đóng băng hình (16/11); bản nháp nội bộ 18/11; nộp báo cáo giữa kỳ **23/11**. Không làm tính năng mới.
- **Tuần 8–9 (23/11–6/12):** vượt vật cản khi bị tấn công (ghi đè điều khiển v = −1,0, ω = ±0,8 trong 400 ms rồi nghỉ), đo thời gian phản ứng bằng camera tốc độ cao; thử va chạm có đệm; theo đường đi đã lên kế hoạch và quét tại chỗ 360°; đo bán kính phát hiện hiệu dụng `r_det` (giá trị tạm 3,0 m).
- **Tuần 10:** tìm kiếm trên robot (lập kế hoạch → đi → quét → nhận lại), vòng đầy đủ với hai kẻ xâm nhập; ngưỡng: tìm thấy T2 ≥ 4/5, đường tìm kiếm cạn 3/3 không va chạm, vòng đầy đủ ≥ 4/5 lần không can thiệp.
- **Tuần 11–13:** tuần đệm hoàn thiện các hàng chưa đạt, kiểm tra căng (pin thấp, mất Wi-Fi, ánh sáng, phòng bừa bộn), đóng băng và diễn tập, nộp **28/12** (cửa sổ bảo vệ tới 2/1).

## 8.3 Rủi ro chính đã đo và cách giảm thiểu

1. **Khuôn mặt tại vị trí ESP32** (rủi ro 32): đo tại cửa ngày 14/11 với ba người: khuôn mặt của DQK 59–97 px ở 3,0–1,8 m (cũ 22–53 px), nên số điểm ảnh không còn là nguyên nhân. FAR bằng 0 trên 1754 điểm của người lạ, nhưng TAR gộp 0,937 ở ngưỡng 0,45 chưa tới 95 %; ngưỡng thấp hơn (0,40) cho TAR 0,990 mà FAR vẫn 0 trên số liệu này, song chỉ có ba người trong một buổi nên chưa kết luận. Còn thiếu: người lạ ngoài nhóm và đăng ký đa dạng hơn cho KR và DQK (thứ Hai 16/11); quyết định mô hình và ngưỡng thuộc về HNHL.
2. **Khoảng cách cửa chưa tự đo được** (rủi ro 33): bộ ước lượng khép vòng đã nhập nhưng chưa kiểm chứng với hình học tốt; cần phòng có ≥ 2,5 m sàn trống vuông góc với tia nhìn tới cửa và ≥ 3 marker; báo cáo nêu rõ sự phụ thuộc vào một giá trị thước.
3. **Chuyển động vòng hở không dự đoán được** (rủi ro 34): luôn đo lại sau mỗi bước, hiệu chỉnh lại trên sàn lớp, giữ quy tắc chỗ trống đã đo.
4. **Lần chạy T2 tính điểm:** đã có ngày 14/11 (hai lần đạt, xem 8.1). Ba lần thử đầu ngày không tính: hai lần dừng vì thả R1 sau khi robot dừng 4–5 s, một lần xuất phát cách bảng 3,54 m nên marker mất khi robot di chuyển (tìm thấy 1 trong 43 khung hình đầu) và vượt thời gian tiếp cận. Hai bài học: giữ R1 tới hai tiếng bíp (ít nhất 10 s sau lời nhắc) và xuất phát cách bảng không quá khoảng 3,35 m; kiểm tra khung hình ESP32 (tháp hướng đúng cửa) trước mỗi lần chạy.
5. **Pin và sạc:** 12,4 V đầu buổi, 11,4–11,6 V sau vài lần chạy; sạc giữa các buổi.
6. **Né vật cản trên sàn gạch bóng:** khoảng cách từ điểm tiếp đất không giải được (phản chiếu), nên robot chỉ quay tránh theo vị trí hộp trong ảnh; chưa có mô hình sẵn nào đạt ±0,15 m (năm bộ phát hiện/phân đoạn và năm mô hình độ sâu đã thử). Hướng đang thử: khoảng cách từ chiều rộng hộp của ghế (độ rộng 139 → 61 px từ 0,9 → 2,4 m), cần thêm nhiều loại ghế và góc nhìn, đánh giá bởi HNHL.
7. **Dữ liệu cá nhân trong lịch sử git:** gói D2_1028.zip chứa khuôn mặt của ba thành viên; mật khẩu nằm ngay trong kho nên gói thực chất không được bảo vệ. **Quyết định của nhóm ngày 13/11, cả ba thành viên đồng ý: giữ gói trong kho**; rủi ro này được chấp nhận và nêu rõ ở đây.

**Nguyên tắc báo cáo:** hạng mục nào chưa chạy ổn đến ngày đóng băng thì ghi là "đang thực hiện" kèm kế hoạch, không vội chạy cho kịp.
