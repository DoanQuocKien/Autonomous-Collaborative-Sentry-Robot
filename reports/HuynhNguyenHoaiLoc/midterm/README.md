# Hồ sơ giữa kỳ HNHL

Snapshot **01/11/2026**, dựa trên code/evidence hiện có. Hồ sơ này là phần HNHL để KR tổng hợp; không phải báo cáo cuối của toàn nhóm. Báo cáo nhóm 10–15 trang, nộp 23/11; thí nghiệm/hình chốt 16/11, full draft 18/11. Chương 5 có ngân sách chung khoảng 3,5 trang với đóng góp KR/DQK.

**Cập nhật 03/11:** [Đối chiếu tuần 5](week-05-audit.md) xác nhận PR #92 đã merge, nhưng T1 D3 và combined GPU RTX4050 còn chờ. [Bổ sung giữa kỳ 03/11](update-2026-11-03.md) có baseline từng model RTX4050/5060, D5 per-class P/R, log đường truyền/watchdog, runtime Jetson/ESP32 và F15 đo điểm cuối từ PR #94. Word/Markdown 01/11 dưới đây giữ nguyên như snapshot đã kiểm tra; editor đọc thêm bản bổ sung trước khi ghép.

## Tài liệu để ghép báo cáo

- [Chương 5 dạng Word](HNHL-Chuong-5.docx): bản ngắn, có F9/F10/F13 và nguồn E01–E12, chỉnh sửa được.
- [Chương 5 dạng Markdown](chapter-05.md): cùng nội dung, dễ review trong Git.
- [Các dòng kết quả cho Chương 7](chapter-07-rows.md): có trạng thái và giới hạn nghiệm thu.
- [Phần phụ lục code](code-appendix.md): module, kiểm thử, cách chạy; KR điền link tag midterm khi có.
- [Danh mục bằng chứng](evidence.md), [metrics snapshot](metrics.json): nguồn và SHA256 để đối chiếu từng số.
- [Checklist cập nhật](update-checklist.md): dữ liệu cần thêm, lệnh đánh giá và các mục phải sửa khi có kết quả mới.

Bản Word dài 3 trang là bản đóng góp để editor chọn/rút gọn. Khi ghép đầy đủ phần cửa của KR và deployment của DQK, nhóm cần dàn lại trong ngân sách chung 3,5 trang; số trang của bản riêng không phải số trang đã chốt cho báo cáo nhóm.

## Hình hiện có

| Hình | Nội dung hiện dùng | Trạng thái |
| :-- | :-- | :-- |
| [F9](figures/F9_gpu.png) | Model cùng nạp trên RTX5060; mỗi frame và scheduled door | Đã có số đo workload; chưa thay RTX4050/live acceptance |
| [F9 bổ sung](figures/F9_single_models.png) | Từng model trên RTX4050 và RTX5060, recorded power limits khác nhau | Có baseline cả hai thiết bị; chưa phải controlled GPU comparison |
| [F10](figures/F10_distance.png) | Scatter median Z theo ID, thống kê error; 8/9 ID có distance; held-out tách riêng | Đã dựng từ E01; thiếu full T1/floor controls |
| [F13](figures/F13_face_roc.png) | ROC D2 thật tại threshold0,45 | Pilot, nhãn tự động cần review; chưa đạt target |
| F7 | Video latency CDF JetBot thật | Chờ raw CSV clock-synced; không dùng localhost CDF thay thế |
| F11 | Map và sweet spot trên sweep thật | Chờ pose, door range/world truth và map artifacts |
| F14 | OSNet rank-1/CMC/ROC hợp lệ | Chờ gallery body crops và D2/D3 protocol |
| F18 | FP32/FP16 trước và sau tối ưu | Chờ phép so latency/memory/accuracy trên cùng dữ liệu |

F12 và phần nhận diện cửa do KR/DQK xác nhận, F20/F21 do DQK hoàn thiện. Chưa tạo hình map hoặc re-ID giả chỉ để đủ số lượng hình. Các hình này không chứa ảnh cá nhân.

## Phạm vi đã làm

Phần phương pháp, code, các so sánh đã chạy, thất bại hiện tại và hướng tiếp theo đã được viết để có thể bắt đầu ghép báo cáo. Kết quả chưa đạt được giữ nguyên: Wire, face pilot, các mode GPU mỗi-frame và các tiêu chí chưa đo. Bộ kiểm thử tuần5: 584 CPU/4 GPU passed, không phải chứng nhận D3 hoặc robot.

Không tự xác nhận timesheet, số liệu đối tác hay tag nộp bài. Hồ sơ chưa được gửi qua email/chat cho KR. Raw D1/D2, embeddings, predictions, weights và bản render QA nằm ngoài Git trong data/.

## Cách tạo lại

```powershell
.venv/Scripts/python.exe -m tools.build_midterm_hnhl
.venv/Scripts/python.exe -m tools.build_midterm_hnhl_update
.venv/Scripts/python.exe -m tools.check_midterm_hnhl --out reports/HuynhNguyenHoaiLoc/midterm/update-verification.json
# Dùng document-authoring runtime có python-docx, không dùng Python robot:
<document-python> tools/export_midterm_hnhl_doc.py
```

Sau export Word phải render lại tất cả trang và kiểm tra layout trước khi đưa vào báo cáo. Bản hiện tại kiểm tra bằng Microsoft Word trên Windows và rasterizer của document runtime; QA page images/PDF chỉ là intermediates trong data/midterm_qa. Không cần chạy lại model để vẽ lại số đo cũ. Nếu nguồn metrics hoặc nội dung thay đổi, sửa snapshot/narrative rồi kiểm tra lại; không ghi đè dữ liệu thí nghiệm lịch sử.

Kết quả đối chiếu hashes, links và kiểm tra bố cục 3 trang: [verification.json](verification.json). Log test 584 CPU/4 GPU là bằng chứng W5 có sẵn, không ghi là vừa chạy lại trong lần biên soạn này.

Đợt 03/11: [update-verification.json](update-verification.json) kiểm tra 20 nguồn, số liệu snapshot, liên kết nội bộ và hash Word. F9 single-model đã xem trực quan; checker không tự tuyên bố visual review cho một hình mới. Hash evidence chuẩn hóa CRLF → LF để tái lập qua Git trên Windows/Linux; hash DOCX/PNG giữ nguyên binary bytes. Word 01/11 vẫn cùng hash đã render/review, không cần tạo lại chỉ để đổi ngày. Nếu sửa Word hoặc nội dung gốc thì phải render lại.
