# HNHL tuần 2 — giao diện và cách kiểm chứng

Theo Week 2 (12–18/10/2026), `docs/Implementation Plan.md`. Chạy bằng `.venv/Scripts/python.exe`. Code DQK/KR đã có sau merge PR #32/#33; xem kết quả thực tế trong [week-02.md](week-02.md).

## Camera, contact và khoảng cách

`ObstacleDetector(frame_bgr,t)` nhận **raw BGR uint8 640×480**; tự undistort cùng K gốc của `calib/camera.json`. Bbox/contact output ở ảnh rectified, không vẽ trực tiếp trên raw. Entrance XFeat/DINOv2 và localization marker nhận raw frame riêng; không dùng ảnh đã undistort của obstacle để undistort lần nữa.

Chọn pose theo session, không theo file mới nhất chung cho mọi ảnh:

| Pose | H (m) | Pitch down (deg) | Sử dụng |
| :-- | --: | --: | :-- |
| camera_pose_nowedge.json | 0,1013 | +2,63 | Session cũ 2026-10-11; ảnh smoke cũ |
| camera_pose_classroom.json | 0,100 | −1,02 | Fit lớp học trước locked mount |
| camera_pose_classroom_locked.json | 0,100 | −2,33 | Setup 1 lớp học sau khóa mount |

Pitch dương nhìn xuống, âm nhìn lên. Locked JSON không có `passed`; loader yêu cầu session, H_fixed_by_tape, ít nhất 3 marks/rows finite và RMS ≤ `pose_max_rms_m`, ghi `measured_session_without_pass_flag`. Nếu có flag `passed` thì bắt buộc true. Không tự sửa calibration để tạo PASS.

`GroundPoint.forward_m` là Z tiến từ điểm sàn dưới lens; `left_m` dương trái. `distance_m=hypot(forward,left)` là planar range dùng cho repulsion, **không phải tape Z**. Với roll=0: `Z=H/tan(pitch+atan((v-cy)/fy))`. Full ray rotation xử lý pitch/roll và lateral.

Floor phải được caller xác nhận `glossy` hoặc `matte` theo recording. Mặc định `unknown`: chưa tạo ground estimate, giữ unresolved. Matte dùng bbox bottom. Glossy dùng row-profile đối xứng phản chiếu, kiểm tra texture/correlation/peak rõ ràng/rectified validity; không đạt thì `reflection_unresolved`. Ngưỡng nằm ở `[obstacle]`, cần kiểm chứng trên held-out data. Contact confidence là correlation heuristic, không phải xác suất calibrated.

`Detection.flat_on_floor=True` chỉ dùng khi annotation/adapter xác nhận vật phẳng nằm trên sàn; cho phép bbox contact, không tự suy ra từ class YOLO. Bbox cắt bất kỳ mép ảnh đều từ chối. Rejection/contact/session xuất trong observations. Model COCO furniture chưa bảo đảm recall cho block gỗ hoặc sleeve.

`repulsive_w` là đóng góp UDP chuẩn hóa [-1,1], không phải rad/s. Vật trái → w âm, phải → w dương; threshold exploration 0,6 m, pursuit 0,5 m. Caller phải xem cả `nearest_m`/`unresolved`: w=0 không chứng minh đường trống. Module không quyết định v hoặc gửi motor commands.

## Pose, map và cửa

`Pose2D(x_m,y_m,yaw_rad)` dùng world metres, yaw CCW; yaw=0 hướng +x. `RobotPose` KR có các alias này, truyền trực tiếp được vào `PreScanner`. Timestamp pose phải tương ứng frame; không dùng pose mặc định khi thiếu dữ liệu.

`camera_forward_m/camera_left_m` là lens offset theo gốc pose. Mặc định 0 chỉ đúng khi pose origin là điểm dưới lens. KR marker correction hiện biểu diễn camera position còn odometry cần thống nhất gốc; phải xác nhận/đo offset và footprint trước HIL.

