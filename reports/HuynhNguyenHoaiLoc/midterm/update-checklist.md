# Checklist tiếp tục hoàn thiện giữa kỳ HNHL

**Hiện hành10/11:** [DQK đã thử lớp, depth và body cues](update-2026-11-10.md); đưa thất bại/coverage vào báo cáo, không làm lại các comparisons này chỉ để đổi ngày. DQK đang làm B/reflection/contact; cần scripts/config/weights hashes, chair+table+empty-floor controls và held-out raw samples để HNHL đánh giá. Chưa có candidate đủ thay detector mặc định. Trunk chọn trên cùng một người/ba sets, cần người khác và mốc1,2/1,8/2,4m. D3/gallery/F11/raw latency/combined4050 vẫn pending; official session/ESP32/T2 chưa được thay bằng buổi DQK một mình09/11.

**Sau bản sửa KR09/11:** [PR101 follow-up](followup-pr101-2026-11-09.md) ghi các lỗi cũ đã sửa và các lỗi còn tái hiện. Phần báo cáo HNHL đã được KR sửa đáng kể; còn cần bỏ distance T1 PASS, sửa destination của appearance vector, đưa F18/caveats vào bản ghép. Chưa có D3/gallery/D5 độc lập/map/latency/combined4050 mới; không chuyển các mục này sang PASS.

**Hiện hành09/11:** [đối chiếu mới](update-2026-11-09.md) và [gói sửa Chương5 cho KR](HNHL-EDITOR-CORRECTIONS-1109.md). Phần nhóm đã có thêm: poses/run08/11,5 video stop-proxy, Phase3 T0 và bản thảo nhóm. Đã bổ sung có giới hạn; chưa đủ D3/re-ID/D5 độc lập/F11/F7 raw/combined4050/T2. Các PR99/101/102 có findings, chưa merge. Converter D3 và F18 đã triển khai/đo trong #100, chờ review; không cần viết lại vì dòng kế hoạch cũ “offered, not written”. Buổi lớp09/11 và bỏ matte là thay đổi đang đề xuất; chưa tự đổi nghiệm thu. Mốc16/18/23-11 giữ nguyên.

**Cập nhật hiện hành 07/11:** [audit bằng chứng DQK/KR](update-2026-11-07.md) xác nhận DQK đã đo pose sau sửa và chạy pilot home một người. Đã bổ sung số đo/giới hạn vào bản thảo; không yêu cầu nhóm làm lại các nguồn GPU/entrance/edge/simulation đã có. Còn thiếu reviewed D3 hai người, re-ID gallery≥5 identities, D5 độc lập, world truth và raw latency/combined RTX4050. PR #99 head mới vẫn request-changes; phần pilot không biến thành PASS hoặc dữ liệu D3.

**Trạng thái hiện hành 06/11:** [DQK báo camera đã sửa](update-2026-11-06.md), stream hoạt động trở lại; cần recheck socket/cáp, self-pose và height trước thu D3/D5/run được tính. Không còn trạng thái mất stream theo báo cáo DQK; HNHL chưa kiểm tra robot trực tiếp. Tool `prepare_d3_recording` đã chuẩn bị bước chuyển JSONL→replay epochs, giữ timestamp thật và tạo template nhãn chưa review. PR #99 chưa sửa, #100 chờ DQK. Các ghi chú blocked phía dưới là lịch sử ngày 05/11.

