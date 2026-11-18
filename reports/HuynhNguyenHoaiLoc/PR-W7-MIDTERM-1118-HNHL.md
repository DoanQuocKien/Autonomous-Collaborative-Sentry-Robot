# HNHL bổ sung giữa kỳ với bằng chứng sau freeze 18/11

Nguồn tower/pursuit mới cần ghi đủ coverage và lượt tránh còn dang dở khi đưa vào báo cáo. Bổ sung addendum HNHL với snapshot 12 nguồn Git, công cụ tái lập và checker. Pursuit-e có 13 triggers, 12 DONE, một active khi hết giờ, tracked 67,2%, trong dải 9,2%, căn tâm 40%. Detector vật cản tổng quát tắt, ba HOLD rows chỉ khoảng 0,14 s. Motion fit bị từ chối.

Cập nhật README, checklist và báo cáo tuần 7. Lưu review/receipts của #130/#131 đã merge và #113 đã sửa, chờ DQK review lại. Các sửa code trong review #131 đã có trên main. Candidate #113 tích hợp đạt 951 CPU/replay tests, 4 skips, 4 GPU deselected, report 14 trang/60 sources và package tái tạo được. Các số này giữ đúng phạm vi từng nhánh và commit.

Kiểm chứng addendum bằng `python -m tools.build_midterm_hnhl_nov18` và `python -m tools.check_midterm_hnhl`, đối chiếu CSV/summary/hash và các link local. Raw robot measurements từ DQK được ghi là bổ sung sau mốc 16/11. Các mục acceptance còn thiếu giữ trong checklist. Reviewers DQK và KR.
