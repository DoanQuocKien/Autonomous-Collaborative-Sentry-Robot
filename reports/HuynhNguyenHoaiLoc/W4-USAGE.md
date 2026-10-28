# HNHL W4 — cách chạy và hợp đồng dữ liệu

## Person re-ID

```python
from sentry.perception.reid import PersonReID, match_gallery

pipeline = PersonReID.from_config()  # local YOLOv8n + OSNet-AIN mặc định
result = pipeline(frame.frame_bgr, frame.t_cap)  # VideoFrame live hoặc replay, raw BGR uint8
for person in result.people:
    if person.embedding is not None:
        # gallery chỉ chứa vectors từ cùng result.model_id / weights hash.
        identity, cosine = match_gallery(person.embedding, gallery, threshold=calibrated_threshold)
```

`ReIDResult(t, people, model_id)`; `PersonAppearance(xyxy,confidence,embedding,rejection)`. Output bbox giữ tọa độ frame raw, crop clip về ảnh; lỗi/nhỏ có embedding None. Positive result không tự enqueue hoặc gửi motor; KR dùng model_id cùng appearance vector khi nối queue. 512D embedding của hai OSNet không thuộc cùng không gian dù có cùng kích thước.

Local weights theo `tools.fetch_models`: `osnet_ain_x1_0_dg.pth` và `osnet_x0_25_market1501.pth`. Không dùng `pretrained=True` hoặc lấy ImageNet weights làm re-ID weights. Các tunables ở `[reid]`, input 256×128, RGB/ImageNet normalization, CPU/CUDA có thể cấu hình. Runtime không download; torch checkpoints dùng weights_only với allowlist NumPy scalar cụ thể.

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
.venv/Scripts/python.exe -m tools.check_reid --out data/w04/reid_smoke.json
.venv/Scripts/python.exe -m tools.evaluate_reid --manifest data/D2/reid_manifest.csv --out reports/HuynhNguyenHoaiLoc/week-04/reid_d2_metrics.json
```

Manifest CSV relative image paths từ thư mục CSV:

```csv
sample_id,identity,image,session,entry_id,camera,partition,role,x1,y1,x2,y2
cal_g_01,p01,crops/cal_g_01.jpg,cal_session,g01,esp32,calibration,gallery,,,,
cal_q_01,p01,crops/cal_q_01.jpg,cal_session,q01,esp32,calibration,query,,,,
test_g_01,p01,crops/test_g_01.jpg,test_session,g01,esp32,test,gallery,,,,
test_q_01,p01,crops/test_q_01.jpg,test_session,q01,jetbot,test,query,,,,
```

Đây chỉ là mẫu schema, phải bổ sung nhiều identities/entries thật; ≥5 gallery identities theo target hiện tại. `identity` là ID ẩn danh, không ghi tên thật. Có thể dùng full frame với đủ bốn trường xyxy; nếu để trống cả bốn thì image là person crop. Cùng capture entry không chia gallery/query hoặc calibration/test; toàn session không chia calibration/test. Byte-duplicate bị từ chối kể cả đổi tên; near-duplicates cần người gán nhãn kiểm tra.

Tool chọn model và threshold trên calibration. Test chỉ đo tại threshold cố định; test ROC phục vụ báo cáo, không chọn lại threshold. Rank-1 tie giữa IDs tính fail. ROC dùng max impostor score theo query, không làm FAR nhỏ giả bằng đếm nhiều negative pairs dễ. Giới hạn nhỏ mẫu và số query cross-camera được ghi rõ. Chỉ recommend nếu đủ identities, rank1 ≥0,85, FAR ≤0,01, TAR ≥0,85 và không phải threshold reject-all. Các gate nằm trong config; threshold 0,7 mặc định chưa được calibration.

Crop evaluation chưa đo person-detector recall và chưa chứng minh handoff ESP32→JetBot nếu không có queries cross-camera. Ảnh/crops/embeddings luôn giữ data ngoài Git; report chỉ chứa metrics/counts/hash.

## D5 corrected-label training

Không ghi đè export hoặc checkpoint cũ:

```powershell
.venv/Scripts/python.exe -m tools.prepare_d5_yolo_dev --source data/D5 --output data/D5_yolo_w04_new
.venv/Scripts/python.exe -m tools.train_d5 --train --data data/D5_yolo_w04_new/data.yaml --weights data/models/yolov8n.pt --imgsz 640 --epochs 30 --batch 8 --workers 0 --seed 42 --device 0 --project runs/d5_w04_new --name yolov8n_640 --out data/w04/train640.json
```

Đổi imgsz 320/416 để so sánh; bản đã chạy trong báo cáo ở `data/D5_yolo_w04` và `runs/d5_w04_corrected`. Cùng session 1024 vẫn là internal dev, không phải T1. Muốn đánh giá lại checkpoint hiện có dùng `tools.train_d5 --val ... --data ... --imgsz ...`; tool từ chối overwrite run/spec.

```powershell
.venv/Scripts/python.exe -m tools.freeze_d5 --weights runs/d5_w04_corrected/yolov8n_640/weights/best.pt --data data/D5_yolo_w04/data.yaml --out-dir data/releases/d5_new --imgsz 640
.venv/Scripts/python.exe -m tools.check_d5_onnx --artifact-dir data/releases/d5_new --images-dir data/D5_yolo_w04/images/val --out data/w04/onnx_parity.json
```

Freeze kiểm tra class order, tạo local `d5_candidate.pt`, `.onnx` opset11 fixed batch1 FP32 và manifest với hash/provenance. Bản 640 hiện chọn theo dev mAP, chưa dành cho robot; manifest `deployment_ready=false`. Không sửa class_ids COCO của live detector thành IDs D5; đây là model custom tám classes. Không commit artifacts. ONNX copy sang Nano để DQK build TensorRT engine theo `docs/Edge Deployment.md`; không copy engine GPU khác. Không dùng parity laptop để báo Nano/FP16 PASS.

## Independent D5 holdout

Chuẩn bị layout `images/...jpg`, `labels/...txt` và CSV:

```csv
image,label,session,floor
images/new_001.jpg,labels/new_001.txt,new_capture_day,glossy
images/new_002.jpg,labels/new_002.txt,another_capture,matte
```

Không dùng lại session hoặc exact image đã tham gia train/dev-val. Label theo class list đã freeze, đầy đủ mọi vật hiện diện và empty controls đã review. Không chỉ đặt tên session khác cho cùng clip cũ.

```powershell
.venv/Scripts/python.exe -m tools.evaluate_d5_holdout --manifest data/D5_independent/manifest.csv --artifact-dir data/releases/d5_w04_640 --out reports/HuynhNguyenHoaiLoc/week-04/d5_independent_metrics.json
```

Tool audit session/image hashes và label layout, báo class metrics riêng glossy/matte và Wire alarm trên empty controls tại confidence0,25. Class metrics Ultralytics dùng operating point validation; muốn chốt threshold triển khai cần calibration độc lập. Chưa có tape contact/distance thì `t1_passed` luôn false; không coi detection metrics là toàn bộ nghiệm thu. Chưa có D5 độc lập trên máy trong phiên 28/10.

## Tests

```powershell
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-w04-new -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m pytest -m gpu --basetemp=data/pytest-w04-gpu-new -p no:cacheprovider -q -rs
```

Chưa có D2/D3 và held-out D5: unit/GPU smoke thành công không thay T1. Không có motor/socket control trong các module/tools mới.