**Cập nhật 05/11:** [PR #98 đã merge, camera hỏng và F18](update-2026-11-05.md). Việc cần video robot đang bị chặn cho tới khi DQK xác nhận sửa xong. Các ngày 04/11/09/11 bên dưới là kế hoạch lịch sử, không phải kết quả thu thập. F18 native CUDA D5 đã có paired latency/memory/accuracy trên dev-val; không cần chạy lại chỉ để đổi ngày. Còn combined RTX4050, các model khác và independent accuracy. PR #99 request changes, chưa là runner đã nghiệm thu.

Snapshot01/11/2026. Khi có cập nhật, bắt đầu từ nguồn evidence mới và trạng thái GitHub; không chạy lại mọi benchmark nếu code/protocol không đổi. Không ghi đè log, checkpoint hoặc dataset lịch sử.

Đã kiểm tra lại 03/11: xem [audit tuần 5](week-05-audit.md) và [bổ sung evidence](update-2026-11-03.md). PR #92 đã merge; #94 cung cấp F15 measured endpoints; #93 có head sửa mới, chưa merge tại snapshot. Baseline RTX4050 single-model đã đưa vào F9 bổ sung; combined workload RTX4050, D3/gallery và real map vẫn thiếu.

Snapshot tiếp sau đó: [#93/#95/#96 đã merge](session-followup-2026-11-03.md). Thực hiện [D3 handoff](D3-HANDOFF-HNHL.md) khi có data từ buổi 04/11 và lớp học 09/11; không đánh dấu các buổi tương lai là đã chạy. DQK/KR giữ phần robot và integration; HNHL review labels/evaluate và GPU/report.

| Ưu tiên | Cập nhật cần có | Việc làm khi nhận được | Phần thay đổi |
| :-- | :-- | :-- | :-- |
| 1 | D2 reviewed walker/identity labels, body crops và gallery đúng model/hash | Review nhãn trước, tách entry/session trước khi xem scores; chạy evaluator với protocol phù hợp, giữ model selection ở calibration | F13/F14, mục face/re-ID, hàng Ch7 |
| 1 | D3 JetBot hai người có reviewed IDs/visibility và capture timestamps | Replay tracker, one-to-one matches, ID switches/min và misses/FP; kiểm tra target lock/re-lock riêng bằng target identity truth | Tracking, F14 nếu có cross-camera gallery, trạng thái T1 |
| 1 | D1 sweep có robot poses/world truth/door range và camera offset | Sinh map/vantage bằng API thực, đối chiếu vị trí vật và điều kiện vị trí quan sát | F11, map/T1/T2 |
| 2 | Paired prediction/tape mới hoặc pose session sửa có bằng chứng | Dùng đúng session pose; báo cả missed IDs, tách development/held-out/floor; không fit pitch bằng chính tape đang chấm | F10 và error summary |
| 2 | Thêm wire masks/labels hoặc D5 session/floor khác | QA labels; freeze split/protocol; train mới vào run mới; báo recall/precision và empty-floor alarms ở operating point đã chốt | D5/Wire, giới hạn tổng quát |
| 2 | RTX4050 hoặc paired FP32/FP16 runs | Cùng input, workload/cadence và accuracy set; tách NVML/allocator; không dùng cosine conversion thay accuracy | F9/F18, GPU/optimization |
| 3 | Robot T2 hoặc evidence Jetson mới của DQK | Nhận log và các câu trả lời tape; xác nhận owner, devices, load, freshness; không coi review code là HIL pass | F20/F21 và Ch7 |
| 3 | Raw clock-synced latency CSV JetBot + watchdog/e-stop logs | CDF/FPS có clock/seq flags, công bố sample count; tách localhost synthetic khỏi robot | F7 cùng DQK |

Khi camera sửa xong: DQK đo lại mount/self-pose; nếu thay module thì cần fisheye calibration mới. HNHL gắn đúng camera/calibration/session cho data mới, giữ calibration cũ cho D1/D2/D5 cũ. Nếu không đủ dữ liệu trước 16/11, chuyển các kết quả còn thiếu sang chưa đo/giới hạn và dùng replay/simulation có nhãn nguồn cho demo.

## Lệnh sau khi có D3 thật

```powershell
.venv/Scripts/python.exe -m tools.track_replay --manifest data/D3/frames.json --out data/midterm/d3_predictions.json --target data/midterm/target.npz
.venv/Scripts/python.exe -m tools.evaluate_tracking --truth data/D3/truth.json --predictions data/midterm/d3_predictions.json --out reports/HuynhNguyenHoaiLoc/week-05/d3_metrics.json
```

Đọc `W5-USAGE.md` trước khi gán nhãn: đủ mọi frame kể cả empty, epoch/ID đúng, cùng timestamps. Chỉ số switch tốt không tự chứng minh detection recall hoặc target identity đúng. Gate re-ID ≥5 người giữ nguyên trừ khi nhóm chính thức đổi protocol; bộ ba người hiện tại là pilot.

## Vòng cập nhật tài liệu

1. Lưu evidence mới có config/weights/data hashes và mô tả protocol; không sửa số trong Word trước.
2. Cập nhật `SOURCES/collect` của `tools/build_midterm_hnhl.py` nếu sửa snapshot Word 01/11. Builder này tổng hợp E01–E12. `tools.build_midterm_hnhl_update` tạo phụ lục 03/11 từ E13–E20 và GitHub snapshot đã lưu. Cả hai không tự phát hiện dataset mới hoặc tự thay null bằng score.
3. Cập nhật narrative trong `tools/export_midterm_hnhl_doc.py` theo kết quả và giới hạn đã review; chạy hai builders để Markdown/Word/figures đồng nhất.
4. Render Word lại, kiểm tra từng trang; so số làm tròn, captions, đơn vị GB/GiB, source hashes và link evidence.
5. Sửa trạng thái Ch7/appendix, gửi KR bản đã được HNHL kiểm tra. Không tự ghi timesheet hoặc đồng thuận nhóm.

## Mốc chốt

- Trước09/11: bổ sung các hình khả thi và bản thảo cho editor.
- 16/11: đóng thí nghiệm, freeze hình; phần chưa chạy chuyển thành đang thực hiện/kế hoạch.
- 18/11: full report draft nhóm và video cut nếu làm video.
- 19–20/11: kiểm tra mọi số với evidence, freeze PR ngày20/11.
- 21/11: clean checkout và tag midterm sau review nhóm.
- 23/11: nộp báo cáo10–15 trang kèm code; video là tùy chọn.

Nếu nhóm làm video, HNHL chuẩn bị screen recording overlay laptop: whitelist/intruder, khóa/mất/khóa lại target và FPS/VRAM. Chỉ quay thao tác đã hoạt động, xin phối hợp DQK/KR cho cảnh robot/cửa; chưa có clip hoàn chỉnh hoặc link demo trong snapshot này.
