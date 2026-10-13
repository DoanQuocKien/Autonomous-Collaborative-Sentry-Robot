# HNHL W2: session camera pose, reflection contact and merged-module integration

## Mục tiêu và thay đổi

Tape DQK là forward từ điểm dưới lens, còn evaluator cũ dùng planar range. Bbox sàn bóng cũng có thể chứa phản chiếu khiến khoảng cách bị ngắn. Bản bổ sung sau PR #27 sửa phép chấm và chỉ đưa contact đã xử lý vào map.

- Pose/floor theo session; hỗ trợ file lớp học H=0,100 m, pitch=−2,33° có tape/fit evidence nhưng không có `passed`. Undistort giữ K của phép đo DQK.
- Reject bbox cắt mọi mép. Glossy dùng contact đối xứng phản chiếu kiểm tra texture/peak; không rõ thì unresolved. `flat_on_floor` cần caller xác nhận; floor mặc định unknown.
- Evaluator dùng `forward_m` / `tape_forward_m`, tách glossy/matte, báo ID thiếu. World truth optional cho forward-only; lateral chưa xác nhận không chấm map.
- Single-image/replay CLI nhận explicit pose/floor, xuất session/contact/rejection. Manual ROI chỉ là diagnostic hình học; raw D1 giữ trong data được Git ignore.
- Tích hợp camera pose DQK và RobotPose KR với prescan/map/camera offset. Helper tọa độ cửa yêu cầu range đo được; bearing đơn lẻ không mặc định cửa ở 2 m.
- Giữ grid UNKNOWN/FREE/OCCUPIED, confirmed-floor rays, clearance/LOS/reachability và vantage 1,5–3 m. Không gửi motor commands.

## Kiểm chứng — 2026-10-12

Sau fast-forward W2 từ `318736f` tới `origin/main` **`8d8aeaa`** (gồm PR #32 DQK và #33 KR):

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-w2-merged-final -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m tools.check_w2 --out reports/HuynhNguyenHoaiLoc/week-02/inference_merged_final.json
.venv/Scripts/python.exe -m pytest tests/test_w2_gpu.py --basetemp=data/pytest-w2-merged-gpu -p no:cacheprovider -q
```

- **321 passed**, 2 skipped (checkerboard và entrance replay D1 thiếu), 1 GPU test deselected; 27,44 s.
- GPU **1 passed**, 5,06 s; YOLOv8n actual CUDA FP32 trên RTX 5060 Laptop.
- Smoke 3 warmup/10 mẫu: p50 16,519 ms, p95 23,125 ms; ảnh/pose cũ đã commit, floor unknown. Chưa gồm map/vantage/transport; chưa thay RTX 4050 benchmark hoặc T1 accuracy.
- XFeat weights khớp pinned SHA256; real warped-reference test đạt. Import package exports và AST Python 3.6 common/jetson đạt.

[Báo cáo](week-02.md), [Protocol/API](W2-USAGE.md), [CPU log](week-02/tests_merged_final.txt), [GPU log](week-02/tests_gpu_merged_final.txt), [smoke JSON](week-02/inference_merged_final.json).

## Giới hạn và nghiệm thu tiếp theo

Diagnostic 3 manual ROIs glossy có median/p90 5,99%/9,52%, ngưỡng khảo sát trên chính ảnh đó. Không claim detector accuracy hoặc T1 PASS; YOLO chỉ có 1 valid ground candidate. Chờ ≥20 IDs, matte, confirmed world truth/pose, footprint/camera offset và robot. DINOv2 và live tilt vào obstacle detector chưa chạy/tích hợp trong bản này. Seen-floor vẫn cần xác nhận độc lập.

T2: 0 collisions trong 5×3 phút, vantage đủ 3 điều kiện 5/5 còn chờ robot. Raw ảnh/ROI riêng không nằm trong PR.

Branch `HuynhNguyenHoaiLoc/w02-obstacles-map-vantage`; base PR bổ sung `8d8aeaa`; reviewer **DQK**. Sửa đổi bổ sung chưa commit/push trong phiên kiểm tra.
