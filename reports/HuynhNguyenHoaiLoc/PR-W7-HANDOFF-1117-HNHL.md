# HNHL chuẩn hóa whitelist và bàn giao giữa kỳ 17/11

Ví dụ enrol Phase 2 lưu ID vào `data/door-whitelist`, trong khi ví dụ monitor/replay đọc thư mục khác. Cập nhật các lệnh đọc cùng thư mục, giúp lượt chạy dùng đúng các ID vừa enrol.

Bổ sung bàn giao Chương 5/7 và phụ lục cho draft 18/11, hướng dẫn fold whitelist, overlay, nhãn entry và evaluator cho cảnh Phase 2 ngày 19/11. Checklist dùng lịch video 19–22/11 đã được nhóm quyết định. Snapshot GitHub xác nhận #128 đã merge sau review DQK và #113 còn cùng các finding xóa dữ liệu.

Kiểm chứng trên main `46dc0e4` bằng `tools.check_midterm_hnhl`, đối chiếu các snapshot số liệu/hash và liên kết local. `--help` của `tools.monitor_door`, `tools.analyse_door_run` và `tools.evaluate_door_entries` chạy thành công. Nguồn kiểm thử CPU được dẫn về lượt 16/11 ở `4970a74`, 882 passed, 2 skipped, 4 GPU deselected. Các bước live trong tài liệu dành cho buổi 19/11.

Reviewers DQK và KR. [Bàn giao](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/blob/HuynhNguyenHoaiLoc/w07-midterm-handoff-1117/reports/HuynhNguyenHoaiLoc/midterm/update-2026-11-17.md), [snapshot GitHub](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/blob/HuynhNguyenHoaiLoc/w07-midterm-handoff-1117/reports/HuynhNguyenHoaiLoc/midterm/github-check-2026-11-17.json), [checker](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/blob/HuynhNguyenHoaiLoc/w07-midterm-handoff-1117/reports/HuynhNguyenHoaiLoc/week-07/review-2026-11-17/midterm_check.json).
