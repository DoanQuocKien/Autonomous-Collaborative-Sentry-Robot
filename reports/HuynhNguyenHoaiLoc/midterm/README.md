# Hồ sơ giữa kỳ HNHL

**Mới nhất 09/11:** [audit PR và nguồn mới DQK/KR](update-2026-11-09.md), [các sửa đổi cụ thể cho editor](HNHL-EDITOR-CORRECTIONS-1109.md). DQK rút lại giải thích mount-slip/foot-stance; các run mới vẫn sai lệch với tape. Năm video stop-proxy có median516 ms, chưa chứng minh motor stop≤350ms; trial4 có R1 end=0. KR đã có Phase3 và bản thảo nhóm nhưng #101 còn lỗi stale/handoff/command legality. #99/#101/#102 đều request-changes; #100 chờ DQK. Lịch09/11 bị đề xuất dời, bỏ matte là proposal chưa merge; không tự đổi gate nghiệm thu. Đọc bản hiện hành09/11 thay cho các snapshot lịch sử dưới đây.

**Mới nhất 07/11:** [đối chiếu evidence của DQK/KR](update-2026-11-07.md) bổ sung pose camera sau sửa, distance diagnostic và [F17 home pilot](figures/F17_home_pilot.png). Nguồn ở PR #99 mới, chưa merge/request-changes; giữ rút kết quả `home_1_3`, không coi run `home_3_1` là pursuit test. Một HOLD endpoint 1,25 m do DQK báo chưa thay T2. Bảng audit chỉ rõ phần người khác đã làm và phần D3/re-ID/map/D5/RTX4050 vẫn thiếu.

**Mới nhất 06/11:** [camera đã sửa và chuẩn bị D3](update-2026-11-06.md). DQK báo sửa socket gốc, stream hoạt động; cần recheck và đo lại camera pose/height trước run được tính. Chưa có D3/gallery/independent D5 hoặc T1/T2 mới. Commit sửa camera ở nhánh #98 cũ đã tích hợp vào PR #100 để DQK review. Bản Chương 5 hiện hành dưới đây đã cập nhật trạng thái này; ghi chú camera-blocked ngày 05/11 là snapshot lịch sử.

