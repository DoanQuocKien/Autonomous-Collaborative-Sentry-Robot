# HNHL W5 — tracking, target lock và GPU profiling

## API live và handoff từ Phase 2

```python
from sentry.perception.tracker import PersonTracker

tracker = PersonTracker.from_config()  # local YOLOv8n, ByteTrack, OSNet-AIN
tracker.set_target_record(queue.active_target)  # IntruderRecord thật từ Phase2
result = tracker(frame.frame_bgr, frame.t_cap)
if result.target is not None:
    bbox = result.target.xyxy  # raw image coordinates; caller handles control/projection
```

`PersonTrack(track_id,epoch,xyxy,confidence,embedding)` và `TrackingResult(t,tracks,target,lock_state,model_id,epoch)`. Không có motor I/O trong module. Một instance sở hữu một stream/consumer; không gọi đồng thời từ nhiều luồng. ByteTrack là implementation của Ultralytics đang cài (đã kiểm chứng 8.4.172), dependency `lap` được khai báo rõ để import không tự cài package.

Mỗi lock cần embedding mới cùng architecture/weights hash, vượt cosine threshold và margin với ứng viên kế tiếp. Không dựa vào track ID để khẳng định danh tính, không cập nhật gallery bằng vector query để tránh drift. Mặc định cần hai frame xác nhận, kể cả re-lock sau che khuất. Tied scores luôn abstain dù margin bằng 0. Thiếu reference: UNSET; đang xác nhận: CONFIRMING; target hiện tại hợp lệ: LOCKED; vắng/không rõ: LOST rồi SEARCHING. `target=None` khi mất dấu; không xuất bbox dự đoán để điều khiển mù.

`set_target(vector,model_id)` dùng cho gallery đã kiểm chứng. `set_target_record` yêu cầu metadata `appearance_simulated=false` và đúng `appearance_model_id`; không nhận vector giả của replay KR. Khi queue đổi người: gọi lại set_target_record. `clear_target()` bỏ reference. Cosine 0,70/margin 0,05 là provisional, chưa được calibration bằng D3.

ByteTrack nhận cả detection confidence thấp 0,10 để association; new track cần 0,25. Timestamp phải finite và tăng nghiêm ngặt. Sau restart/sequence reset phải `reset()` trước frame mới. Khoảng trống >1 s tự reset motion history, tăng epoch và xác nhận lại lock; reference thật vẫn giữ. `(epoch,track_id)` là key, không chỉ ID tái sử dụng. Buffer 30 tính theo processed frames, không phải thời gian camera; cần tune theo FPS thật. Các tham số ở `[tracking]`.