Grid UNKNOWN=-1/FREE=0/OCCUPIED=1, `cells[row_y,col_x]`. Chỉ footprint đã đi và `seen_floor` được xác nhận độc lập mới tạo FREE; không dùng YOLO absence. Occupied persists; floor rays dừng tại occupied/outside. Extent cố định, pose ngoài map gây lỗi. NPZ save/load atomic, metadata/guarding pose, không pickle.

`VantageSelector` cần **tọa độ cửa world đã đo/ước lượng có range**, không dùng bearing đơn lẻ. `EntranceResult.estimate_door_world_xy(pose)` trả None khi thiếu range; `RobotPose.calculate_door_world_xy(bearing, distance_m)` yêu cầu range explicit. Hai helper dùng range/bearing từ gốc pose: caller phải hiệu chỉnh camera offset; không lấy optical/euclidean range marker làm floor range cửa trực tiếp.

Vantage chỉ xét FREE reachable có footprint clearance, LOS không qua UNKNOWN/occupied (cho phép occupied cell endpoint cửa), cách cửa 1,5–3 m và ưu tiên boundary đã quan sát. Trả None nếu không đủ evidence. Yaw hướng cửa cho camera placement; robot quay tâm phòng/audio thuộc deployment.

```python
from sentry.perception.obstacle import ObstacleDetector
from sentry.nav.gridmap import OccupancyGrid
from sentry.nav.vantage import VantageSelector
from sentry.nav.prescan import PreScanner

detector = ObstacleDetector.from_config(
    camera_pose_path='calib/camera_pose_classroom_locked.json', floor_type='glossy')
scanner = PreScanner(detector, OccupancyGrid.from_config(), VantageSelector.from_config(),
                     door_xy=measured_door_world_xy)
# frame: VideoFrame raw; pose: KR RobotPose hoặc Pose2D cùng thời điểm.
result = scanner(frame.frame_bgr, frame.t_cap, pose, seen_floor=confirmed_floor_points)
scanner.grid.save('data/room_map.npz')
```

Không cung cấp seen_floor thì map chỉ biết footprint và điểm vật cản, có thể chưa chọn được vantage. Không thêm floor points tùy ý để tạo PASS.

## Chạy single-image và replay

