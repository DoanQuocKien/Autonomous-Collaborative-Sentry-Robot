# F18 — native PyTorch FP32/FP16, đo sớm ngày 05/11/2026

**Bổ sung09/11:** [đính chính DQK, stop-proxy và bản thảo KR](../midterm/update-2026-11-09.md). Sau builder07/11 chạy `tools.build_midterm_hnhl_nov09`, rồi checker. Archive đã commit thì không dùng lại `--import-source`. F18 dưới đây giữ nguyên phép đo05/11; các nguồn mới không tạo thêm accuracy hoặc robot PASS.

**Bổ sung 07/11:** [pilot/pose/tape của DQK và audit phần nhóm đã làm](../midterm/update-2026-11-07.md). Sau các builder 05/11 và 06/11, chạy `tools.build_midterm_hnhl_team_update` rồi checker để bản hiện hành giữ trạng thái mới nhất. Bản archive nguồn đã có trong Git; không chạy lại `--import-source` hoặc model chỉ để tái tạo hình.

**Cập nhật 06/11:** [camera đã sửa và D3 adapter](../midterm/update-2026-11-06.md), [27 targeted CPU tests](tests_recovery_2026-11-06.log). Phép đo F18 dưới đây giữ nguyên ngày/protocol, không chạy lại để đổi ngày. Tạo lại addenda theo thứ tự `build_midterm_hnhl_followup`, `build_midterm_hnhl_recovery`, rồi `check_midterm_hnhl` để bản Chương 5 hiện hành phản ánh camera repaired.

Đầu việc tối ưu dự kiến tuần 6, chạy bằng dữ liệu hiện có trong tuần 5. [Metrics đầy đủ](d5_precision_2026-11-05.json), [log CPU regression](tests_cpu_2026-11-05.log), [FP32 validator](fp32_2026-11-05.log), [FP16 validator](fp16_2026-11-05.log). Kết luận, hình và đoạn ghép Chương 5: [addendum 05/11](../midterm/update-2026-11-05.md).

```powershell
$env:YOLO_CONFIG_DIR = Join-Path (Get-Location) 'data/ultralytics'
$env:YOLO_AUTOINSTALL = 'false'
.venv/Scripts/python.exe -m tools.compare_d5_precision `
  --weights runs/d5_w04_corrected/yolov8n_640/weights/best.pt `
  --data data/D5_yolo_w04/data.yaml --imgsz 640 --warmup 10 --repeats 3 `
  --work-dir data/midterm_fp16_1105 `
  --out reports/HuynhNguyenHoaiLoc/week-06/d5_precision_2026-11-05.json
```

Đó là lệnh đã chạy. Muốn chạy lại phải chọn `--work-dir` và `--out` mới; tool từ chối ghi đè. Checkpoint và D5 raw/export private không được commit; hashes cần khớp metrics. Tool chỉ đọc dataset gốc, copy 90 ảnh/nhãn validation vào work-dir; validator chỉ viết cache ở bản sao. Hai precision chạy process riêng, cùng ảnh và nhãn, 270 timing samples/precision. CUDA input và parameter dtype được kiểm tra trong cả `predict` lẫn validation. Không tải model qua mạng, không train, không đổi config live và không có motor commands.

Kết quả: FP32/FP16 123,59/107,38 FPS; p95 12,01/16,35 ms; Torch peak allocated 32,41/17,53 MiB. Đây là synchronized `predict()` trên ảnh BGR đã decode (gồm preprocess/NMS và hook kiểm tra dtype), không phải raw GPU-kernel time hoặc toàn pipeline. P/R của validator là best-F1 dev operating point, không dùng làm frozen deployment threshold. `rect=False`, batch 1 trong cả hai precision; số accuracy cũ E02 có batch/rect khác nên không dùng làm baseline paired.

Không có bằng chứng FP16 nhanh hơn trong lần chạy này. Dữ liệu 24/10 cùng session, đã dùng chọn checkpoint; không independent T1, RTX4050 hoặc TensorRT/Nano. Nguồn AC/battery chưa xác nhận; thứ tự FP32 rồi FP16 và thermal không kiểm soát, không kết luận chung từ một lần đo. Các nghiệm thu wire, independent D5, re-ID, tracking D3, map và robot vẫn chờ.

```powershell
.venv/Scripts/python.exe -m pytest -m 'not gpu and not hil' --basetemp=data/pytest-midterm-1105 -p no:cacheprovider -q -rs
.venv/Scripts/python.exe -m tools.build_midterm_hnhl_followup
.venv/Scripts/python.exe -m tools.check_midterm_hnhl --out reports/HuynhNguyenHoaiLoc/midterm/update-verification.json
```

CPU suite ngày 05/11: **633 passed**, 2 skipped (checkerboard và entrance D1 classroom thiếu), 4 GPU deselected, 29,76 s. Phép đo CUDA ở trên đã thực thi riêng, không lấy số deselected làm GPU test pass. Chưa có motor/HIL hoặc dữ liệu D3 mới.
