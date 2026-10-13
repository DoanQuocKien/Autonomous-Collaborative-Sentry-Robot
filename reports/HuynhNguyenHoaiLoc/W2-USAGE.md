# HNHL tuần 2 — giao diện và cách kiểm chứng

Triển khai theo `docs/Implementation Plan.md`, Week 2 (12–18/10/2026). Đầu vào camera hiện tại: `calib/camera.json` và `calib/camera_pose_nowedge.json` (H=0,1013 m; pitch xuống 2,63°). Chạy bằng `.venv/Scripts/python.exe` trên laptop HNHL.

## Quy ước để tích hợp với KR/DQK

- `ObstacleDetector.__call__(frame_bgr, t)` trả `ObstacleResult` dataclass; frame BGR uint8 **640×480 từ camera fisheye nguyên bản**. Module tự undistort; caller không undistort lần nữa. Timestamp được giữ nguyên và phải finite.
- Output K bằng K của calibration, cùng hệ pixel với `tools.measure_camera_pose`. YOLO boxes nằm trên ảnh **đã undistort**, không vẽ trực tiếp lên ảnh raw.
- `GroundPoint.forward_m` là khoảng cách theo trục tiến; `left_m` dương sang trái, gốc trên sàn ngay dưới lens. `distance_m` là khoảng cách phẳng `hypot(forward,left)`, `bearing_rad` dương sang trái. Khi camera ngang và pixel ở cx, forward bằng `fy*H/(v-cy)`; camera hiện nghiêng nên phải xoay ray theo pitch trước khi giao sàn. Roll được gỡ theo quy ước phép đo camera.
- `Pose2D(x_m,y_m,yaw_rad)` dùng world x/y metres, yaw ngược chiều kim đồng hồ; yaw=0 hướng +x. KR chuyển pose localization của mình sang dataclass này. `camera_forward_m/camera_left_m` là offset lens so với gốc pose, được grid áp dụng trước khi xoay vào world. Hai offset mặc định 0 chỉ hợp lệ nếu gốc pose là điểm dưới lens; **đo lại theo gốc mà KR chọn**.
- `repulsive_w` là thành phần w **chuẩn hóa [-1,1]**, không phải rad/s. Vật cản trái -> w âm, phải -> w dương; đúng tâm -> hướng mặc định từ config. Gần hơn tăng lực; exploration 0,6 m, pursuit 0,5 m. `detector(frame,t,mode="pursuit")` dùng ngưỡng pursuit.
- `unresolved=True` khi furniture có bbox cắt đáy, pixel rectified không hợp lệ hoặc không có ground intersection trong range. Không lấy bbox bị cắt đáy làm ground contact. Controller phải xem cả `unresolved` và `nearest_m`; w=0 có thể do hai phía cân bằng, không chứng minh đường trống. Module này không quyết định v hay gửi motor.
- Grid giữ UNKNOWN=-1, FREE=0, OCCUPIED=1 ở `cells[row_y,col_x]`. Chỉ vị trí/footprint đã đi và các `seen_floor` **được xác nhận độc lập** mới tạo FREE. Không coi YOLO không phát hiện là floor trống; ray vật cản không clear các ô trên đường. Occupied được giữ cho đến khi có một cơ chế clear được kiểm chứng ở PR khác.
- `seen_floor` là danh sách GroundPoint; có thể do nhãn replay hoặc module xác nhận sàn cung cấp. Hiện chưa có floor segmentation tự động. Khi không cung cấp, bản đồ chỉ biết footprint đã đi và các điểm vật cản; có thể chưa đủ vùng FREE để chọn vị trí.
- Door phải là **tọa độ world (x,y)** đã biết từ KR/đo chuẩn. Bearing một mình chưa đủ. Vantage chỉ chọn ô FREE reachable với clearance footprint, cách door 1,5–3,0 m, LOS không xuyên UNKNOWN/occupied. Chỉ ô occupied của endpoint cửa được miễn LOS. Ưu tiên gần boundary/furniture đã quan sát; UNKNOWN không được xem là tường.
- Vantage yaw hướng cửa cho vị trí đặt camera. Hành vi robot quay hướng tâm phòng/phát audio thuộc phần deployment, chưa có trong module HNHL này.

Ví dụ API (không gửi lệnh điều khiển):

```python
from sentry.perception.obstacle import ObstacleDetector
from sentry.nav.gridmap import OccupancyGrid, Pose2D
from sentry.nav.vantage import VantageSelector
from sentry.nav.prescan import PreScanner

scanner = PreScanner(ObstacleDetector.from_config(), OccupancyGrid.from_config(),
                     VantageSelector.from_config(), door_xy=(4.0, 1.0))
# frame: VideoFrame của live receiver hoặc ReplayStream.read()
# pose: do localization của KR cung cấp, cùng thời điểm với frame.
result = scanner(frame.frame_bgr, frame.t_cap, Pose2D(x_m, y_m, yaw_rad))
scanner.grid.save("data/room_map.npz")
```

Map NPZ chứa `cells` và JSON `metadata` (version1, resolution, origin, camera offset, coordinate convention, guarding pose nếu có). Load bằng `OccupancyGrid.load(path)`, không dùng pickle. Extent cố định trong `[gridmap]`; robot ngoài extent gây lỗi để caller chỉnh extent, không ép điểm vào mép map.

