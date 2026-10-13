# HNHL tuần 2 — bàn giao trạng thái

Cập nhật 2026-10-12, Asia/Bangkok, sau yêu cầu kiểm tra code DQK vừa merge.

Nhánh HuynhNguyenHoaiLoc/w02-obstacles-map-vantage đã fast-forward an toàn tới 8d8aeaa, cùng origin/main khi kiểm tra. Upstream vẫn origin/HuynhNguyenHoaiLoc/w02-obstacles-map-vantage. W2 ban đầu đã merge PR #27. DQK camera pose/entrance và KR localization đã có local. Merge --ff-only --autostash giữ đầy đủ sửa đổi chưa commit, không có conflict. Chưa commit/push sửa đổi bổ sung.

Đã sửa forward tape metric, session pose thiếu passed flag có tape/fit evidence, reflection contact/abstention, all-border rejection, glossy/matte metrics, map exclusion cho lateral chưa xác nhận, tool single-image. Helper cửa KR không giả định range 2 m. Tests xác nhận RobotPose qua prescan/map có camera offset và locked pose.

Kiểm chứng mới: 321 passed, 2 skipped (checkerboard D1 + entrance D1), 1 deselected, 27,44 s; GPU 1 passed, 5,06 s. Smoke CUDA FP32 RTX5060 p50 16,519 ms / p95 23,125 ms, 3 warmup/10 samples, floor unknown. Logs tests_merged_final.txt, tests_gpu_merged_final.txt, inference_merged_final.json/.txt. Logs trước merge giữ và ghi rõ phiên cũ. XFeat weights tải đúng pinned hash tại weights/xfeat.pt (gitignored), real warped-reference test đạt. Chưa tải/cache DINOv2 hoặc D1 entrance.

ZIP DQK riêng ở data/dqk-obstacles-2026-10-12 (gitignored): setup1 5 nhãn, locked pose H=.100/pitch=-2.33, ảnh/raw/manual ROI giữ riêng. Aggregate public dqk_setup1_diagnostic.json: 3 manual ROIs, corrected median/p90 5.99/9.52%, chưa formal T1; YOLO valid ground 1 candidate. Không stage ảnh/ROI/weights/.venv/settings. Matte, ≥20 IDs, world truth/poses và hardware còn thiếu. Lateral ghế phải chưa xác nhận không chấm map.

Tài liệu: week-02.md, W2-USAGE.md, PR-W2-HNHL.md trong reports/HuynhNguyenHoaiLoc. Giữ forward tape, same-K undistort, pose theo session, floor unknown abstention. TiltFilter DQK có nhưng chưa nối detector từng frame. Marker correction/odometry cần xác nhận gốc pose/camera offset ngoài thực tế. Range cửa không suy ra từ bearing.

Khi tiếp tục: đọc git status và tài liệu, giữ uncommitted changes. Chỉ kiểm thử lại khi có code/dependency/data mới cần kiểm chứng. Có D1 matte/nhãn/world pose thì chạy evaluator; không dựng số liệu PASS. T1/T2 robot và DQK review còn chờ. Không tự gửi motor commands hoặc push main. Nếu user yêu cầu push, dùng branch W2.

Workspace C:/Users/Hoai Loc/Desktop/ROBOT/Autonomous-Collaborative-Sentry-Robot; PowerShell; .venv/Scripts/python.exe. YOLO_CONFIG_DIR=data/ultralytics. Không spawn agent/tạo goal. Shell dùng require_escalated do helper sandbox trong phiên; không có auto-review rejection.
