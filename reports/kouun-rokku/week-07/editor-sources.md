# Editor source registry — 14/11/2026

Nguồn định lượng của bản report 14 trang. Hash từng file trong [JSON](editor-source-registry.json).
`python -m tools.check_midterm_sources` kiểm tra drift và links của bản ghép.

PR #108 vẫn mở tại snapshot: DQK commit `054d2adc8aabe0ce33b0cdbff40e8b936b232c85`.
Các source DQK được archive với SHA256; riêng README có mật khẩu cũ đã che và ghi transformation trong provenance. Markdown lưu `.md.txt` để phân biệt source với bản editor.
Không lấy source owner-reported để nhận code PR #108 hoặc tự nâng kết quả thành T1/T2.

K3 là log checkout sạch/package được thêm sau candidate commit; không trộn với log #101 trước đó.

| ID | Source | Scope |
| :-- | :-- | :-- |
| S0 | [docs/Implementation Plan.md](../../../docs/Implementation%20Plan.md) | committed source in candidate; historical measurements retain their original date/tier |
| S0 | [docs/Mid-Term Report Plan.md](../../../docs/Mid-Term%20Report%20Plan.md) | committed source in candidate; historical measurements retain their original date/tier |
| C1 | [calib/camera.json](../../../calib/camera.json) | committed source in candidate; historical measurements retain their original date/tier |
| C2 | [reports/DoanQuocKien/week-03/t2_dead_reckoning/README.md](../../DoanQuocKien/week-03/t2_dead_reckoning/README.md) | committed source in candidate; historical measurements retain their original date/tier |
| H1 | [reports/HuynhNguyenHoaiLoc/midterm/chapter-05-current.md](../../HuynhNguyenHoaiLoc/midterm/chapter-05-current.md) | committed source in candidate; historical measurements retain their original date/tier |
| H1 | [reports/HuynhNguyenHoaiLoc/midterm/evidence.md](../../HuynhNguyenHoaiLoc/midterm/evidence.md) | committed source in candidate; historical measurements retain their original date/tier |
| H1 | [reports/HuynhNguyenHoaiLoc/midterm/update-2026-11-05.json](../../HuynhNguyenHoaiLoc/midterm/update-2026-11-05.json) | committed source in candidate; historical measurements retain their original date/tier |
| H2 | [reports/HuynhNguyenHoaiLoc/midterm/update-2026-11-10.md](../../HuynhNguyenHoaiLoc/midterm/update-2026-11-10.md) | committed source in candidate; historical measurements retain their original date/tier |
| H2 | [reports/HuynhNguyenHoaiLoc/midterm/update-2026-11-11.json](../../HuynhNguyenHoaiLoc/midterm/update-2026-11-11.json) | committed source in candidate; historical measurements retain their original date/tier |
| H2 | [reports/HuynhNguyenHoaiLoc/midterm/update-2026-11-11.md](../../HuynhNguyenHoaiLoc/midterm/update-2026-11-11.md) | committed source in candidate; historical measurements retain their original date/tier |
| K1 | [reports/kouun-rokku/week-04/sector_accuracy.json](../week-04/sector_accuracy.json) | committed source in candidate; historical measurements retain their original date/tier |
| K1 | [reports/kouun-rokku/week-05/bytetrack_parity.json](../week-05/bytetrack_parity.json) | committed source in candidate; historical measurements retain their original date/tier |
| K1 | [reports/kouun-rokku/week-05/hold_detector_metrics.json](../week-05/hold_detector_metrics.json) | committed source in candidate; historical measurements retain their original date/tier |
| K1 | [reports/DoanQuocKien/week-02/d1/entrance_bench_robot_ref.json](../../DoanQuocKien/week-02/d1/entrance_bench_robot_ref.json) | committed source in candidate; historical measurements retain their original date/tier |
| K2 | [reports/kouun-rokku/week-06/phase3_replay_summary.json](../week-06/phase3_replay_summary.json) | committed source in candidate; historical measurements retain their original date/tier |
| K2 | [reports/kouun-rokku/week-06/pr101-review-fixes.md](../week-06/pr101-review-fixes.md) | committed source in candidate; historical measurements retain their original date/tier |
| K2 | [reports/kouun-rokku/week-06/pr101-review-pytest.log](../week-06/pr101-review-pytest.log) | committed source in candidate; historical measurements retain their original date/tier |
| E1 | [docs/Edge Deployment.md](../../../docs/Edge%20Deployment.md) | committed source in candidate; historical measurements retain their original date/tier |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/midterm-chapter-03.md.txt](sources/reports/DoanQuocKien/midterm-chapter-03.md.txt) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/midterm-chapter-04.md.txt](sources/reports/DoanQuocKien/midterm-chapter-04.md.txt) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/midterm-chapter-05x.md.txt](sources/reports/DoanQuocKien/midterm-chapter-05x.md.txt) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/midterm-chapter-08.md.txt](sources/reports/DoanQuocKien/midterm-chapter-08.md.txt) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/classroom_1111_pm/README.md.txt](sources/reports/DoanQuocKien/week-06/classroom_1111_pm/README.md.txt) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/gpu_rtx4050_1113/pipeline_both.json](sources/reports/DoanQuocKien/week-06/gpu_rtx4050_1113/pipeline_both.json) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/gpu_rtx4050_1113/pipeline_both_5hz.json](sources/reports/DoanQuocKien/week-06/gpu_rtx4050_1113/pipeline_both_5hz.json) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/gpu_rtx4050_1113/pipeline_xfeat.json](sources/reports/DoanQuocKien/week-06/gpu_rtx4050_1113/pipeline_xfeat.json) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/figures/F7_video_latency.png](sources/reports/DoanQuocKien/week-06/figures/F7_video_latency.png) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/figures/F8_esp32_stream.png](sources/reports/DoanQuocKien/week-06/figures/F8_esp32_stream.png) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/figures/F22_drive_veer.png](sources/reports/DoanQuocKien/week-06/figures/F22_drive_veer.png) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/figures/F23_door_approach.png](sources/reports/DoanQuocKien/week-06/figures/F23_door_approach.png) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/figures/F25_d2_face_width.png](sources/reports/DoanQuocKien/week-06/figures/F25_d2_face_width.png) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/edge_bench_1113/stageB_person_1113.json](sources/reports/DoanQuocKien/week-06/edge_bench_1113/stageB_person_1113.json) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/edge_bench_1113/stageC600_live_esp32_seated_1113.json](sources/reports/DoanQuocKien/week-06/edge_bench_1113/stageC600_live_esp32_seated_1113.json) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/edge_bench_1113/stageC60_live_esp32_1113.json](sources/reports/DoanQuocKien/week-06/edge_bench_1113/stageC60_live_esp32_1113.json) | owner-reported; PR108 open; no code adopted |
| D13 | [reports/kouun-rokku/week-07/sources/reports/DoanQuocKien/week-06/edge_bench_1113/stageC60b_live_esp32_phone_closer_1113.json](sources/reports/DoanQuocKien/week-06/edge_bench_1113/stageC60b_live_esp32_phone_closer_1113.json) | owner-reported; PR108 open; no code adopted |
| Figure | [reports/DoanQuocKien/week-05/figures/F1_system_overview.png](../../DoanQuocKien/week-05/figures/F1_system_overview.png) | figure from committed owner evidence; caption defines tier/date |
| Figure | [reports/DoanQuocKien/week-05/figures/F4_fisheye_error.png](../../DoanQuocKien/week-05/figures/F4_fisheye_error.png) | figure from committed owner evidence; caption defines tier/date |
| Figure | [reports/DoanQuocKien/week-05/f15/F15_dead_reckoning.png](../../DoanQuocKien/week-05/f15/F15_dead_reckoning.png) | figure from committed owner evidence; caption defines tier/date |
| Figure | [reports/HuynhNguyenHoaiLoc/midterm/figures/F10_distance.png](../../HuynhNguyenHoaiLoc/midterm/figures/F10_distance.png) | figure from committed owner evidence; caption defines tier/date |
| Figure | [reports/HuynhNguyenHoaiLoc/midterm/figures/F13_face_roc.png](../../HuynhNguyenHoaiLoc/midterm/figures/F13_face_roc.png) | figure from committed owner evidence; caption defines tier/date |
| Figure | [reports/HuynhNguyenHoaiLoc/midterm/figures/F18_d5_precision.png](../../HuynhNguyenHoaiLoc/midterm/figures/F18_d5_precision.png) | figure from committed owner evidence; caption defines tier/date |
| Figure | [reports/DoanQuocKien/week-05/figures/F20_edge_engines.png](../../DoanQuocKien/week-05/figures/F20_edge_engines.png) | figure from committed owner evidence; caption defines tier/date |
| Figure | [reports/kouun-rokku/week-05/F16_state_machine.png](../week-05/F16_state_machine.png) | figure from committed owner evidence; caption defines tier/date |
| Figure | [reports/DoanQuocKien/week-05/figures/F19_test_growth.png](../../DoanQuocKien/week-05/figures/F19_test_growth.png) | figure from committed owner evidence; caption defines tier/date |
| Figure | [reports/HuynhNguyenHoaiLoc/midterm/figures/F10_availability_1109.png](../../HuynhNguyenHoaiLoc/midterm/figures/F10_availability_1109.png) | figure from committed owner evidence; caption defines tier/date |
