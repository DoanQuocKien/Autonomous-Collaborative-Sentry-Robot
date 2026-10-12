# HNHL — Báo cáo tuần 2: vật cản, bản đồ, vị trí quan sát

Kiểm chứng **2026-10-12**, Asia/Bangkok. Nhánh `HuynhNguyenHoaiLoc/w02-obstacles-map-vantage`, base `6dbf79a`. Phần triển khai laptop và kiểm thử local hoàn thành; T1 D1/T2 robot còn chờ. Chưa commit/push trong phiên này.

## Triển khai

| Hạng mục | Kết quả |
| :-- | :-- |
| `perception/obstacle.py` | YOLO furniture trên ảnh undistort; ground projection pitch/roll; repulsive w; giữ bbox không đo được dưới dạng rejection |
| `nav/gridmap.py` | World grid UNKNOWN/FREE/OCCUPIED; pose+camera offset; confirmed-floor rays có occlusion; NPZ metadata/guarding pose |
| `nav/vantage.py` | Ô FREE reachable có clearance, LOS tới cửa, distance1,5–3 m; ưu tiên boundary đã quan sát |
| Offline | `PreScanner`, `tools.prescan_replay`; dùng cùng detector với live, bắt buộc pose mỗi frame |
| T1 tooling | `tools.evaluate_w2`; matched annotations, distance median/p90, ID thiếu, map errors; thiếu dữ liệu không tạo PASS |
| GPU tooling | `tools.check_w2`; YOLO thật, kiểm tra actual CUDA/FP32, versions/hashes/latency |

CameraGeometry giữ rectified K bằng K gốc, thống nhất `tools.measure_camera_pose` của DQK. Camera cao0,1013 m, nghiêng xuống2,63°, roll0°. Khi camera ngang, tâm ảnh trả `forward=fy*H/(v-cy)`; output có forward/left và planar range riêng.

FREE chỉ có từ footprint đã đi hoặc `seen_floor` do caller xác nhận. Không suy ra free floor từ YOLO absence; occupied không bị floor rays xóa. UNKNOWN chặn travel/LOS. Đã sửa sai số số thực trên mép ô và ray corner/boundary traversal. Vantage nhận world door location cùng robot pose, không dùng bearing đơn lẻ làm vị trí cửa.

## Kiểm chứng

Python3.12.15, OpenCV5.0.0, torch2.9.1+cu128, Ultralytics8.4.172, CUDA12.8, **RTX5060 Laptop GPU**. Máy HNHL không thay baseline RTX4050 target.

```powershell
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-w2-final -p no:cacheprovider -q -rs
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
.venv/Scripts/python.exe -m tools.check_w2 --out reports/HuynhNguyenHoaiLoc/week-02/inference_smoke.json
.venv/Scripts/python.exe -m pytest tests/test_w2_gpu.py --basetemp=data/pytest-w2-gpu-release -p no:cacheprovider -q
```

| Kiểm tra | Kết quả |
| :-- | :-- |
| CPU/transport regression | **257 passed**,1 skipped,1 deselected, **12,43 s** |
| Skip | Ca hiệu chuẩn thật cần `data/D1/checkerboard`, chưa có local |
| Kiểm thử mới | **60 CPU tests +1 GPU test**, gồm các ca tham số hóa |
| GPU test | **1 passed**, **3,73 s**, `cuda:0`, FP32 |
| Detector smoke | 3 warmup/10 mẫu; p50 **7,722 ms**, p95 **8,157 ms** |
| CLI/whitespace | Help các CLI hoạt động; `git diff --check` đạt |

Bằng chứng: [CPU log](week-02/tests_cpu.txt), [GPU log](week-02/tests_gpu.txt), [Inference JSON](week-02/inference_smoke.json), [stdout](week-02/inference_smoke.txt).

T0 kiểm tra projection bằng phép chiếu thuận độc lập (ngang/nghiêng/roll); horizon và calibration/input invalid; filtering/rejection/repulsion; pose/offset; unknown/occlusion; ray corner/boundary/reversal; clearance/connectivity; save/load; vantage; synthetic recording seq reset/pose join; evaluator pass/fail/missing labels.

Smoke dùng ảnh raw camera-pose đã có trong repo, ghi hashes weights/image/config/calibration và actual device. Latency chỉ gồm undistort+YOLO preprocessing/inference/postprocessing+projection, chưa gồm map/vantage, transport hay motor. 10 mẫu là smoke runtime, chưa phải benchmark ổn định hoặc bằng chứng accuracy. Không có motor commands.

## Nghiệm thu còn chờ

| Tiêu chí | Trạng thái |
| :-- | :-- |
| T1 distance median<=10%,p90<=20% ở0,3–2 m | Chờ D1+tape labels |
| T1 map >=80% của20 obstacles trong20 cm | Chờ world truth+pose |
| T2 repulsion 0 collisions trong5×3 phút | Chờ robot DQK |
| T2 vantage đủ3 điều kiện5/5 | Chờ KR entrance/localization+robot |

Máy chưa có raw D1/nhãn thật; base main chưa có KR localization/entrance. `motion.json` đã có nhưng không thay localization poses. Phải đo footprint/camera offset theo gốc pose KR. `seen_floor` là input xác nhận, chưa có automatic floor segmentation. Map extent cố định, occupied persists; không suy ra coverage toàn phòng.

Evaluator distance dùng planar range từ dưới lens, median theo ID trước khi lấy median/p90, ít nhất20 IDs và mỗi ID có estimate. Map dùng nearest occupied cell centre, chưa đánh giá precision/recall. Protocol/API: [W2-USAGE.md](W2-USAGE.md). Nội dung PR: [PR-W2-HNHL.md](PR-W2-HNHL.md), reviewer DQK. Definition of Done toàn bộ còn cần T1/T2 và PR review/merge.