Weights YOLO local ở `data/models/yolov8n.pt`, không tự download. XFeat local ở `weights/xfeat.pt` được verify pinned hash. DINOv2 chỉ cần cho phone-reference/combined policy, chưa tải/cache trong phiên này. Room enrollment và D1 doorway replay vẫn cần dữ liệu thật.

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
.venv/Scripts/python.exe -m tools.obstacle_image --image data/D1/setup1_frame_raw.jpg --camera-pose calib/camera_pose_classroom_locked.json --floor-type glossy --out data/w2/setup1
.venv/Scripts/python.exe -m tools.prescan_replay --recording data/D1 --poses data/D1/poses.csv --camera-pose calib/camera_pose_classroom_locked.json --floor-type glossy --door 4.0 1.0 --out data/w2/replay
```

Paths và `--door` là ví dụ, thay bằng dữ liệu/đo thực. `--camera` override intrinsics. Mixed-session recordings phải chia riêng để chọn đúng pose/floor. Config copy cho CPU nên ở repo root (relative paths resolve từ config parent); dùng `--config` và device cpu.

Single-image không có world pose, xuất world coordinates trống. `--manual-regions data/D1/regions.json` nhận list `{id,xyxy,flat_on_floor}` với bbox rectified; chỉ là diagnostic geometry/contact, không chấm detector accuracy/recall.

Replay theo `tools.record`: jetbot_meta.jsonl + jetbot/. Poses CSV phải đủ mỗi frame theo thứ tự metadata, frame_index từ 0, không dùng seq vì có thể reset:

```csv
frame_index,x_m,y_m,yaw_rad,seen_floor_json
0,0,0,0,"[[1.0,0.2]]"
1,0.1,0,0,[]
```

Seen_floor ví dụ chỉ dùng khi điểm đó đã xác nhận sàn trống. Output observations.csv có forward/left/planar/world/contact/floor/session/rejection; frames.jsonl, room_map.npz và summary.json. Raw D1/ROI/replay riêng giữ dưới data được Git ignore, không đưa lên repo public.

## Nhãn và evaluator T1

Tape là **forward từ plumb point dưới lens**, field `tape_forward_m` (cũng nhận `forward_m` của nhãn DQK). Không dùng `tape_distance_m` hoặc chuyển tape/lateral bằng hypot. Labels phải độc lập với projection.

```csv
obstacle_id,frame_index,detection_index,tape_forward_m,floor,use_in_metric,world_x_m,world_y_m,map_eligible
chair_01,0,0,1.40,glossy,yes,,,no
chair_right,0,1,1.70,glossy,check,,,no
chair_missing,1,-1,0.80,matte,yes,0.80,0.20,yes
bag_cut,0,2,0.40,glossy,no,,,no
```

Ghép frame_index/detection_index thủ công đúng object, không dùng ground truth để chọn detection gần nhất. Detection_index=-1 ghi missed object. `use_in_metric=no` loại và báo ID; `check` vẫn dùng forward đã xác nhận nhưng mặc định không chấm map. `map_eligible=yes` yêu cầu world truth finite/đã xác nhận. Lateral ghế phải setup 1 chưa xác nhận không đưa vào map truth.

World coordinates optional cho forward-only. Cùng ID phải có một fixed contact/floor; các setup/floor khác dùng ID riêng. Một detection chỉ ghép một annotation. Object eligible thiếu estimate không bị bỏ để tạo PASS.

```powershell
.venv/Scripts/python.exe -m tools.evaluate_w2 --observations data/w2/setup1/observations.csv --annotations data/D1/w2_annotations.csv --out data/w2/setup1/metrics.json
# Khi có map + world truth, thêm --map data/w2/replay/room_map.npz.
```

Tool lấy median relative error theo ID rồi median/p90 giữa IDs chung và từng sàn. Distance PASS cần ≥20 eligible IDs, mỗi ID có estimate, median ≤10%, p90 ≤20%, có cả glossy/matte và từng sàn đạt limits. Thiếu matte báo rõ, không tạo PASS dù subset đạt. Đây chưa phải detector recall benchmark.

Map PASS cần ≥20 confirmed world IDs, ≥80% trong 20 cm của nearest occupied cell centre. Không có map/world truth thì map_pass false; metric này chưa đánh giá precision/coverage và có thể bị false positives/nhiều ID khớp một cell ảnh hưởng. CLI exit 1 khi formal passed false, JSON vẫn chứa kết quả diagnostic.

## Kiểm chứng và phần còn chờ

```powershell
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-w2-check -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m tools.check_w2 --out reports/HuynhNguyenHoaiLoc/week-02/inference_smoke.json
.venv/Scripts/python.exe -m pytest tests/test_w2_gpu.py --basetemp=data/pytest-w2-gpu-check -p no:cacheprovider -q
```

Smoke mặc định dùng ảnh/pose cũ public và floor unknown, ghi hashes/device/FP32/latency; không đánh giá setup 1 accuracy hay full pipeline/RTX4050. Có thể chọn image/pose/floor qua CLI; output của ảnh riêng giữ data.

`TiltFilter` DQK nhận same-K undistorted marker frames; obstacle detector hiện dùng pose session JSON, chưa nối live tilt từng frame. Chờ D1 matte/≥20 objects/world poses, room enrollment và T2 robot: 0 collisions 5×3 phút, vantage đủ 3 điều kiện 5/5. Test synthetic không thay nghiệm thu ngoài thực tế.
