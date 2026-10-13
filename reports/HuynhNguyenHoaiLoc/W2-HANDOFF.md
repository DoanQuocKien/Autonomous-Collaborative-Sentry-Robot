# HNHL tuần 2 — trạng thái cuối phiên

Cập nhật 2026-10-12 (Asia/Bangkok). Người dùng đã nhắn “Tiếp tục”; phần triển khai và kiểm chứng local hoàn thành. Nhánh HuynhNguyenHoaiLoc/w02-obstacles-map-vantage, base/HEAD chưa commit 6dbf79a. Chưa commit/push hoặc tạo PR GitHub.

Đã hoàn thành CameraGeometry, ObstacleDetector, OccupancyGrid, VantageSelector, PreScanner; tools replay/evaluate/GPU smoke; config và tests. 257 CPU/transport tests passed, 1 skipped (D1 checkerboard thiếu), 1 deselected (GPU); 1 GPU test passed. Smoke RTX5060 cuda:0 FP32: p50 7,722 ms / p95 8,157 ms, 3 warmup / 10 mẫu.

Tài liệu chính để đọc khi tiếp tục:
- reports/HuynhNguyenHoaiLoc/week-02.md: báo cáo/kết quả/giới hạn.
- reports/HuynhNguyenHoaiLoc/W2-USAGE.md: coordinate contracts, APIs, replay và annotations.
- reports/HuynhNguyenHoaiLoc/PR-W2-HNHL.md: nội dung PR theo thư mục người dùng yêu cầu.
- reports/HuynhNguyenHoaiLoc/week-02/: logs CPU/GPU và inference JSON.

Còn chờ bên ngoài: D1 raw +20 obstacles có tape/world truth; KR localization/entrance; đo footprint/camera offset; T2 robot với DQK; review/merge PR. Không claim Definition of Done toàn bộ hoặc T1/T2 đã đạt.

Khi tiếp tục: giữ thay đổi chưa commit, đọc báo cáo/usage và git status. Nếu có D1 thì chạy replay/evaluator; nếu sửa code/thresholds thì kiểm chứng lại phần tương ứng và cập nhật evidence. Nếu người dùng yêu cầu push branch, lưu ý upstream hiện origin/main nên dùng git push -u origin HEAD. Không tự chạy motor hoặc đưa raw D1 lên repo public.

Workspace C:/Users/Hoai Loc/Desktop/ROBOT/Autonomous-Collaborative-Sentry-Robot, PowerShell, .venv/Scripts/python.exe. Shell calls dùng require_escalated do helper sandbox trong session; apply_patch được; không có approval rejection. Không spawn agents/tạo goal. YOLO_CONFIG_DIR nên trỏ data/ultralytics và thư mục tồn tại trước import. Settings phát sinh từ GPU test đầu đã chuyển từ root vào data/w2-generated-ultralytics-settings (gitignored); không stage models/settings/venv. Các file đang thay đổi là config.toml, sentry/nav, sentry/perception, tools/check_w2.py, tools/evaluate_w2.py, tools/prescan_replay.py, 5 tests mới và tài liệu/evidence W2.
