# HNHL chốt Chương 5 và bàn giao tuần 7

Tuần 7 (16–22/11) giao HNHL chốt Chương 5 với hình ROC, sai số khoảng cách, GPU/tối ưu và sửa lỗi còn sót tuần 5–6. Bản bàn giao này đồng nhất số liệu với báo cáo nhóm và cập nhật trạng thái sau merge #113/#132/#133.

## Thay đổi

- Chốt [Chương 5 HNHL ngày 21/11](midterm/chapter-05-final-2026-11-21.md) với F10, ROC cửa 14/11, F9, F18 và phần Nano/F20 phối hợp DQK. Có manifest hash cho văn bản và năm hình.
- Cập nhật hình ROC/F9 trong bản ghép nhóm, giữ mẫu số genuine/impostor và kết quả RTX5060/4050 riêng biệt. Nêu rõ policy confirmed-unresolved chưa enqueue, theo quyết định tạm 14/11.
- Tái lập addendum từ 38 nguồn Git pin ở `55ddfc8`: find-door, pursuit, approach, pose tháp và F7 raw clocks. STANDBY 56,317 s; pursuit distance-in-band 9,4%/18,1%. F7 đã có raw CSV nhưng chưa đạt FPS/p95.
- Bổ sung năm nguồn hình/ROC vào registry nhóm, tổng 91. Cập nhật báo cáo tuần 7, README, checklist và checker; giữ các snapshot theo ngày cùng các gate chưa nghiệm thu.
- Regression kiểm tra drift CSV/summary/state/timestamp/tape và mutable refs. Các sửa perception/handoff liên quan đã ở main qua #115/#124; không thêm tính năng perception của tuần 8.

## Kiểm chứng

Clone Git sạch tại candidate **`a798f43e8331bdd5fae53e5dafc38413af27d903`**, dùng `.venv` HNHL hiện có: **983 passed, 4 skipped, 4 GPU deselected**, 73,07 s. Các skip cần checkerboard, XFeat weights và ReportLab của môi trường pytest; không sao chép private data/weights vào clone và không xác nhận cài mới môi trường.

Render PDF riêng bằng dependencies báo cáo: bản nhóm **15 trang**, Chương 5 riêng **4 trang**, đã xem mọi trang; render hai lần có cùng bytes. Registry **91 nguồn PASS**; hai ZIP từ candidate giống bytes, 1.520 file export và audit không có forbidden paths. Các kiểm chứng này có candidate và phạm vi riêng.

[Tổng kết tuần 7](week-07.md), [clean-checkout log](week-07/review-2026-11-21/clean_checkout_pytest.log), [validation](week-07/review-2026-11-21/w7-final-validation.json), [addendum và nguồn](midterm/update-2026-11-21.md).

Không có inference, camera/motor trial hoặc accuracy benchmark mới trong PR. Full door T1, D3/gallery, D5 độc lập/per-class, F11/world truth và RTX4050 precision accuracy còn cần dữ liệu phù hợp; việc đóng #114 không chứng nhận các hàng này. Tag `midterm`, owner sign-off và video tùy chọn theo bước chốt của nhóm.

Refs #111. Reviewers: DQK và KR.
