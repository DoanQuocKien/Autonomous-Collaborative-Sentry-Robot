# Kết quả HNHL để ghép Chương 7

**Bổ sung10/11:** retest ghế lớp09/11 cho4/36 frame detection và0/36 distance (giữ error=null). Đây là kết quả failure/coverage mới, không thay8/9 IDs F10 cũ hoặc gộp hai tape origins. Depth/zoom/floor-anchor chưa transfer; trunk một người có per-set bias,0,49m và0,50m là protocol khác. [Bảng nguồn/so sánh](update-2026-11-10.md), [F10 availability](figures/F10_availability_1109.png). Không có T1/T2 PASS mới; không đổi default detector.

**Đối chiếu bản sửa KR969a5e0 ngày09/11:** Chương7 của draft vẫn ghi distance “ĐẠT T1”; phải đổi sang kết quả bộ nhỏ/partial pending vì p90=20,91%, chỉ8/9 IDs và chưa≥20. Các sửa scope/links khác đã có, không yêu cầu làm lại. [Theo dõi review mới](followup-pr101-2026-11-09.md); chưa có experimental acceptance mới.

**Hiện hành09/11:** [nguồn mới và đính chính](update-2026-11-09.md). DQK rút lại giả thuyết mount-slip/foot-stance; nguyên nhân ranging vẫn chưa rõ. `home_6_1` log≈1,27m nhưng tape1,77m, chưa accuracy/T2 PASS. Link-cut có5 video stop-proxy, median516ms/range481–524ms; chưa đo mechanical stop hoặc chứng minh≤350ms, trial4 có R1 end=0. KR có Phase3 T0/bản thảo nhưng còn findings ở #101; không thay D3 hoặc robot acceptance. D3/gallery/D5 độc lập/F11/F7 raw/combined4050 vẫn pending. [Sửa claim và figure paths cho editor](HNHL-EDITOR-CORRECTIONS-1109.md).

**Bổ sung 07/11 từ DQK:** [home pilot và camera/tape diagnostics](update-2026-11-07.md). Pose mới pitch −4,68..−4,49°, roll biến thiên chưa giải thích; readings tại tape 1,2/1,8/2,4 m được DQK báo 1,02/1,57/1,63 m. `home_4_1` có 362 log rows, logged HOLD tại 7,45 s và một tape endpoint 1,25 m do DQK báo, chưa time-aligned. Không dùng `home_1_3` in-band đã withdraw hoặc `home_3_1` start-near để báo pursuit PASS. PR nguồn #99 chưa merge; đây không phải kết quả HNHL chạy robot hoặc full T1/T2.

**Trạng thái 06/11:** DQK báo camera sửa socket gốc, stream hoạt động khoảng 18,6 FPS; chưa có raw repair log hoặc HNHL HIL để xác minh. Camera mất stream đã được báo khắc phục, nhưng self-pose/height phải kiểm tra lại trước run được tính. Không dùng phép kiểm tra stream này làm F7 latency, D3 tracking hoặc T2 PASS. Adapter recording→D3 manifests đã qua T0, chưa có reviewed D3 mới. [Nguồn và cập nhật hiện hành](update-2026-11-06.md).

