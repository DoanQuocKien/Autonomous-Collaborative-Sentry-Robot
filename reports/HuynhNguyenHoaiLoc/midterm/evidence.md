# Danh mục bằng chứng HNHL

Snapshot biên soạn 01/11/2026; không chạy lại model. Số đo giữ phạm vi và điều kiện gốc. SHA256 dùng source bytes sau chuẩn hóa CRLF thành LF; các byte khác giữ nguyên, nên checkout Windows/Linux cho cùng hash.

| Mã | Nguồn trong repo | SHA256 |
| :-- | :-- | :-- |
| E01 | [chairs_semantic.json](../../../reports/HuynhNguyenHoaiLoc/week-02/issue-43/chairs_semantic.json) | `6936d5a1a77ff9250b0504f2f4ba70c8149c7e1a45f3450fc8eeb3168bbacb0f` |
| E02 | [d5_corrected_validation.json](../../../reports/HuynhNguyenHoaiLoc/week-04/d5_corrected_validation.json) | `c094f15ef2db9d21ed89d626d38fc7cf21c3afea70ff85d81263369b5cdcd828` |
| E03 | [d2_pilot.json](../../../reports/HuynhNguyenHoaiLoc/week-04/d2_pilot.json) | `3024bea82958c39c1ce72524e13affa933011aac5a276606b3440cfe35971367` |
| E04 | [d2_tracking_runtime.json](../../../reports/HuynhNguyenHoaiLoc/week-05/d2_tracking_runtime.json) | `6d419c587c3e1445c48fd50575ef22d481b9e9759903fd17f559cf265ed5b670` |
| E05 | [pipeline_both.json](../../../reports/HuynhNguyenHoaiLoc/week-05/pipeline_both.json) | `d718ed31ea0dc4d04796c73ff9a39d6a0e2c63c8c6ff4a70b43240b157df4686` |
| E06 | [pipeline_xfeat.json](../../../reports/HuynhNguyenHoaiLoc/week-05/pipeline_xfeat.json) | `55e6275de93558cde4c61a64a974f5b02eacd69fc62f897834d2094abab45d49` |
| E07 | [pipeline_both_5hz.json](../../../reports/HuynhNguyenHoaiLoc/week-05/pipeline_both_5hz.json) | `58b6504a28f1f998995461ba04d1bb526bef8c7ca3ea1a3c3f188e4d5d24dd03` |
| E08 | [d5_onnx_real_parity.json](../../../reports/HuynhNguyenHoaiLoc/week-04/d5_onnx_real_parity.json) | `62c21b2f977335021dd90bbb566b6dc3f8292aa35a2420862b7dac93688107a3` |
| E09 | [parity_results.json](../../../reports/DoanQuocKien/week-04/edge_parity/parity_results.json) | `89cb8814602beb2b53e1b6224c52a3f7f13dbf9f380ba09cefb4bf39a377a3c2` |
| E10 | [gpu_baseline.json](../../../reports/HuynhNguyenHoaiLoc/week-01/gpu_baseline.json) | `6ac109a8ea1e85de317cb0bf4894aec9ce606537e92c5599046978850790d416` |
| E11 | [pytest_cpu.log](../../../reports/HuynhNguyenHoaiLoc/week-05/pytest_cpu.log) | `bce97a9bf81830bc9ce7d3bed71412f634fe93d2f1781420cbc8f4b2e8fa9b7e` |
| E12 | [pytest_gpu.log](../../../reports/HuynhNguyenHoaiLoc/week-05/pytest_gpu.log) | `5b2eae6ab722f065484bc5038d96f9a2c4cf7855c27de6b0ff886195466f844e` |

Không đổi pilot/dev-val thành T1. F10 dùng 8 ID có estimate và báo ID21 thiếu; điểm scatter là median khoảng cách theo ID, thống kê error giữ cách tổng hợp của report gốc.
F9 single-model W1 dùng PyTorch allocator; F9 combined W5 dùng NVML toàn thiết bị. Không ghép hai số memory thành cùng loại phép đo.
metrics.json ghi null cho rank-1/ID switches chưa đo. Số nhãn tự động D2 chưa được coi là ground truth đã nghiệm thu.
