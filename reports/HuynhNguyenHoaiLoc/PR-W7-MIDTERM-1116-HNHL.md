# HNHL W7 cập nhật giữa kỳ từ buổi lớp 16/11

PR #124 đã được DQK approve và merge. Bản bổ sung này cập nhật Chương 5/7, appendix và checklist HNHL từ các PR #125/#126/#127 vừa review và merge.

- Tính lại pursuit từ toàn bộ 1.181 dòng CSV với interval weights và full elapsed denominator, đối chiếu deployment/handshake/calibration cùng summary đã commit. Tracked 99,7%, distance-in-band 32,2%, centred 91,1% và 0 HOLD. Ghi kết quả cự ly dưới yêu cầu 80% và điều kiện foot-row, một người, chế độ nguồn đọc cuối buổi.
- Ghi deployment thứ 7, pose mới, F3/F17b, các rehearsal hợp lệ/thất bại và lịch video 19/11. Các số D2 re-score/e-stop tối được quy nguồn DQK cùng trạng thái raw logs local.
- Bổ sung `build_midterm_hnhl_nov16` và checker cho nguồn Git/hash Markdown mới. Snapshot 15/11 được kiểm tra từ commit lịch sử khi current Markdown chuyển sang 16/11.
- Theo review #124, giải thích timestamp None/0 trong IntruderRecord và thêm regression khi active target thiếu queue record lúc inject tracker.
- Lưu review và merge receipts. #113 vẫn chờ xử lý các finding xóa dữ liệu và cập nhật package.

HNHL giữ các đầu việc door T1, D3/gallery, independent D5, body visibility/cross-camera và automatic map/vantage trong phần nghiệm thu còn chờ. Hình F17b tái tạo byte-identical từ nguồn đã commit. Reviewer đề nghị DQK kiểm tra số đo/attribution và KR kiểm tra handoff tài liệu cho bản draft 18/11.

Kiểm tra trên `.venv` của HNHL đạt **882 passed, 2 skipped, 4 GPU deselected trong 62,85 s**. Hai ca skip cần checkerboard và D1 classroom. Evidence checker xác minh 24 nguồn đợt 16/11, các snapshot trước và 255 liên kết local. Snapshot Word giữ hash đã được kiểm tra. Log kiểm thử và checker nằm ở `reports/HuynhNguyenHoaiLoc/week-07/review-2026-11-16/`.
