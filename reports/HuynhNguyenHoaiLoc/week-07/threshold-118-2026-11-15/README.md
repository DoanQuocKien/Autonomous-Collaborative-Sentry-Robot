# HNHL — quyết định issue #118, 15/11/2026

Giữ **cosine 0,45** và chọn **3 mẫu mặt tốt nhất của entry; ít nhất 2 mẫu chấp nhận cùng một ID**. Đây là quyết định tạm thời đã có trong PR #115, phù hợp ý kiến DQK và quyết định nhóm ở PR #120. Chưa hạ ngưỡng hoặc thay model từ một buổi ba người. Không thay đổi `config.toml`.

Đã tính lại CSV của DQK tại commit `b831e76f073e7de51a774fdaf06b5aee2590f274` thuộc PR #116. Mỗi ảnh có score với từng enrolment; không chạy lại model từ ảnh. Genuine dùng 877 frame nhìn thẳng, thiếu face tính miss; impostor dùng 5.254 score có sẵn từ mọi frame đối với hai enrolment khác. Hash CSV được chuẩn hóa LF để dùng được trên Windows.

| Ngưỡng | Genuine chấp nhận | TAR | Impostor chấp nhận | FAR quan sát |
| :-- | --: | --: | --: | --: |
| 0,45 | 822/877 | 93,729% | 0/5.254 | 0% |
| 0,40 | 868/877 | 98,974% | 0/5.254 | 0% |
| 0,35 | 875/877 | 99,772% | 0/5.254 | 0% |
| 0,30 | 877/877 | 100% | 14/5.254 | 0,266% |

Riêng impostor frame nhìn thẳng là 0/1.754 tại 0,45. Max impostor mọi frame 0,336; khoảng cách tới ngưỡng là 0,114 ở 0,45 và 0,064 ở 0,40. Bootstrap mô tả theo 9 clip, seed 0, 5.000 lần, cho TAR tại 0,45 khoảng 95% **[0,904; 0,970]**. Khoảng này chứa 0,95, nên chưa thể kết luận mức TAR thực sự thấp hơn mục tiêu chỉ từ point estimate. Các clip vẫn thuộc ba người trong một session; bootstrap này không phải kiểm chứng quần thể.

[ROC theo lưới ngưỡng 0,01](roc.png), [CSV ROC](roc.csv), [số liệu và provenance](summary.json), [chạy lại công cụ phân tích của DQK](dqk-analysis.txt). FAR bằng 0 trên mẫu tương quan không phải FAR quần thể bằng 0; các cặp identity đều là thành viên đã enrol, còn thiếu người lạ ngoài nhóm.

## Ý nghĩa của top-K live

N xác nhận entry = 3 frame có face hợp lệ liên tiếp; K quyết định = 3 mẫu tốt nhất, ưu tiên frontal rồi confidence × width × sharpness; 2/3 phiếu phải cùng ID. Lịch yêu cầu 5 Hz, không chạy bù frame. Entry kết thúc sau M=3 frame xử lý thiếu face hợp lệ hoặc giới hạn 15 giây. K=3 không có nghĩa là ba frame liên tiếp cuối cùng và không bảo đảm thời gian enqueue cố định.

Phép thử cửa sổ liên tiếp 5/12 frame của DQK cho thấy phương án gộp nhiều frame đáng thử, nhưng chạy ở 12,5 Hz và CSV chưa có sharpness/track/entry truth. **Không gán TAR 0,974 hay 0,990 của các cửa sổ đó cho chính sách top-3 live.** Cần giữ cả unresolved, interrupted và lượt thiếu trong mẫu số coverage. Bản bổ sung #115 ghi `person_confirmed` sau N frame person liên tiếp; `confirmed_unresolved` đếm những segment có person được xác nhận nhưng kết thúc unresolved. `confirmed` cũ vẫn là xác nhận bằng face. Counter chỉ phục vụ audit, chưa thay đổi quyết định enqueue.

## Đợt dữ liệu tiếp theo

Trước khi thay ngưỡng, cần session khác với enrolment webcam/ESP32 được giữ tách biệt, ba khoảng cách 1,8/2,4/3,0 m và ít nhất một người ngoài whitelist/ngoài nhóm. Ghi lượt qua cửa vật lý, ID và thời điểm bắt đầu/kết thúc đã review; chạy chính top-K live với thresholds cố định trước khi xem test. Báo TAR/FAR theo entry, coverage, confirmed-unresolved, missing và latency; đối chiếu body visibility/cross-camera với DQK và queue dùng chung với KR. Không thêm T1 PASS từ dữ liệu hiện tại.

Issue #118 đã được đăng trả lời và đóng cho **quyết định ngưỡng/N đã trả lời**. Nghiệm thu và dữ liệu bổ sung tiếp tục theo #114; D3, independent D5 và accuracy FP16/FP32 trên RTX4050 vẫn là các việc đo riêng.

```powershell
.venv/Scripts/python.exe reports/HuynhNguyenHoaiLoc/week-07/threshold-118-2026-11-15/reproduce.py --csv-dir reports/DoanQuocKien/week-06/t2_1114 --out-dir data/threshold-118-rerun
```

Cần CSV đúng pinned commit của PR #116. Nếu PR chưa merge, dùng đường dẫn checkout riêng của PR đó. Chọn thư mục output mới; script từ chối ghi đè.