**Mới nhất 05/11:** [addendum sau PR #98 và F18 đo thật](update-2026-11-05.md) cập nhật camera JetBot đang hỏng, G2 chưa đạt và lịch dự phòng. F18 so native PyTorch CUDA FP32/FP16 trên cùng 90 ảnh D5 development: FP16 giảm allocator nhưng chưa tăng tốc. PR #99 chưa merge; T1 D3/re-ID/independent D5 và T2 vẫn chờ. Editor ưu tiên trạng thái ở addendum này khi ghép; các snapshot cũ giữ để truy vết.

Snapshot **01/11/2026**, dựa trên code/evidence hiện có. Hồ sơ này là phần HNHL để KR tổng hợp; không phải báo cáo cuối của toàn nhóm. Báo cáo nhóm 10–15 trang, nộp 23/11; thí nghiệm/hình chốt 16/11, full draft 18/11. Chương 5 có ngân sách chung khoảng 3,5 trang với đóng góp KR/DQK.

**Cập nhật 03/11:** [Đối chiếu tuần 5](week-05-audit.md) xác nhận PR #92 đã merge, nhưng T1 D3 và combined GPU RTX4050 còn chờ. [Bổ sung giữa kỳ 03/11](update-2026-11-03.md) có baseline từng model RTX4050/5060, D5 per-class P/R, log đường truyền/watchdog, runtime Jetson/ESP32 và F15 đo điểm cuối từ PR #94. Word/Markdown 01/11 dưới đây giữ nguyên như snapshot đã kiểm tra; editor đọc thêm bản bổ sung trước khi ghép.

**Sau merge #96:** #93, #95 và #96 đều đã merge; xem [ghi chú tích hợp mới nhất](session-followup-2026-11-03.md) và [D3 handoff cho HNHL](D3-HANDOFF-HNHL.md). Bảng D5 bổ sung đủ gate precision/recall cho cả bags. Lịch 04/11/09/11/16/11 là kế hoạch thu thập, chưa có D3 hoặc nghiệm thu mới. Metadata GitHub E20 cũ được giữ làm snapshot lịch sử; trạng thái mới ở file session-followup.

## Tài liệu để ghép báo cáo

- [Chương 5 hiện hành, Markdown 09/11](chapter-05-current.md): hợp nhất kết quả HNHL, pilot và đính chính mới do DQK cung cấp; dùng để ghép nội dung hiện hành cùng gói sửa cho editor.
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
| [F17 bổ sung](figures/F17_home_pilot.png) | DQK home_4_1: estimated distance/centre và logged HOLD | Một người, endpoint tape chưa time-aligned; chưa full pursuit/HOLD T2 |
| [F18](figures/F18_d5_precision.png) | FP32/FP16 native PyTorch trên cùng D5-640, RTX5060 | Có paired dev latency/memory/accuracy ngày 05/11; chưa TensorRT/independent T1 hoặc toàn pipeline |

F12 và phần nhận diện cửa do KR/DQK xác nhận, F20/F21 do DQK hoàn thiện. Chưa tạo hình map hoặc re-ID giả chỉ để đủ số lượng hình. Các hình này không chứa ảnh cá nhân.

## Phạm vi đã làm

Phần phương pháp, code, các so sánh đã chạy, thất bại hiện tại và hướng tiếp theo đã được viết để có thể bắt đầu ghép báo cáo. Kết quả chưa đạt được giữ nguyên: Wire, face pilot, các mode GPU mỗi-frame và các tiêu chí chưa đo. Bộ kiểm thử tuần5: 584 CPU/4 GPU passed, không phải chứng nhận D3 hoặc robot.

Không tự xác nhận timesheet, số liệu đối tác hay tag nộp bài. Hồ sơ chưa được gửi qua email/chat cho KR. Raw D1/D2, embeddings, predictions, weights và bản render QA nằm ngoài Git trong data/.

## Cách tạo lại

```powershell
.venv/Scripts/python.exe -m tools.build_midterm_hnhl
.venv/Scripts/python.exe -m tools.build_midterm_hnhl_update
.venv/Scripts/python.exe -m tools.build_midterm_hnhl_followup
.venv/Scripts/python.exe -m tools.build_midterm_hnhl_recovery
.venv/Scripts/python.exe -m tools.build_midterm_hnhl_team_update
.venv/Scripts/python.exe -m tools.build_midterm_hnhl_nov09
.venv/Scripts/python.exe -m tools.check_midterm_hnhl --out reports/HuynhNguyenHoaiLoc/midterm/update-verification.json
# Dùng document-authoring runtime có python-docx, không dùng Python robot:
<document-python> tools/export_midterm_hnhl_doc.py
```

Sau export Word phải render lại tất cả trang và kiểm tra layout trước khi đưa vào báo cáo. Bản hiện tại kiểm tra bằng Microsoft Word trên Windows và rasterizer của document runtime; QA page images/PDF chỉ là intermediates trong data/midterm_qa. Không cần chạy lại model để vẽ lại số đo cũ. Nếu nguồn metrics hoặc nội dung thay đổi, sửa snapshot/narrative rồi kiểm tra lại; không ghi đè dữ liệu thí nghiệm lịch sử.

Kết quả đối chiếu hashes, links và kiểm tra bố cục 3 trang: [verification.json](verification.json). Log test 584 CPU/4 GPU là bằng chứng W5 có sẵn, không ghi là vừa chạy lại trong lần biên soạn này.

Đợt 03/11: [update-verification.json](update-verification.json) kiểm tra 20 nguồn, số liệu snapshot, liên kết nội bộ và hash Word. F9 single-model đã xem trực quan; checker không tự tuyên bố visual review cho một hình mới. Hash evidence chuẩn hóa CRLF → LF để tái lập qua Git trên Windows/Linux; hash DOCX/PNG giữ nguyên binary bytes. Word 01/11 vẫn cùng hash đã render/review, không cần tạo lại chỉ để đổi ngày. Nếu sửa Word hoặc nội dung gốc thì phải render lại.
