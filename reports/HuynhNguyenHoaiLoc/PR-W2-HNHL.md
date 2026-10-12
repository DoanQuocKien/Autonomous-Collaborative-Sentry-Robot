# HNHL W2: calibrated obstacle perception, room map and vantage selection

## Mục tiêu

Triển khai phần laptop tuần2 của HNHL: nhận diện furniture/ground distance với camera hiệu chuẩn, occupancy grid world frame và vị trí quan sát cửa. Các module chạy offline bằng replay và nhận pose/entrance từ KR khi tích hợp.

## Thay đổi

- `CameraGeometry` undistort với cùng K của phép đo DQK, ground projection có pitch/roll. Camera H_cam0,1013 m, pitch xuống2,63°; trả forward/left, planar range và bearing positive-left.
- `ObstacleDetector(frame_bgr,t)` trả dataclass; YOLO furniture, thresholds cấu hình, weights local, FP32. Box cắt đáy/không có ground intersection giữ unresolved. Repulsive w chuẩn hóa dùng0,6 m exploration/0,5 m pursuit, quay tránh phía vật cản.
- `OccupancyGrid` UNKNOWN/FREE/OCCUPIED; pose+camera offset; chỉ clear footprint/seen-floor xác nhận. Rays có occlusion, UNKNOWN chặn navigation. Xử lý corner/boundary và sai số số thực biên ô. Atomic NPZ save/load không pickle, có guarding pose/quy ước tọa độ.
- `VantageSelector` chỉ xét FREE reachable với footprint clearance, LOS, cách cửa1,5–3 m, ưu tiên boundary quan sát. Trả None khi chưa đủ điều kiện.
- `PreScanner`, replay export, evaluator T1 báo ID thiếu, GPU smoke kiểm tra CUDA/FP32 và hashes. Không gửi motor commands.
- Thêm config, **60 CPU tests +1 GPU test**. PR/docs/evidence đặt trong `reports/HuynhNguyenHoaiLoc`.

## Kiểm chứng — 2026-10-12

```powershell
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-w2-final -p no:cacheprovider -q -rs
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
.venv/Scripts/python.exe -m tools.check_w2 --out reports/HuynhNguyenHoaiLoc/week-02/inference_smoke.json
.venv/Scripts/python.exe -m pytest tests/test_w2_gpu.py --basetemp=data/pytest-w2-gpu-release -p no:cacheprovider -q
```

- CPU/transport: **257 passed**,1 skipped (D1 checkerboard thiếu),1 GPU test deselected,12,43 s.
- GPU: **1 passed**,3,73 s; YOLOv8n thực thi `cuda:0`, FP32 trên RTX5060 Laptop GPU.
- Detector smoke: 3 warmup/10 mẫu trên ảnh camera-pose raw đã commit; p50 **7,722 ms**,p95 **8,157 ms**. Chưa gồm mapping/transport; không thay baseline RTX4050 hoặc T1D1.
- CLI help và `git diff --check` đạt.

Báo cáo: `reports/HuynhNguyenHoaiLoc/week-02.md`. API/protocol: `reports/HuynhNguyenHoaiLoc/W2-USAGE.md`. Logs/JSON: `reports/HuynhNguyenHoaiLoc/week-02/`.

## Tích hợp tiếp theo

- KR cung cấp pose đồng thời frame và tọa độ cửa world; DQK xác nhận footprint/camera offset, controller xử lý unresolved/nearest.
- Nhận D1+tape/world labels để đo median/p90 distance và80% map trong20 cm. Synthetic không thay dữ liệu thật.
- T2 robot:0 collisions trong5×3 phút; vantage đủ3 điều kiện5/5. Chưa chạy các phép này.
- Seen-floor là input xác nhận; không suy ra free floor từ YOLO absence. UNKNOWN có thể khiến chưa có vantage khi dữ liệu phòng chưa đủ.

Branch `HuynhNguyenHoaiLoc/w02-obstacles-map-vantage`; base `6dbf79a`; reviewer theo rotation: **DQK**.
