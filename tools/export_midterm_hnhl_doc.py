"""Export a compact HNHL Chapter 5 from the mid-term evidence snapshot.

Requires python-docx in the document-authoring runtime, not the robot runtime.
Run tools.build_midterm_hnhl first. Creates matching Word and Markdown text.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'reports/HuynhNguyenHoaiLoc/midterm'


def blocks(m):
    d, face, gpu = m['distance'], m['face'], m['gpu']
    return [
        [
            ('title', 'Nhận thức thị giác và triển khai mô hình'),
            ('subtitle', 'Chương 5  HuynhNguyenHoaiLoc  01 tháng 11 năm 2026'),
            ('p', 'Các module perception đã chạy trên laptop, gồm nhận diện vật cản, face verification, re-ID và tracking. Kết quả hiện có cho phép phân tích sai số và chi phí tính toán; chưa chứng minh đầy đủ các tiêu chí nhận diện và thử robot. Chương này phân biệt kết quả đo, pilot và các phép kiểm chứng còn thiếu.'),
            ('h', 'Vật cản và khoảng cách'),
            ('p', 'Ảnh fisheye được undistort bằng intrinsics đã hiệu chuẩn. Ray tại điểm tiếp xúc sàn được chiếu theo chiều cao lens và pitch/roll của session. Khi roll bằng 0: Z = H / tan(pitch + atan((v - cy)/fy)). Z là forward distance từ điểm dưới lens, đúng với tape truth; planar range dùng cho repulsion là đại lượng riêng. Sàn bóng tạo phản chiếu nên bbox bottom có thể sai; contact estimator không đủ bằng chứng sẽ từ chối khoảng cách.'),
            ('image', 'figures/F10_distance.png'),
            ('caption', f"F10. Ghế trên sàn glossy: {d['ids_with_distance']}/{d['ids']} vị trí có estimate, ID21 thiếu do cắt mép. Error median/p90: {d['median_pct']:.2f}%/{d['p90_pct']:.2f}%; ba vị trí held-out: {d['held_median_pct']:.2f}%/{d['held_p90_pct']:.2f}%. Điểm là median Z theo ID; error giữ cách tổng hợp gốc. [E01]"),
            ('h', 'Huấn luyện từ góc nhìn sát sàn'),
            ('p', 'D5 có 397 ảnh, một phòng và một session glossy. Split 307 train/90 dev-val giữ nguyên nhóm khoảng cách; dev-val đã dùng chọn checkpoint và input size. Sau sửa nhãn nền, YOLOv8n được train 30 epochs, batch 8, seed 42. Kết quả dưới đây là development validation, chưa độc lập về floor/session. [E02]'),
            ('table', ['Input', 'mAP50', 'mAP50-95', 'Leg recall', 'Wire recall'],
             [[size, f"{v['map50']:.3f}", f"{v['map50_95']:.3f}", f"{v['classes']['leg']['recall']:.3f}", f"{v['classes']['wire']['recall']:.3f}"]
              for size, v in m['d5']['models'].items()]),
            ('p', '640 là development candidate, chưa bật làm mặc định trên robot. Wire recall chưa đạt 80%; fallback hình học còn nhầm ron sàn. Mười hai masks dây mới là annotation pilot, chưa có kết quả segmentation. F10 chưa thay full T1: thiếu matte/control và số ID đủ điều kiện. F11 còn thiếu sweep với pose và vị trí vật/cửa đo thật.'),
        ],
        [
            ('h', 'Face verification tại cửa'),
            ('p', f"Whitelist dùng buffalo_s với SCRFD và MobileFaceNet, tạo embedding 512D được chuẩn hóa. Query so với tất cả reference bằng maximum cosine; threshold hiện tại {face['threshold']:.2f}. D2 cafe có {face['frames']} walker-face frames, {face['entries']} entries và {face['identities']} người. Nhãn largest-face/entry tự động cần được review, nhất là ảnh mờ và bystanders. [E03]"),
            ('image', 'figures/F13_face_roc.png'),
            ('caption', f"F13. ROC pilot cùng session, leave-one-member-out, enrollment từ entry đầu. Tại cosine {face['threshold']:.2f}: TAR {face['tar']:.2%}, FAR {face['far']:.2%}; chưa đạt mục tiêu TAR95% tại FAR1%. Queries liên tiếp tương quan; không dùng chính pilot để chọn lại threshold rồi báo PASS. [E03]"),
            ('h', 'Re ID và chuyển appearance giữa camera'),
            ('p', 'YOLO person crops được đưa qua OSNet-AIN x1.0 hoặc OSNet x0.25 với weights đã train re-ID. Cùng kích thước 512D không có nghĩa cùng embedding space: handoff yêu cầu đúng architecture, weights hash và preprocessing. D2 hiện chỉ có 23 body crops không mơ hồ; thiếu gallery ở 2/3 người. Vì vậy chưa có rank-1/CMC hợp lệ, chưa chọn model thắng và chưa có F14. Gate theo kế hoạch vẫn là rank-1 ≥85% với ≥5 gallery identities. [E03]'),
            ('h', 'Tracking và khóa mục tiêu'),
            ('p', 'ByteTrack dùng chuyển động/IoU và detection confidence thấp để nối track. OSNet kiểm tra appearance mới của track đang quan sát; track ID không được coi là danh tính. Khóa mục tiêu cần cosine và margin, xác nhận qua hai frame; mất dấu hoặc mơ hồ thì không xuất target. Re-lock sau che khuất phải xác nhận lại. Reference không tự cập nhật bằng query, và record simulated không được dùng khóa người thật.'),
            ('p', f"Đã chạy replay {m['tracking']['frames']} frame D2 bằng cùng API live và có {m['tests']['cpu_passed']} CPU tests, {m['tests']['gpu_passed']} GPU tests passed trong suite tuần 5. Replay dùng timestamp xấp xỉ đều và chưa có body ID truth nên không cung cấp ID-switch accuracy. D3 cảnh hai người có reviewed IDs/visibility còn thiếu; mục tiêu ≤1 switch/phút chưa nghiệm thu. [E04, E11, E12]"),
            ('h', 'Nhận diện cửa và phạm vi phối hợp'),
            ('p', 'XFeat ghép local features và kiểm tra homography RANSAC với robot-eye reference; DINOv2 hỗ trợ mô tả toàn ảnh khi reference khác camera. Threshold hiệu chuẩn bằng negative sweep theo cửa. Bearing không tự cung cấp door range. KR/DQK bổ sung kết quả cửa demo và F12; timing workload ở trang sau không phải accuracy cửa.'),
        ],
        [
            ('h', 'Ngân sách GPU khi các model cùng nạp'),
            ('p', 'Workload trên RTX 5060 Laptop nạp cùng YOLOv8n, OSNet-AIN, YOLOv8n-pose, SCRFD/MobileFaceNet, XFeat và DINOv2-B. Mỗi run có 5 warmup/100 iterations. DINO dùng FP16, Torch khác FP32. Khi thiếu detection, body/face work được pad tới ít nhất hai crop tổng hợp; đây không phải accuracy test. [E05-E07]'),
            ('image', 'figures/F9_gpu.png'),
            ('caption', 'F9. Throughput workload và NVML device-used; không gồm transport, map/control hoặc hai camera live. Memory gồm Torch/ORT/driver/process khác, lấy mẫu 20 ms nên có thể bỏ lỡ spike. Không đồng nhất với PyTorch allocator. [E05-E07]'),
            ('table', ['Workload', 'FPS', 'p95 ms', 'VRAM GiB'],
             [[name, f"{r['fps']:.2f}", f"{r['p95_ms']:.2f}", f"{r['peak_gib']:.3f}"]
              for name, r in zip(['Đủ model mỗi frame', 'XFeat mỗi frame', 'Đủ model cửa scheduled'], gpu)]),
            ('p', f"Run scheduled đạt {gpu[2]['door_hz']:.2f} door updates/s khi yêu cầu 5 Hz; scheduler hiện ở profiler. Hai run mỗi-frame chưa đạt 15 FPS. Scheduled đạt budget của workload trên máy này; chưa thay nghiệm thu RTX 4050 hoặc main-loop live. Giới hạn memory là 5,5 GB decimal, tương đương 5,12 GiB. Nguồn AC/battery chưa xác nhận."),
            ('h', 'Chuyển đổi mô hình và triển khai trên Jetson'),
            ('p', 'D5 custom đã freeze class order và checkpoint, export ONNX opset11 fixed-shape. So PyTorch CUDA FP32 với ONNX Runtime CPU trên 90 ảnh: 90/90 frame cùng số bbox, 294 reference boxes ghép đủ ở IoU ≥0,9. Đây là conversion parity trên laptop, chưa phải TensorRT accuracy. [E08]'),
            ('p', 'Kết quả stock edge models của DQK đạt cosine ≥0,999 trên các output được kiểm tra; YOLOv8n chỉ cùng count 205/208 frame. Không dùng phép đo đó chứng nhận model D5 custom hoặc OSNet-AIN handoff. DQK hoàn thiện phần engine build, workaround SCRFD Resize và F20/F21; các bước chưa qua gate chỉ được mô tả là kế hoạch. [E09]'),
            ('h', 'Phần cần kiểm chứng tiếp'),
            ('p', 'Ưu tiên bổ sung D3 và gallery toàn thân, map/vantage có pose/truth, nhãn Wire, phép so FP32-FP16 về accuracy và budget RTX 4050. F11, F14, F18 và T2 robot còn chờ. Kết quả chưa đạt được giữ nguyên trong báo cáo; không hạ ngưỡng hoặc dùng pilot/dev-val thay nghiệm thu độc lập.'),
            ('source', 'Nguồn E01-E12 và SHA256: midterm/evidence.md trong reports/HuynhNguyenHoaiLoc. Tài liệu phương pháp OSNet, ByteTrack, SCRFD/MobileFaceNets, YOLOv8 và phân công đọc nằm trong docs/Mid-Term Report Plan.md; KR tổng hợp bibliography của báo cáo nhóm.'),
        ],
    ]


def export(folder=OUT):
    from docx import Document
    from docx.shared import Cm, Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    folder = Path(folder)
    m = json.loads((folder / 'metrics.json').read_text(encoding='utf-8'))
    pages = blocks(m)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(1.9)
    sec.top_margin, sec.bottom_margin = Cm(1.65), Cm(1.65)
    for name in ['Normal', 'Title', 'Subtitle', 'Heading 1', 'Caption']:
        style = doc.styles[name]
        style.font.name = 'Times New Roman'
        style.font.color.rgb = RGBColor(0, 0, 0)
        fonts = style.element.get_or_add_rPr().rFonts
        for attr in list(fonts.attrib):
            if attr.endswith('Theme'):
                del fonts.attrib[attr]
        for attr in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
            fonts.set(qn('w:' + attr), 'Times New Roman')
        props = style.element.find(qn('w:pPr'))
        if props is not None:
            for border in list(props.findall(qn('w:pBdr'))):
                props.remove(border)
        style.paragraph_format.space_after = Pt(5)
    doc.styles['Normal'].font.size = Pt(11)
    doc.styles['Normal'].paragraph_format.line_spacing = 1.04
    doc.styles['Title'].font.size = Pt(17)
    doc.styles['Subtitle'].font.size = Pt(10.5)
    doc.styles['Heading 1'].font.size = Pt(12)
    doc.styles['Heading 1'].font.bold = True
    doc.styles['Heading 1'].paragraph_format.space_before = Pt(7)
    doc.styles['Heading 1'].paragraph_format.keep_with_next = True
    doc.styles['Caption'].font.size = Pt(9.5)
    doc.styles['Caption'].font.italic = True
    doc.styles['Caption'].font.bold = False
    doc.core_properties.author = 'HuynhNguyenHoaiLoc'
    doc.core_properties.title = 'Nhận thức thị giác và triển khai mô hình'
    doc.core_properties.subject = 'Chương 5 giữa kỳ CS532'
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = footer.add_run()
    run.font.name, run.font.size = 'Times New Roman', Pt(9)
    fld = OxmlElement('w:fldSimple')
    fld.set(qn('w:instr'), 'PAGE')
    run._r.append(fld)
    markdown = ['# Chương 5 Nhận thức thị giác và triển khai mô hình', '', 'HNHL • Snapshot 01/11/2026', '']
    for page_index, page in enumerate(pages):
        if page_index:
            doc.add_page_break()
        for item in page:
            kind, content = item[:2]
            if kind == 'image':
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.keep_with_next = True
                p.paragraph_format.space_after = Pt(2)
                picture = p.add_run().add_picture(str(folder / content), width=Inches(6.5))
                picture._inline.docPr.set('descr', content)
                markdown.extend([f'![{Path(content).stem}]({content})', ''])
            elif kind == 'table':
                data = item[2]
                table = doc.add_table(rows=1, cols=len(content))
                table.autofit = False
                widths = ([1.4, 3.8, 3.8, 3.8, 3.8] if len(content) == 5 else [7.2, 2.7, 3.0, 3.7])
                props = table._tbl.tblPr
                borders = OxmlElement('w:tblBorders')
                for edge in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
                    border = OxmlElement('w:' + edge)
                    for key, value in [('val', 'single'), ('sz', '4'), ('color', 'D9D9D9')]:
                        border.set(qn('w:' + key), value)
                    borders.append(border)
                props.append(borders)
                for row_index, values in enumerate([content, *data]):
                    row = table.rows[0] if row_index == 0 else table.add_row()
                    row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
                    for j, (cell, value) in enumerate(zip(row.cells, values)):
                        cell.width = Cm(widths[j])
                        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                        p = cell.paragraphs[0]
                        p.paragraph_format.space_before = Pt(3)
                        p.paragraph_format.space_after = Pt(3)
                        p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
                        r = p.add_run(str(value))
                        r.font.name, r.font.size = 'Times New Roman', Pt(10)
                        r.bold = row_index == 0
                        r.font.color.rgb = RGBColor(255, 255, 255) if row_index == 0 else RGBColor(0, 0, 0)
                        shade = OxmlElement('w:shd')
                        shade.set(qn('w:fill'), '29445A' if row_index == 0 else ('F2F4F6' if row_index % 2 else 'FFFFFF'))
                        cell._tc.get_or_add_tcPr().append(shade)
                markdown += ['| ' + ' | '.join(content) + ' |', '| ' + ' | '.join(['---'] * len(content)) + ' |']
                markdown += ['| ' + ' | '.join(map(str, row)) + ' |' for row in data]
                markdown.append('')
                doc.add_paragraph().paragraph_format.space_after = Pt(0)
            else:
                style = {'title': 'Title', 'subtitle': 'Subtitle', 'h': 'Heading 1', 'caption': 'Caption'}.get(kind, 'Normal')
                p = doc.add_paragraph(content, style)
                if kind in ('p', 'source'):
                    p.paragraph_format.widow_control = True
                if kind == 'source':
                    for r in p.runs:
                        r.font.size = Pt(9)
                if kind not in ('title', 'subtitle'):
                    markdown.extend([('## ' if kind == 'h' else '') + content, ''])
    path = folder / 'HNHL-Chuong-5.docx'
    doc.save(path)
    (folder / 'chapter-05.md').write_text('\n'.join(markdown), encoding='utf-8')
    print('Created', path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--folder', default=str(OUT))
    args = ap.parse_args()
    export(args.folder)


if __name__ == '__main__':
    main()