## Chạy offline với D1

Weights đã có ở `data/models/yolov8n.pt`; inference yêu cầu file local, không tự download. Nếu chạy CPU, đổi `[obstacle].device="cpu"` trong một config copy **ở repo root** và dùng `--config`, vì paths tương đối được resolve từ thư mục của config. Các tunables ở `[obstacle]`, `[gridmap]`, `[vantage]`, `[w2_validation]`.

Recording theo format `tools.record`: `jetbot_meta.jsonl` và thư mục `jetbot/`. Chuẩn bị poses CSV có **mỗi frame một pose** theo thứ tự metadata, frame_index từ 0; seq có thể reset. Không tự nội suy hay dùng pose mặc định khi thiếu.

```csv
frame_index,x_m,y_m,yaw_rad,seen_floor_json
0,0,0,0,"[[1.0,0.2]]"
1,0.1,0,0,[]
```

Ví dụ dòng seen_floor chỉ dùng khi đã có bằng chứng sàn trống ở điểm đó; không thêm tùy ý để tạo vantage. Các frames khác phải có pose thực tương ứng.

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
.venv/Scripts/python.exe -m tools.prescan_replay --recording data/D1 --poses data/D1/poses.csv --door 4.0 1.0 --out data/w2
```

`--door 4.0 1.0` là ví dụ, thay bằng tọa độ đo/ước lượng thật. Output: `observations.csv` (bbox rectified, ground/world point hoặc rejection), `frames.jsonl` (timestamps/pose/w/nearest/vantage), `room_map.npz`, `summary.json`. Không gửi lệnh motor. Dữ liệu raw/replay giữ trong `data/`, không đưa lên repo public.

## Đo T1

Nhận D1, chọn ít nhất **20 obstacle IDs độc lập** có tape measurements 0,3–2,0 m và ground contacts world đo chuẩn. Khớp từng vật cản với `frame_index,detection_index` trong observations.csv bằng nhãn thủ công; không khớp theo khoảng cách gần nhất rồi dùng chính ground truth để chọn detection.

```csv
obstacle_id,frame_index,detection_index,tape_distance_m,world_x_m,world_y_m
chair_01,0,0,0.50,0.50,0.00
chair_02,1,-1,0.80,0.80,0.20
```

`detection_index=-1` biểu thị vật cản bị bỏ sót; các ID thiếu estimate được báo và không được loại để tạo PASS. Một detection chỉ được gán cho một annotation. Các world coordinates của một ID phải là cùng ground contact cố định.

**Tape distance trong tool là planar range từ điểm dưới lens đến ground contact**, cùng `distance_m`, không phải khoảng cách từ đầu robot. Nếu nhãn cũ ghi forward distance và lateral offset, chuyển range bằng hypot trước. Ghi riêng camera-to-pose offset để kiểm chứng map. Không lấy khoảng cách từ chính camera projection làm ground truth.

```powershell
.venv/Scripts/python.exe -m tools.evaluate_w2 --observations data/w2/observations.csv --annotations data/D1/w2_annotations.csv --map data/w2/room_map.npz --out reports/HuynhNguyenHoaiLoc/week-02/d1_metrics.json
```

Tool gom relative errors bằng median theo obstacle ID để video dài không lấn video ngắn, rồi báo median/p90 giữa các ID. PASS distance: đủ20 IDs, mỗi ID có estimate, median<=10%, p90<=20%. Report số ID thiếu riêng; protocol này đánh giá ground-distance estimates, chưa phải recall benchmark detector.

Map: khoảng cách tới tâm occupied cell gần nhất trong map đã lưu, >=80% các20 IDs trong20 cm. Đây là metric định vị có thể bị false positives hoặc nhiều ID khớp một cell ảnh hưởng; báo thêm các sai lệch cụ thể, không suy ra precision/coverage của cả map. JSON có thresholds sử dụng; CLI exit1 khi không đạt.

## Kiểm chứng tái lập và phần còn chờ

```powershell
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-w2-check -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m tools.check_w2 --out reports/HuynhNguyenHoaiLoc/week-02/inference_smoke.json
.venv/Scripts/python.exe -m pytest tests/test_w2_gpu.py --basetemp=data/pytest-w2-gpu-check -p no:cacheprovider -q
```

GPU smoke dùng ảnh raw đã commit của phép đo camera, 3 warmup/10 inference; ghi runtime thực, FP32, phiên bản, hashes weights/image/config/calibration và thời gian detector (undistort+predict+projection). Không gồm mapping/vantage, video transport hay motor; không phải FPS toàn pipeline hoặc baseline RTX4050. Kiểm tra GPU cần weights đã fetch, có thể skip khi không có CUDA/weights.

T1 D1 còn chờ dữ liệu/nhãn thật. T2 còn chờ KR pose/entrance và phiên robot DQK: 0 collisions trong5×3 phút, sweet spot đủ3 điều kiện5/5. Đo footprint+camera offset và điều chỉnh tunables trước HIL. `calib/motion.json` có drift và gains từ một protocol; KR/DQK còn kiểm chứng đa tốc độ. Không thay kết quả thật bằng test synthetic.
