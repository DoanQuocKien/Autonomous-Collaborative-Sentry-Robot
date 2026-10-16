# HNHL tuần 2 — bàn giao trạng thái

## Phiên mới nhất: 2026-10-17 — issue #43

Đã đọc GitHub issue/comment bằng API với credential Git hiện có; chỉ đọc, không đăng comment/đóng issue. Issue mở giao HNHL là #43. Đã fast-forward branch W2 tới origin/main b7d19be rồi tạo branch `HuynhNguyenHoaiLoc/w02-issue43-obstacles`. HNHL đã yêu cầu commit/push nhánh này sau khi xem kết quả; khi tiếp tục, kiểm tra git status/log/upstream để xác định trạng thái thực tế.

Đã thêm floor.py (local SegFormer-B0/ADE20K, semantic non-floor proposals và image-edge contact), world.py (offline prompt-bound YOLO-World + tiled floor crops/NMS), optional requirements, pinned tools.fetch_floor_model, tools.bench_obstacles, CLI flags/source exports, CPU/GPU tests. Cả hai backend mới mặc định tắt; bật --semantic-floor và --open-vocabulary. Không đổi motor/controller hoặc tự suy ra map FREE.

Private ZIP 15/10 có tại Downloads và đã giải nén an toàn trong data/dqk-obstacles-2026-10-15. Private boxes tại data/issue43/mixed_boxes.json, ảnh/overlay thử nghiệm trong data/issue43; không stage các file này. Weights SegFormer và bound World ở data/models, CLIP cache ở weights/clip, tất cả gitignored. requirements-floor.txt/runtime Transformers4.57.1, requirements-world.txt chỉ cho chuẩn bị vocabulary; CUDA torch giữ nguyên.

Kết quả cuối: 360 CPU passed, 2 data skips, 2 deselected; 2 GPU passed (network blocked trong inference), check_env ALL GOOD. pip check có cảnh báo tên requirement onnxruntime của InsightFace vì đã dùng onnxruntime-gpu theo Setup, không cài thêm CPU package. JSON/logs ở reports/HuynhNguyenHoaiLoc/week-02/issue-43.

Ghế 86 frames: baseline distance 0/9; semantic 8/9, còn ID21 border-truncated. Held-out chairs_c 3/3 có estimate, median/p90 5.37/17.11%; chưa formal T1. Mixed259frames: all80 detects7/15 (stable2); hybrid12/15 (stable10), distance10/15 (stable6), median/p9011.27/27.80%. Charger10, stand13, phone15 vẫn missed; vài ID có detection nhưng không có distance ổn định. FPS semantic/hybrid11.45/7.80 trên RTX5060, không thay RTX4050 hoặc 20FPS target. Issue chưa đủ để đóng; cần reviewed dense labels/false-positive eval, matte/rugged images, pitch validation và optimization/HIL.

Đọc **ISSUE-43-HNHL.md** và **PR-I43-HNHL.md** khi tiếp tục. Không dùng chữ Closes #43 trong PR; hiện Refs #43. Nội dung dưới đây là bàn giao lịch sử phiên 12/10.

Cập nhật 2026-10-12, Asia/Bangkok, sau yêu cầu kiểm tra code DQK vừa merge.

Nhánh HuynhNguyenHoaiLoc/w02-obstacles-map-vantage đã fast-forward an toàn tới 8d8aeaa, cùng origin/main khi kiểm tra. Upstream vẫn origin/HuynhNguyenHoaiLoc/w02-obstacles-map-vantage. W2 ban đầu đã merge PR #27. DQK camera pose/entrance và KR localization đã có local. Merge --ff-only --autostash giữ đầy đủ sửa đổi chưa commit, không có conflict. Chưa commit/push sửa đổi bổ sung.

Đã sửa forward tape metric, session pose thiếu passed flag có tape/fit evidence, reflection contact/abstention, all-border rejection, glossy/matte metrics, map exclusion cho lateral chưa xác nhận, tool single-image. Helper cửa KR không giả định range 2 m. Tests xác nhận RobotPose qua prescan/map có camera offset và locked pose.

Kiểm chứng mới: 321 passed, 2 skipped (checkerboard D1 + entrance D1), 1 deselected, 27,44 s; GPU 1 passed, 5,06 s. Smoke CUDA FP32 RTX5060 p50 16,519 ms / p95 23,125 ms, 3 warmup/10 samples, floor unknown. Logs tests_merged_final.txt, tests_gpu_merged_final.txt, inference_merged_final.json/.txt. Logs trước merge giữ và ghi rõ phiên cũ. XFeat weights tải đúng pinned hash tại weights/xfeat.pt (gitignored), real warped-reference test đạt. Chưa tải/cache DINOv2 hoặc D1 entrance.

ZIP DQK riêng ở data/dqk-obstacles-2026-10-12 (gitignored): setup1 5 nhãn, locked pose H=.100/pitch=-2.33, ảnh/raw/manual ROI giữ riêng. Aggregate public dqk_setup1_diagnostic.json: 3 manual ROIs, corrected median/p90 5.99/9.52%, chưa formal T1; YOLO valid ground 1 candidate. Không stage ảnh/ROI/weights/.venv/settings. Matte, ≥20 IDs, world truth/poses và hardware còn thiếu. Lateral ghế phải chưa xác nhận không chấm map.

Tài liệu: week-02.md, W2-USAGE.md, PR-W2-HNHL.md trong reports/HuynhNguyenHoaiLoc. Giữ forward tape, same-K undistort, pose theo session, floor unknown abstention. TiltFilter DQK có nhưng chưa nối detector từng frame. Marker correction/odometry cần xác nhận gốc pose/camera offset ngoài thực tế. Range cửa không suy ra từ bearing.

Khi tiếp tục: đọc git status và tài liệu, giữ uncommitted changes. Chỉ kiểm thử lại khi có code/dependency/data mới cần kiểm chứng. Có D1 matte/nhãn/world pose thì chạy evaluator; không dựng số liệu PASS. T1/T2 robot và DQK review còn chờ. Không tự gửi motor commands hoặc push main. Nếu user yêu cầu push, dùng branch W2.

Workspace C:/Users/Hoai Loc/Desktop/ROBOT/Autonomous-Collaborative-Sentry-Robot; PowerShell; .venv/Scripts/python.exe. YOLO_CONFIG_DIR=data/ultralytics. Không spawn agent/tạo goal. Shell dùng require_escalated do helper sandbox trong phiên; không có auto-review rejection.