## CLI chỉ nhận video, không điều khiển robot

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
$env:YOLO_AUTOINSTALL = 'false'
.venv/Scripts/python.exe -m tools.track_live --ip auto --seconds 60 --out data/w5/live_tracks.jsonl
```

CLI xử lý seq reset và timestamp capture; không suy ra latency clock-synced từ phép chạy này. `--target data/w5/target.npz` tùy chọn: NPZ `vector` (512,) và scalar string `model_id`, `allow_pickle=False`. Không có target thì không tự chọn ai để bám. Chưa chạy JetBot thật trong phiên này.

Replay manifest JSON, image paths relative to manifest:

```json
{"frames": [{"t": 0.0, "image": "images/f000.jpg"}, {"t": 0.05, "image": "images/f001.jpg"}]}
```

```powershell
.venv/Scripts/python.exe -m tools.track_replay --manifest data/D3/frames.json --out data/w5/d3_predictions.json --target data/w5/target.npz
```

Predictions có person boxes/IDs nên CLI chỉ cho ghi dưới `data/`. Không ghi embeddings trong predictions. Nếu cần đổi mục tiêu trong replay, dùng API theo event log của Phase2; CLI hiện chỉ nhận một reference cho cả clip.

## D3 evaluator

Truth: `kind="D3_TRACKING", reviewed=true, camera="jetbot"`, `frames=[{"t":...,"objects":[{"id":"p1","xyxy":[...]}]}]`. Gán nhãn toàn bộ người nhìn thấy, kể cả distractor; khi occluded hoàn toàn thì không có box, khi thấy lại vẫn giữ identity. Pred: cùng frames/timestamp, `tracks=[{"track_id":1,"epoch":0,"xyxy":[...]}]`. Mọi frame, kể cả empty, phải có mặt trên cả hai phía.

```powershell
.venv/Scripts/python.exe -m tools.evaluate_tracking --truth data/D3/truth.json --predictions data/w5/d3_predictions.json --out reports/HuynhNguyenHoaiLoc/week-05/d3_metrics.json
```

Hungarian one-to-one, IoU ≥0,50. ID switch khi identity được ghép sang key khác lần ghép trước, kể cả sau khoảng trống; tính theo phút video, đồng thời báo misses/FP/recall. Protocol yêu cầu video JetBot reviewed ≥60 s và cảnh ≥2 người. Giới hạn plan ≤1 switch/phút giữ nguyên. `switch_limit_met` báo riêng tiêu chí đó; `t1_passed` thận trọng còn yêu cầu không miss/FP để không tạo PASS bằng tracker không output. Điều kiện coverage này là guard bảo thủ của tool, không thay đổi ngưỡng plan; nếu có misses/FP thì reviewer đánh giá cùng số liệu. Không đo lock accuracy chỉ từ ID-switch. D3 chưa có: chưa chạy T1, không dùng D2 làm D3.

## GPU profiling và F9

Chuẩn bị local assets trước inference: YOLOv8n, YOLOv8n-pose, hai face ONNX trong `data/insightface/models/buffalo_s`, OSNet và XFeat. DINOv2-B cache dùng revision đã pin trong `tools.fetch_models`; đặt `$env:TORCH_HOME = Join-Path (Get-Location) 'data/torch_w5'` rồi gọi `fetch_dino('b')` từ helper chuẩn bị model. Model artifacts không commit. `nvidia-ml-py` đo VRAM tổng thiết bị; inference chặn urllib/requests để không âm thầm download.

Input manifest chỉ cần `frames=[{"image":"..."}]`; dùng ảnh đã được phép sử dụng, giữ manifest trong `data/`. Ví dụ:

```powershell
.venv/Scripts/python.exe -m tools.profile_pipeline --manifest data/w5_profile_inputs.json --out reports/HuynhNguyenHoaiLoc/week-05/pipeline_both.json
.venv/Scripts/python.exe -m tools.profile_pipeline --manifest data/w5_profile_inputs.json --entrance-mode xfeat --out reports/HuynhNguyenHoaiLoc/week-05/pipeline_xfeat.json
.venv/Scripts/python.exe -m tools.profile_pipeline --manifest data/w5_profile_inputs.json --door-hz 5 --out reports/HuynhNguyenHoaiLoc/week-05/pipeline_both_5hz.json
.venv/Scripts/python.exe -m tools.plot_w5_profile --root reports/HuynhNguyenHoaiLoc/week-05 --out reports/HuynhNguyenHoaiLoc/week-05/F9_pipeline_gpu.png
```

Tracking/OSNet và pose chạy mỗi frame. Face/entrance mặc định mỗi frame; `--door-hz 5` dùng wall clock, không backlog/catch-up, báo actual Hz (không tự ghi 5 Hz). Các model vẫn cùng resident. Đây là scheduler của benchmark, chưa được nối vào main app. Workload body/face được pad ít nhất hai crop khi ít detections, crop pad là synthetic và được đếm riêng. XFeat match/RANSAC và DINO descriptor đều thực thi; reference chỉ phục vụ workload, không có accuracy cửa trong benchmark này.

5 warmup/100 iterations; DINO FP16 theo backend sẵn có, các Torch model còn lại FP32. NVML device-used lấy mẫu 20 ms bao gồm Torch, ORT, driver và process khác; có thể bỏ lỡ spike ngắn. Torch allocated/reserved báo riêng. Đây là aggregate workload throughput, không gồm transport, map, control loop và không phải GPU time thuần. `measured_workload_budget_met` so ≥15 FPS/≤5,5 GB decimal (5.500.000.000 bytes, khoảng5,12 GiB); `t1_accepted=false`, RTX5060 không thay RTX4050. JSON giữ run settings gốc; `budget_recheck` áp ngưỡng decimal lên mẫu đo đã lưu, không thay số timing/memory. Không xem ba run ngắn là một nghiên cứu causal về model speed.

## Kiểm thử

```powershell
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-w5-cpu-new -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m pytest -m gpu --basetemp=data/pytest-w5-gpu-new -p no:cacheprovider -q -rs
```

Synthetic tests và D2 runtime smoke không chứng minh ID switches hoặc re-lock accuracy trên D3. Bằng chứng public chỉ chứa metrics/hash; ảnh, person boxes, identities, reference vectors, engines và predictions đầy đủ ở data/ ignore.
