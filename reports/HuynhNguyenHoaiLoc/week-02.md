# HNHL — Báo cáo tuần 2: vật cản, bản đồ, vị trí quan sát

**Cập nhật 2026-10-17:** đã xử lý thử nghiệm [issue #43](ISSUE-43-HNHL.md) trên dữ liệu DQK 15/10, bổ sung semantic floor và tiled YOLO-World; có kết quả và giới hạn mới. [Nội dung PR bổ sung](PR-I43-HNHL.md). Các mục dưới đây lưu kết quả phiên 12/10, không thay báo cáo issue mới.

Kiểm chứng **2026-10-12**, Asia/Bangkok. Nhánh `HuynhNguyenHoaiLoc/w02-obstacles-map-vantage` đã fast-forward tới **`8d8aeaa`**, cùng `origin/main`, gồm PR #32 DQK và #33 KR. W2 ban đầu đã merge qua PR #27; các sửa đổi bổ sung bên dưới **chưa commit/push**. T1/T2 chưa nghiệm thu đầy đủ.

## Triển khai và lưu ý DQK

| Hạng mục | Kết quả |
| :-- | :-- |
| Camera | Undistort giữ K gốc; ground projection pitch/roll; pose theo session |
| Vật cản | YOLO furniture; repulsive w; bbox cắt bất kỳ mép ảnh đều unresolved |
| Sàn bóng | Ước lượng contact bằng đối xứng phản chiếu; texture/peak không rõ thì từ chối distance |
| Bản đồ | UNKNOWN/FREE/OCCUPIED; world pose + camera offset; FREE từ footprint đã đi hoặc seen_floor xác nhận |
| Vantage | FREE reachable, clearance, LOS, cách cửa 1,5–3 m; ưu tiên boundary đã quan sát |
| Offline/T1 | Replay bắt buộc pose mỗi frame; forward tape metric tách glossy/matte, báo ID thiếu |
| Tích hợp | RobotPose KR qua prescan/map; helper cửa cần range đo được, không mặc định 2 m |

Pose cũ `camera_pose_nowedge.json`: H=0,1013 m, pitch=+2,63°. Session lớp học sau khóa mount dùng **`calib/camera_pose_classroom_locked.json`: H=0,100 m, pitch=−2,33°** (camera nhìn lên), RMS=0,008 m. File này không có `passed`; loader yêu cầu bằng chứng tape/fit và ghi `measured_session_without_pass_flag`, không tự thêm PASS. Không dùng pose session cũ cho ảnh mới.

Tape DQK là **forward Z từ điểm trên sàn ngay dưới lens**, đối chiếu `forward_m`; không chuyển thành `hypot(forward,left)`. `distance_m` vẫn là planar range cho repulsion. Khi roll=0: `Z=H/tan(pitch+atan((v-cy)/fy))`.

Contact estimator glossy là heuristic có ngưỡng cấu hình; correlation không phải xác suất đúng. Vật phẳng dùng bbox contact khi caller/annotation xác nhận `flat_on_floor`, không tự suy ra từ class. Floor mặc định `unknown` giữ unresolved. Bbox cắt mép hoặc phản chiếu chưa giải quyết không cung cấp ground point cho map.

UNKNOWN chặn travel/LOS; occupied không bị floor rays xóa. `seen_floor` cần xác nhận độc lập, chưa có automatic floor segmentation. Map extent cố định, chưa suy ra coverage toàn phòng. Camera offset và footprint vẫn cần đo theo gốc pose KR.

## Kiểm chứng sau merge

Python 3.12.15, OpenCV 5.0.0, torch 2.9.1+cu128, Ultralytics 8.4.172, CUDA 12.8, **RTX 5060 Laptop GPU**; không thay baseline RTX 4050.

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-w2-merged-final -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m tools.check_w2 --out reports/HuynhNguyenHoaiLoc/week-02/inference_merged_final.json
.venv/Scripts/python.exe -m pytest tests/test_w2_gpu.py --basetemp=data/pytest-w2-merged-gpu -p no:cacheprovider -q
```

| Kiểm tra | Kết quả |
| :-- | :-- |
| Regression + integration | **321 passed**, 2 skipped, 1 deselected; **27,44 s** |
| Skip | Checkerboard D1 và entrance replay D1 chưa có local |
| GPU test | **1 passed**, **5,06 s**, CUDA FP32 |
| Detector smoke | 3 warmup / 10 mẫu; p50 **16,519 ms**, p95 **23,125 ms** |
| XFeat | Weights khớp pinned SHA256; ca warped-reference thật đạt |
| Import / cú pháp | Package exports tải đủ; common/jetson đạt AST Python 3.6 |

Bằng chứng: [test log](week-02/tests_merged_final.txt), [GPU log](week-02/tests_gpu_merged_final.txt), [inference JSON](week-02/inference_merged_final.json), [stdout](week-02/inference_merged_final.txt). Logs trước merge giữ để đối chiếu, không phải kết quả của HEAD mới.

Tests gồm projection ngang/nghiêng/roll/signed pitch; session pose thiếu flag và validation; reflection/abstention/mép ảnh; rays/occlusion/clearance/save-load; replay seq reset; forward metric, floor groups, lateral chưa xác nhận; RobotPose qua prescan có camera offset; bearing thiếu range không tạo tọa độ cửa giả.

Smoke dùng ảnh camera-pose cũ đã có trong repo cùng pose cũ, floor `unknown`; kiểm tra runtime và abstention, không đo accuracy setup 1. Latency gồm undistort + YOLO preprocessing/inference/postprocessing + contact/projection, chưa gồm map/vantage/transport/motor. 10 mẫu chưa phải benchmark ổn định. Không có motor commands.

## Dữ liệu DQK setup 1

ZIP riêng ngày 2026-10-12 lưu ở `data/dqk-obstacles-2026-10-12`, được Git ignore. Raw ảnh và manual ROI không đưa lên repo public. [Diagnostic tổng hợp](week-02/dqk_setup1_diagnostic.json).

Ba ROI thủ công glossy cho median/p90 forward error **5,99% / 9,52%** sau xử lý contact; bbox bottom thô là **17,37% / 19,27%**. Đây là diagnostic hình học: ngưỡng đã khảo sát trên cùng ảnh, sleeve được xác nhận phẳng; chưa phải held-out accuracy hoặc detector recall. YOLO thực tế có 2 furniture candidates, chỉ 1 contact hợp lệ, 1 bbox cắt mép bị từ chối. Model COCO không bảo đảm nhận wooden block/sleeve.

Chưa có matte, chưa đủ 20 IDs, chưa có world truth/poses xác nhận để chấm map. Lateral ghế phải đang cần DQK kiểm tra: dùng forward đã xác nhận nhưng không dùng lateral đó làm map truth.

## Nghiệm thu còn chờ

| Tiêu chí | Trạng thái |
| :-- | :-- |
| T1 forward median ≤10%, p90 ≤20%, 0,3–2 m | Có diagnostic setup 1; chờ ≥20 IDs, matte và nhãn khớp detection |
| T1 map ≥80% của ≥20 obstacles trong 20 cm | Chờ world truth + pose, camera offset đo được |
| T2 repulsion: 0 collisions trong 5×3 phút | Chờ robot DQK |
| T2 vantage đủ 3 điều kiện 5/5 | Modules đã có; chờ room enrollment/range/floor evidence và robot |

Entrance hiện dùng XFeat/DINOv2 theo code DQK, không còn ORB baseline. XFeat local weights đã có; DINOv2 chưa tải/cache và không chạy trong lần kiểm tra này. Chưa có D1 entrance replay trên máy. `TiltFilter` DQK đã có, nhưng detector HNHL dùng pose JSON theo session, chưa tự cập nhật tilt từng frame.

Evaluator lấy median theo ID rồi median/p90 chung và từng sàn; thiếu estimate/floor set không tạo PASS. Map dùng nearest occupied cell centre, chưa đánh giá precision/recall. [Protocol/API](W2-USAGE.md), [nội dung PR bổ sung](PR-W2-HNHL.md), reviewer DQK. Definition of Done còn cần T1/T2 và review/merge sửa đổi mới.
