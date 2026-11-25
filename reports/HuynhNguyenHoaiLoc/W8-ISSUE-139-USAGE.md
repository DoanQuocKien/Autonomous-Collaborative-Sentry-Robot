# HNHL bàn giao chuẩn bị issue 139

Buổi lớp dự kiến **26/11/2026, 08:00–12:00, Asia/Bangkok**. Tài liệu này bàn giao ba phần HNHL trước buổi D3/D4, không xác nhận buổi quay đã diễn ra. [Issue #139](https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/issues/139).

## ONNX cho DQK xây engine Stage A

Artifact ở [team_data/HNHL_yolov8n_320_op11_2026-11-25.zip](../../team_data/HNHL_yolov8n_320_op11_2026-11-25.zip), theo AES/password convention của `tools.team_data`. Gói 11.059.599 bytes chứa ONNX, JSON và README, đã đọc lại/decrypt và đối chiếu hash từng file. [Hash và parity](week-08/onnx_delivery.json).

```powershell
.venv/Scripts/python.exe -m tools.team_data unpack team_data/HNHL_yolov8n_320_op11_2026-11-25.zip data/models/onnx_from_HNHL_1125
```

Stock COCO YOLOv8n, **không phải D5 fine-tune**. Model cố định FP32, opset 11, input `images [1,3,320,320]`, output `[1,84,2100]`. Input RGB/NCHW/[0,1], cùng letterbox scale/padding với đường laptop. Output raw cần postprocessing/NMS của YOLOv8. Tham số export theo [Ultralytics export](https://docs.ultralytics.com/modes/export/), được kiểm tra trực tiếp trên graph đã xuất.

ONNX SHA256 `4905b828a5ab1da5dcb4d0bd2cf12fad75b83cd91d7cb0ff71ccad1bd9c216eb`. ONNX checker và CPU ONNX Runtime đã chạy thật; ba tensor zero/random/gradient có cosine tối thiểu 0,99999999999995, max absolute diff tối đa 0,000458 so PyTorch FP32. Đây là export parity, chưa phải D1 accuracy hay TensorRT FP16 parity.

DQK dùng lệnh hiện có trong [Edge Deployment](../../docs/Edge%20Deployment.md) trên Jetson:

```bash
/usr/src/tensorrt/bin/trtexec --onnx=yolov8n_320_op11.onnx --saveEngine=yolov8n_320_op11_fp16.engine --fp16 --workspace=512
```

Nhờ DQK bàn giao build log, phiên bản TensorRT/JetPack, hash engine và outputs trên cùng D1 parity inputs để HNHL chấm cosine/distance. Chưa có engine Nano trong phiên này, nên G2 và distance-error comparison của đường robot tiếp tục chờ. Exporter hiện trả exit code khác 0 khi job lỗi và từ chối ghi đè file YOLO đã có.

## Detector và đầu vào cho KR

`sentry.perception.pose.LungeDetector` hỗ trợ `update(t, bbox, track_id=..., epoch=...)` và callable `(t, sample) -> bool`, khớp interface pluggable của PR #142. Bbox dùng raw pixel xyxy. So sánh mọi baseline trong cửa sổ capture **100 ms** với ngưỡng strict **dA/A > 0,40** từ config; không thay bằng số frame. Duplicate timestamp, clock reset, target/epoch/resize, mất box, box nhỏ hoặc cắt mép làm mất baseline. Sai số làm tròn timestamp tại biên cho phép 1 microsecond.

`sample.t_cap` được ưu tiên cho cửa sổ detector; `sample.t` có thể là `t_local` để ghép onset. Chỉ truyền target đã chọn có track ID/epoch ổn định. Bbox phình do chuyển động/camera hoặc jitter vẫn có thể false-trigger; người bị crop có thể bị bỏ lỡ. Cue nâng cổ chân tương đối với hips/chiều cao box đã có nhưng mặc định tắt (`strike.ankle_rise_fraction=0`), cần D4 trước khi đặt threshold.

`YOLOPoseEstimator` nạp YOLOv8n-pose và trả bbox, 17 keypoints/confidence theo COCO; không điều khiển robot. Lệnh offline sau buổi quay:

```powershell
$env:YOLO_AUTOINSTALL = 'false'
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
.venv/Scripts/python.exe -m tools.detect_lunges --recording data/D4/2026-11-26 --out-dir data/D4/2026-11-26/pose-01 --device 0
```

Output private gồm `pose.jsonl` (raw geometry, chưa có `strike`), `strikes.jsonl` (đã chạy detector) và `summary.json` với hashes/counters/device thực. Mọi frame đều có dòng, kể cả missing/ambiguous. Không tự chọn người đầu tiên khi ảnh có nhiều người. Chỉ dùng output khi summary có `complete=true`; output cũ được bảo vệ.

Sau khi PR #142 của KR được review/merge, chấm raw geometry bằng detector HNHL:

```powershell
.venv/Scripts/python.exe -m tools.evaluate_strike_false_triggers --predictions data/D4/2026-11-26/pose-01/pose.jsonl --detector sentry.perception.pose:LungeDetector --events data/D4/2026-11-26/events.csv --out data/D4/2026-11-26/evaluation-01.json
```

Hoặc dùng `strikes.jsonl` làm predictions và bỏ `--detector` để chấm kết quả đã tính. Clock `t_local` là lúc laptop nhận/ghi frame, không phải camera exposure hoặc motor-command time. Nhờ KR giữ cả raw/refined onset, align với đúng `jetbot_meta.jsonl`, epoch/frame index và clap/phone reference. Chưa dùng delay offline này để khẳng định frame-to-command ≤150 ms. Detector chưa tự bật vào đường motor của `pursue_live`; `--evade` trên main vẫn dùng key `e` theo PR #138.

## Những gì HNHL cần từ DQK và KR cho D3

- **DQK:** giữ nguyên `jetbot/*.jpg` và `jetbot_meta.jsonl`, seq/t_cap/t_rx/t_local; đo mount/height/self-pose đúng ngày và ghi camera CAM1, calibration hash, floor/light/battery. Quay từng clip 65–90 s để thời gian capture thực ≥60 s, có ít nhất hai người đi, dừng, giao nhau, che khuất và xuất hiện lại. Ghi riêng target được chọn, lúc mất/khóa lại; giữ distractors và frame trống.
- **DQK cùng các thành viên:** lấy gallery và query body crops cho từng người từ đoạn/entry khác nhau, gắn cùng person code xuyên D2/ESP32 và D3/JetBot; giữ model/hash/preprocessing của cả OSNet x0.25 và AIN. Không cho cùng frame/crop vào gallery và query. Nếu chỉ ba người, báo pilot ba người; gate re-ID ≥5 identities vẫn chưa đủ. Không chốt lock model chỉ từ thiếu gallery hoặc dữ liệu tự sinh.
- **KR:** bbox xyxy raw frame và identity qua occlusion, visibility, đầy đủ mọi frame kể cả empty; nhãn `reviewed=false` cho tới khi đã kiểm tra. Lưu target identity truth/events để chấm re-lock riêng. Khi KR đóng vai lunge cần người khác bấm onset, không kiêm hai vai cùng lúc; phân vai thực tế do nhóm xác nhận.

Dùng `python -m tools.record D3/2026-11-26` cho hai camera nếu cần cross-camera, chỉ một reader cho mỗi stream. Chuẩn bị manifest JetBot bằng `tools.prepare_d3_recording` theo [handoff D3 chi tiết](midterm/D3-HANDOFF-HNHL.md); giữ các epoch riêng, không nội suy timestamp. Bàn giao recording/labels/crops trong `data/` hoặc archive theo [Team Data Sharing](../../docs/Team%20Data%20Sharing.md), không commit ảnh/video thô. HNHL sẽ review nhãn rồi chạy re-ID/tracking/re-lock evaluation; raw D3/D4 chưa có ở phiên chuẩn bị này.

Các vai/tốc độ và protocol padded-lunge trong PR #140 còn là draft để nhóm chốt. Ghi D4 theo quy trình motors disabled; thử evasion chuyển động là bước riêng do DQK vận hành với dead-man/e-stop, sau khi dữ liệu và detector đã được kiểm tra.
