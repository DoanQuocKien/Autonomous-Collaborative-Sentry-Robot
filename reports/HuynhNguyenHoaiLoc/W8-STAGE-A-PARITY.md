# HNHL W8: D1 parity và bàn giao TensorRT

Kiểm chứng ngày **25/11/2026, Asia/Bangkok**. Đây là phần laptop của Stage A trong [Implementation Plan](../../docs/Implementation%20Plan.md), bổ sung cho [handoff issue #139](W8-ISSUE-139-USAGE.md).

## Đã chạy trên laptop

- 200 ảnh khác nhau, chọn đều theo thứ tự từ 256 ảnh của `chairs_a/b/c` ngày 15/10; lần lượt 71/65/64 ảnh. Không có ảnh người hoặc dữ liệu mới của buổi 26/11. Chín ID ghế có bbox độc lập và tape forward từ dưới lens; đây là ba clip tĩnh tương quan, không phải 200 cảnh độc lập.
- Cùng trọng số stock COCO và cùng tensor: undistort 640×480 bằng K gốc, pose `classroom_1015`, letterbox vuông 320×320, RGB/NCHW/[0,1]. PyTorch CPU FP32 so ONNX Runtime CPU FP32. Output raw `[1,84,2100]`.
- Cosine tối thiểu **0,99999999999989**, **919/919** bbox khớp theo class ở IoU ≥0,9; số bbox bằng nhau trên mọi frame. Chỉ tiêu chuyển đổi PyTorch → ONNX đạt trên bộ này. **Đây chưa phải kết quả TensorRT.**
- Postprocessing dùng best-class, confidence 0,25, class-aware NMS IoU 0,7, max 300, clip về ảnh rectified. `jetson.yolo_post.decode` cũ dùng class-agnostic NMS; KR/DQK cần đối chiếu lựa chọn này khi tích hợp, không mặc định decoder cũ đã đồng nhất với đường laptop.

Kết quả máy đọc được: [JSON](week-08/stage_a_onnx_d1_release.json), [stdout](week-08/stage_a_onnx_d1_release.txt). Report ghi hashes model/calibration/pose/config/code, device và coverage từng ID; raw tensors và ảnh giữ trong `data/`.

## So sánh khoảng cách và giới hạn thực tế

Ground/contact dùng cùng `ObstacleDetector` laptop, đúng session pose và floor **glossy**, không đổi sàn thành matte để lấy số đo. Ghép ID bằng bbox IoU ≥0,3 một-một, không dùng tape distance để chọn prediction. Mỗi ID lấy median relative error trước khi tính median/p90 trên các ID; ID thiếu giữ nguyên.

| Đường chạy | ID có khoảng cách / tổng ID | Kết quả |
| :-- | --: | :-- |
| PyTorch 320, adapter laptop | 3/9 | Chỉ 4 ID-frame hợp lệ, không ID nào có khoảng cách ở ≥50% frame |
| ONNX 320, adapter laptop | 3/9 | Cùng coverage; median error trên 3 ID khoảng 41,67%, chưa đạt accuracy |
| Laptop cấu hình hiện tại, YOLO 640 FP32 CUDA | 0/9 | Bbox bị cắt hoặc contact phản chiếu chưa giải quyết; không có baseline distance để so chênh lệch |

PyTorch/ONNX 320 có chênh lệch median error khoảng **0,000174 điểm phần trăm** trên ba ID chung. Đây là diagnostic của chuyển đổi: sai số lớn và coverage rất thấp vẫn được giữ trong report. So sánh **với laptop 640** trả `null` cho median-error delta và `passed`, không tạo PASS từ tập rỗng. Chưa thể kết luận Stage A nằm trong 2 điểm phần trăm của laptop.

Tool chỉ đánh giá distance gate khi có ≥20 ID có estimate ở cả hai đường và không bỏ ID thiếu. Policy này được ghi trong JSON; chín ghế hiện tại không đóng T1. Cần thêm D1 có contact xác định được, nhãn contact được review hoặc bộ matte thật cùng pose/calibration. Không suy ra accuracy cho vật nhỏ/D5, full-image precision, hoặc map/HIL từ lần chạy này.

## Chạy lại trên laptop

Các đường output phải mới; giữ code/config/model đúng version được ghi trong manifest.

```powershell
$env:YOLO_AUTOINSTALL = 'false'
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
.venv/Scripts/python.exe -m tools.stage_a_parity prepare --onnx data/models/onnx_issue139_2026-11-25/yolov8n_320_op11.onnx --out data/stage_a_rerun --report reports/HuynhNguyenHoaiLoc/week-08/stage_a_rerun.json
```

Mặc định đọc ảnh private `data/dqk-obstacles-2026-10-15`. Có thể đổi bằng `--data-root`; clip phải chứa ≥200 ảnh khác nhau. Bbox/tape/pose lấy từ bộ 15/10, không dùng pose mới ngày 23/11 cho ảnh cũ. Output private có `manifest.json`, `inputs.npz`, `reference.npz`, `torch.npz`, `laptop.json`. Hash source giữ phiên bản adapter cố định giữa prepare/compare; nếu source/model/calibration đổi thì prepare một bundle mới.

## DQK chạy trên Nano và gửi lại

Gói input hiện giữ riêng trên máy HNHL tại `data/stage_a_nano_handoff_1125.zip`, theo convention của `tools.team_data`. Gói chỉ chứa `manifest.json` và `inputs.npz`; không cần mang PyTorch/ORT hay raw reference lên Nano. [Receipt/hashes](week-08/stage_a_handoff.json). PR có code và số liệu tổng hợp; quyền công bố bộ input ảnh lên GitHub chưa được xác nhận. Cần bàn giao riêng gói này qua kênh chia sẻ dữ liệu của nhóm sau khi xác nhận quyền chia sẻ. Người đã có raw D1 cũng có thể chạy `prepare` để tạo bundle mới cùng reference tương ứng.

Giải nén trên laptop bằng môi trường Python hiện có, rồi copy hai file vào `/workspace/stage_a` của Nano:

```powershell
.venv/Scripts/python.exe -m tools.team_data unpack data/stage_a_nano_handoff_1125.zip data/stage_a_nano_inputs
```

Nhận ONNX và build engine theo [hướng dẫn model](W8-ISSUE-139-USAGE.md). Sau đó, trong môi trường TensorRT/PyCUDA trên Nano, dùng code của PR này:

```bash
python3 jetson/stage_a_parity_run.py --bundle /workspace/stage_a --onnx /workspace/yolov8n_320_op11.onnx --engine /workspace/yolov8n_320_op11_fp16.engine --out /workspace/stage_a_trt_1126
```

Runner Python 3.6 gửi từng tensor fixed-shape cho engine, giữ đúng thứ tự frame, từ chối sai hash/shape và NaN/Inf. Output gồm `raw.npz`, `result.json` với engine/ONNX/input/output hashes và phiên bản TensorRT. Hash ONNX xác định build source do người chạy cung cấp; cần giữ build log để kiểm tra engine thực sự xây từ file đó. Không có motor I/O.

Nhờ DQK gửi lại **cả hai file**, build log và JetPack/TensorRT version. HNHL lưu vào `data/stage_a_trt_1126` rồi chạy:

```powershell
.venv/Scripts/python.exe -m tools.stage_a_parity compare --bundle data/stage_a_2026-11-25_release --candidate-dir data/stage_a_trt_1126 --report reports/HuynhNguyenHoaiLoc/week-08/stage_a_trt_d1.json
```

Comparator kiểm tra provenance, thứ tự, raw hash, code/calibration và ảnh gốc. Gate conversion yêu cầu ≥200 frame, cosine mọi frame ≥0,999, ≥95% bbox khớp cùng class tại IoU ≥0,9 và số bbox bằng nhau trên từng frame. Distance dùng cùng adapter laptop để tách lỗi model; chưa kiểm tra module ground/repulsion Python 3.6 của KR. Robot-module parity, fallback ≤1 s, disconnect stop ≤350 ms và 5×3 phút không va chạm là các kiểm tra riêng trước G2 ngày 29/11.

Chưa có engine/output mới từ DQK tại thời điểm báo cáo. Số TensorRT aggregate cũ tháng 10 không xác minh được model/input hashes của gói mới, nên không dùng thay kết quả này.
