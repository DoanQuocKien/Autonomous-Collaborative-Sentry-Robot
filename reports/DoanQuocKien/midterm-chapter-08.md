# Chương 8 — Kết quả kỳ vọng và kế hoạch còn lại

**Bản thảo DQK (2026-11-12), ngân sách 1 trang.** Nguồn: `docs/Implementation Plan.md` (mục 4.3 ngưỡng nghiệm thu, mục 5 các tuần 8–13, mục 7 rủi ro 31–34), `reports/DoanQuocKien/week-06/classroom_1111_pm/README.md`. Con số trong chương đều là một buổi đo (chưa phải nghiệm thu), trừ khi ghi khác.

---

## 8.1 Trạng thái so với ngưỡng nghiệm thu (tới 12/11)

| Hạng mục | Ngưỡng (mục 4.3) | Hiện có | Kết luận |
| :-- | :-- | :-- | :-- |
| Xác minh khuôn mặt (D2) | TAR ≥ 95 % tại FAR ≤ 1 % | tại cửa lớp học (khuôn mặt 22–53 px) TAR 0,40 tại FAR 0,066 (buffalo_s, ngưỡng 0,45); buffalo_l: TAR 0,32 tại FAR 1 % (mức khung hình) | **chưa đạt**; nguyên nhân chính là số điểm ảnh của khuôn mặt |
| Bắt tay ESP32 | 10/10 chấp nhận, 10/10 từ chối | hai lần đạt 10/10 và 10/10, nhưng lần gần nhất chưa có biến thiên khi đặt lại camera | một phần |
| Truy bám PD | 1,2 ± 0,2 m, căn tâm ± 10 % trong 80 % thời gian | các lần chạy có giám sát đầu tiên, 43–54 % thời gian trong dải, không tính nghiệm thu | chưa đánh giá |
| Tiếp cận cửa tự động | tới vị trí đỗ 1,5–3,0 m trước cửa | 4 lần chạy tới 1,6–1,9 m (thước), 51 / 15 / 6 / 5 bước (sau khi sửa cửa sổ căn tâm), sai khoảng cách ≤ 0,05 m với số mũ 1,6 | một cửa, một ngày |
| Ước lượng vị trí cửa tự động | — | sai +11 % và +15 % (hình học yếu) | chưa có lần chạy hình học tốt |
| Cắt động cơ khi thả R1 / nút khác | dừng ngay | trung vị 7 ms (cắt), robot từ chối lệnh sau đó | chưa đo cơ học |

## 8.2 Kế hoạch tới hết kỳ (mỗi mục có cổng riêng, không làm gấp)

- **Tuần 7 (16–22/11):** đóng thí nghiệm giữa kỳ và đóng băng hình (16/11); bản nháp nội bộ 18/11; nộp báo cáo giữa kỳ **23/11**. Không làm tính năng mới.
- **Tuần 8–9 (23/11–6/12):** vượt vật cản khi bị tấn công (ghi đè điều khiển v = −1,0, ω = ±0,8 trong 400 ms rồi nghỉ), đo thời gian phản ứng bằng camera tốc độ cao; thử va chạm có đệm; theo đường đi đã lên kế hoạch và quét tại chỗ 360°; đo bán kính phát hiện hiệu dụng `r_det` (giá trị tạm 3,0 m).
- **Tuần 10:** tìm kiếm trên robot (lập kế hoạch → đi → quét → nhận lại), vòng đầy đủ với hai kẻ xâm nhập; ngưỡng: tìm thấy T2 ≥ 4/5, đường tìm kiếm cạn 3/3 không va chạm, vòng đầy đủ ≥ 4/5 lần không can thiệp.
- **Tuần 11–13:** tuần đệm hoàn thiện các hàng chưa đạt, kiểm tra căng (pin thấp, mất Wi-Fi, ánh sáng, phòng bừa bộn), đóng băng và diễn tập, nộp **28/12** (cửa sổ bảo vệ tới 2/1).

## 8.3 Rủi ro chính đã đo và cách giảm thiểu

1. **Khuôn mặt quá nhỏ tại vị trí ESP32** (rủi ro 32): tăng độ phân giải hoặc cắt cảm biến (bản opt4: khoảng 77 px ở 2,1 m trên bàn thử), đặt gần/ít nghiêng hơn, thử buffalo_l (AUC khung hình 0,79 thay vì 0,71), thử lại tại cửa; quyết định mô hình thuộc về HNHL.
2. **Khoảng cách cửa chưa tự đo được** (rủi ro 33): bộ ước lượng khép vòng đã nhập nhưng chưa kiểm chứng với hình học tốt; cần phòng có ≥ 2,5 m sàn trống vuông góc với tia nhìn tới cửa và ≥ 3 marker; báo cáo nêu rõ sự phụ thuộc vào một giá trị thước.
3. **Chuyển động vòng hở không dự đoán được** (rủi ro 34): luôn đo lại sau mỗi bước, hiệu chỉnh lại trên sàn lớp, giữ quy tắc chỗ trống đã đo.
4. **Chưa có lần chạy T2 tính điểm** (ESP32 trên tháp chưa xong ở các buổi gần đây, pin dưới 11,4 V cuối buổi): cần buổi có ESP32 trên tháp, tham chiếu bắt tay đặt đúng vị trí, người thứ hai đi vào.
5. **Pin và sạc:** 12,4 V đầu buổi, 11,4–11,6 V sau vài lần chạy; sạc giữa các buổi.
6. **Dữ liệu cá nhân trong lịch sử git:** gói D2_1028.zip (khuôn mặt của ba thành viên, mã hóa bằng mật khẩu nằm ngay trong kho) phải được gỡ khỏi lịch sử hoặc không nộp cùng báo cáo trước khi kho được chuyển cho người chấm.

**Nguyên tắc báo cáo:** hạng mục nào chưa chạy ổn đến ngày đóng băng thì ghi là "đang thực hiện" kèm kế hoạch, không vội chạy cho kịp.