**Bổ sung mới nhất 05/11:** [F18 và trạng thái sau PR #98](update-2026-11-05.md). Dòng mới để ghép: native PyTorch FP32/FP16 D5-640 trên RTX5060 đạt 123,59/107,38 FPS, p95 12,01/16,35 ms, Torch peak allocated 32,41/17,53 MiB; mAP50 81,071%/81,072% trên cùng 90 ảnh dev-val. FP16 chưa tăng tốc; chưa TensorRT/independent T1. Camera JetBot hỏng: các thử nghiệm cần video bị chặn. G2 chưa đạt, không làm Stage A/B mới trước giữa kỳ. Các kết quả lịch sử dưới đây giữ nguyên.

Snapshot 01/11/2026. Mã E01–E12 tra tại [evidence.md](evidence.md). “Đã đo” mô tả bằng chứng, không mặc định đồng nghĩa đạt nghiệm thu. KR có thể rút gọn các dòng này trong ngân sách chung 1,5 trang của Chương 7.

Bổ sung 03/11: [bảng GPU từng model, D5 per-class và video/watchdog/Jetson](update-2026-11-03.md) cung cấp E13–E20. [Audit tuần 5](week-05-audit.md) cập nhật PR #92 đã merge; không dùng suite review nhánh KR để thay nghiệm thu D3 của HNHL.

| Thành phần | Kết quả hiện có | So với yêu cầu và giới hạn | Nguồn |
| :-- | :-- | :-- | :-- |
| Khoảng cách ghế glossy | 8/9 ID có distance; median/p90 5,34%/20,91%; 3 ID held-out 5,37%/17,11% | p90 tổng chưa đạt20%; chưa ≥20 IDs/đủ floor sets. Báo missed ID21, không chỉ báo subset tốt | E01, F10 |
| Fine-tune D5 | 397 ảnh; 307/90 cùng session; mAP50 320/416/640 =0,759/0,753/0,810 | Dev-val đã dùng chọn model/size, chưa independent T1. Giữ nguyên mục tiêu từng class | E02 |
| Wire | Recall0 tại validation operating point sau sửa nhãn/training lại | Chưa đạt80%; không có segmentation benchmark. 12 masks chỉ annotation pilot | E02 |
| Face whitelist | 125 face frames/21 entries/3 người; cosine0,45: TAR82,99%, FAR46,40% | Chưa đạt TAR95% tại FAR1%; nhãn largest-face và bystanders chưa review đầy đủ; frame queries tương quan | E03, F13 |
| OSNet re-ID | Cả AIN và x0.25 chạy được; 23 crop người không mơ hồ | Thiếu gallery ở2/3 người; chưa có rank-1/CMC/ROC hợp lệ hoặc model thắng; không đủ gate5 identities | E03 |
| Tracking | ByteTrack + appearance lock có API/tests; replay822 frame D2 hoàn tất | Runtime smoke, timestamp xấp xỉ; chưa có reviewed body IDs D3 nên ID switches và lock accuracy chưa đo | E04 |
| GPU workload RTX5060 | Đủ model mỗi frame12,72 FPS; XFeat mỗi frame14,25; đủ model với door schedule19,65, actual door4,52 Hz; NVML peak0,939 GiB full mix | Hai mode mỗi-frame chưa đạt15 FPS. Scheduled đạt cho workload đo, chưa RTX4050/dual-stream; crop padding và DINO FP16 ghi rõ | E05–E07, F9 |
| ONNX D5 conversion | 90/90 frame cùng count,294 reference boxes ghép đủ IoU≥0,9 | Parity laptop PyTorch/ORT, không phải accuracy hoặc TensorRT certification | E08 |
| Edge stock models DQK | Cosine≥0,999; YOLOv8n cùng count205/208 | Phần count nguyên văn chưa đạt; không thay parity của custom D5/OSNet-AIN. DQK xác nhận narrative thiết bị | E09 |
| T0/GPU checks | 584 CPU tests +4 GPU tests passed | Hai skip do D1 local thiếu; tests không thay T1/T2. Không motor commands trong phiên HNHL | E11–E12 |
| Map/vantage và T2 | Có code và tests logic | Chưa có map evaluation/sweep truth hoặc run robot đủ protocol để nghiệm thu | W2/W5 reports |

## Bổ sung baseline model riêng

Baseline W1 RTX5060 (ảnh tổng hợp640, batch1 FP32,10 warmup/100 iterations, nguồn AC/battery chưa xác nhận): YOLOv8n49,18 FPS/p95 27,02ms; YOLOv8s26,06 FPS/p95 40,74ms. Đây là phép đo riêng từng model, không so ngang với throughput W5 theo điều kiện hoàn toàn giống nhau. Memory W1 là PyTorch allocator, W5 là sampled NVML toàn thiết bị. Nguồn E10; số đo RTX4050 từ DQK cần đặt ở cột thiết bị riêng.

## Cách diễn đạt trong báo cáo

Có thể ghi: “Pipeline đã được triển khai và kiểm tra runtime; một số chỉ tiêu accuracy và thử robot chưa hoàn tất.” Không ghi “hệ thống đạt toàn bộ yêu cầu”, “re-ID rank-1 đạt85%”, “tracking ≤1 ID-switch/phút” hoặc “GPU target RTX4050 đạt” khi chưa có phép đo tương ứng.
