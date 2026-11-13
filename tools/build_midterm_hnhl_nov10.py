"""Offline HNHL addendum: DQK classroom failures and ranging alternatives, 10/11."""
import argparse
import csv
import hashlib
import io
import json
import subprocess

import numpy as np

from tools.build_midterm_hnhl import ROOT, OUT, evidence_bytes
from tools.build_midterm_hnhl_team_update import summarize_rows

ARCHIVE = OUT/'team-evidence-2026-11-10'
P99 = '45416e7ed13293df805e2f4e9255b4dd9e1d3393'
P102 = '8ec3598c4387640e790a33d82785b3c76ed8375a'
CLASS = 'reports/DoanQuocKien/week-06/classroom_1109/'
HOME = 'reports/DoanQuocKien/week-05/home_1107/'
COLS = ('t','dist_m','forward_m','left_m','yaw_err','v_req','w_req','v','w','suppressed','mode','event','range_src','foot_forward_m')
NAME = 'update-2026-11-10'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def import_source():
    if ARCHIVE.exists():
        raise FileExistsError('historical archive exists; do not overwrite')
    names = ['README.md']
    names += ['pose/camera_pose_self_1109_%d.json'%i for i in range(1,5)]
    names += ['furniture/chair_%s_1109/result.json'%d for d in ('1p2','1p8','2p4')]
    names += ['experiment_'+n+'.json' for n in ('B_offline_pass1','A_depth_pass1_body_zoom2',
        'A_depth_zoom_holdout','A_models_trial','A_floor_anchor_trial','A_anthro_range',
        'A_anthro_temporal','A_anthro_fusion')]
    files = [('classroom/'+n,P102,CLASS+n) for n in names]
    files += [('pursuit/README.md',P99,HOME+'README.md'),
        ('plan/week06.md',P102,'reports/DoanQuocKien/week-06.md'),
        ('plan/limits.md',P102,'docs/Mid-Term Report Plan.md')]
    files += [('pursuit/'+run+'/'+n,P99,HOME+'pursuit/'+run+'/'+n)
        for run in ('p2_dry_1','tile_1_1','tile_2_1') for n in ('log.csv','summary.json')]
    pending, entries = [], []
    for relative,commit,path in files:
        original = subprocess.run(['git','show',commit+':'+path],cwd=ROOT,capture_output=True,check=True).stdout.replace(b'\r\n',b'\n')
        data,transformation = original,'verbatim numeric source'
        if relative.endswith('log.csv'):
            rows = list(csv.DictReader(io.StringIO(original.decode('utf-8-sig'))))
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream,fieldnames=COLS,lineterminator='\n')
            writer.writeheader()
            writer.writerows({k:r.get(k,'') for k in COLS} for r in rows)
            data,transformation = stream.getvalue().encode(),'retain numeric/control columns; omit track IDs/boxes'
        elif relative.endswith('summary.json'):
            value = json.loads(original)
            value.pop('target_id',None)
            data,transformation = (json.dumps(value,indent=2,allow_nan=False)+'\n').encode(),'omit target_id; retain unaccepted source diagnostics'
        elif relative=='plan/limits.md':
            data = ('## 8.'+original.decode('utf-8').split('## 8.',1)[1]).rstrip().encode()+b'\n'
            transformation = 'section8 excerpt; trim EOF whitespace; owner attribution retained'
        pending.append((relative,data))
        entries.append(dict(archive=relative,source_commit=commit,source_path=path,
            source_url='https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/blob/'+commit+'/'+path.replace(' ','%20'),
            original_sha256=sha(original),archive_sha256=sha(data),transformation=transformation))
    ARCHIVE.mkdir(parents=True)
    for relative,data in pending:
        path = ARCHIVE/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    (ARCHIVE/'provenance.json').write_text(json.dumps(dict(imported_date='2026-11-10',
        source_prs={99:P99,102:P102},merged=False,files=entries),indent=2)+'\n',encoding='utf-8')


def chair_availability(doc):
    rows = doc['rows']
    if not rows or len(rows)!=doc['frames']:
        raise ValueError('nonempty frame-aligned furniture rows required')
    detected = sum(bool(r) for r in rows)
    ranged = sum(any(item.get('distance_m') is not None for item in row) for row in rows)
    if detected!=doc['frames_with_detection'] or ranged!=doc['frames_with_distance']:
        raise ValueError('source counts disagree with rows')
    return dict(front_marker_m=doc['tape_m'],frames=len(rows),detected=detected,ranged=ranged,
        median_error_m=None if ranged==0 else doc.get('error_m'),
        tape_origin='robot front to nearest chair floor point; not lens-forward truth',
        acceptance=False)


def range_stats(values,tape):
    a = np.asarray(values,dtype=float)
    if a.ndim!=1 or not len(a) or not np.isfinite(a).all() or (a<=0).any() or not np.isfinite(tape) or tape<=0:
        raise ValueError('finite nonempty ranges and positive tape required')
    return dict(samples=len(a),median_m=float(np.median(a)),
        median_signed_error_m=float(np.median(a-tape)),sd_m=float(np.std(a)),
        frame_fraction_within_15cm=float(np.mean(np.abs(a-tape)<=.15)))


def collect_nov10():
    registry = {}
    provenance = json.loads((ARCHIVE/'provenance.json').read_text(encoding='utf-8'))
    def source(key,path):
        data = evidence_bytes(ROOT/path)
        registry[key] = dict(path=path,sha256=sha(data))
        return data
    for i,entry in enumerate(provenance['files']):
        data = source('C%02d'%i,(ARCHIVE/entry['archive']).relative_to(ROOT).as_posix())
        assert sha(data)==entry['archive_sha256'],'archived teammate source drift'
    source('C-provenance',(ARCHIVE/'provenance.json').relative_to(ROOT).as_posix())
    for n in (99,102):
        for suffix in ('.md','.json'):
            source('review%d%s'%(n,suffix),'reports/HuynhNguyenHoaiLoc/reviews/PR-%d-2026-11-10%s'%(n,suffix))
    source('tests99','reports/HuynhNguyenHoaiLoc/reviews/PR-99-2026-11-10-tests.log')
    tests = source('evidence-tests','reports/HuynhNguyenHoaiLoc/week-06/tests_evidence_2026-11-10.log')
    assert b'21 passed in 4.21s' in tests
    reproduction = json.loads(source('repro99','reports/HuynhNguyenHoaiLoc/reviews/PR-99-2026-11-10-reproductions.json'))
    def read(path):
        return json.loads((ARCHIVE/path).read_text(encoding='utf-8'))
    chairs = [chair_availability(read('classroom/furniture/chair_%s_1109/result.json'%d)) for d in ('1p2','1p8','2p4')]
    temporal = {}
    for name,doc in read('classroom/experiment_A_anthro_temporal.json').items():
        assert len(doc['raw'])==len(doc['smoothed'])==doc['gated']
        temporal[name] = dict(tape_m=doc['tape'],frames=doc['frames'],gated=doc['gated'],
            raw=range_stats(doc['raw'],doc['tape']),smoothed=range_stats(doc['smoothed'],doc['tape']))
    fusion = {name:{cue:range_stats(values,doc['tape']) for cue,values in doc['series'].items()}
              for name,doc in read('classroom/experiment_A_anthro_fusion.json').items()}
    depth = {name:{zoom:range_stats(values,doc['tape']) for zoom,values in doc['per_zoom'].items() if values}
             for name,doc in read('classroom/experiment_A_depth_zoom_holdout.json').items()}
    runs = {}
    for run in ('p2_dry_1','tile_1_1','tile_2_1'):
        rows = list(csv.DictReader((ARCHIVE/'pursuit'/run/'log.csv').open(encoding='utf-8',newline='')))
        runs[run] = dict(stats=summarize_rows(rows),summary=read('pursuit/'+run+'/summary.json'),acceptance=False)
    return dict(snapshot_date='2026-11-10',evidence=registry,source_heads={'99':P99,'102':P102},
        source_prs_merged=False,chairs=chairs,offline_B=read('classroom/experiment_B_offline_pass1.json'),
        temporal_trunk_prior_m=.50,temporal=temporal,fusion_trunk_prior_m=.49,fusion=fusion,
        depth_zoom=depth,runs=runs,tile3_source_available=False,
        camera_mount_cause='DQK attributes to handling/movement; not independently measured',
        robot_commands_sent=0,inference_rerun=False,review99_reproduction=reproduction,
        acceptance=dict(d3=False,reid=False,independent_d5=False,map_world_truth=False,
            raw_latency=False,combined4050=False,pursuit_hold=False),
        limitations=['one chair/one person, correlated frames and previously inspected sets',
            'chair tape origin differs from lens-forward; do not pool with earlier F10 errors',
            'round7 frame accuracy is not round8 per-set median-bias success',
            'source experiment date labels say Nov10 evening/night; exact execution time not independently verified',
            'table/empty-floor controls, person1.2/2.4m/other people, raw D3 IDs still absent'])


def update_chapter(text):
    text = text.replace('Phần HNHL cập nhật 09/11/2026','Phần HNHL cập nhật 10/11/2026')
    old = next(line for line in text.splitlines() if line.startswith('DQK đã bổ sung các run'))
    new = ('DQK bổ sung thử lớp09/11 (glossy tile; các run06–08/11 là home wooden floor). '
        'Retest một ghế có4/36 frame detection và0/36 distance; không tính error=0 khi thiếu estimate. '
        'Tape từ đầu robot khác lens-forward nên không gộp với F10 cũ. Các model depth/zoom/floor-anchor chưa chuyển được giữa sets; '
        'trunk cue0,50m trên một người có bias≈0,16m ở hai sets, smoothing không bỏ bias. Round0,49m có median tốt hơn nhưng là protocol khác, '
        'chưa arbitrary-person accuracy. Trunk mode mặc định off ở PR99; không thay detector/config HNHL. '
        'DQK quy nguyên nhân pitch cho mount/handling, chưa đo độc lập. PR99 đã sửa config, centring và pose cap nhưng vẫn overwrite log khi numbering có lỗ; '
        'PR102 chưa sửa cleanup motor; PR101 còn các lỗi follow-up09/11. Chưa merge các PR này. '
        'D3/gallery/D5 độc lập/F11/raw latency/combined4050/T2 vẫn thiếu. [Kết quả và phương án đã thử](update-2026-11-10.md). '
        'Chốt hình16/11, draft18/11, nộp23/11 không đổi.')
    return text.replace(old,new)


def plot_availability(m):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    x = np.arange(3)
    fig,ax = plt.subplots(figsize=(7.5,4.4),layout='constrained')
    ax.bar(x-.18,[r['detected'] for r in m['chairs']],.36,label='frames with detection')
    ax.bar(x+.18,[r['ranged'] for r in m['chairs']],.36,label='frames with accepted distance')
    for i,r in enumerate(m['chairs']):
        ax.text(i-.18,r['detected']+.2,str(r['detected']),ha='center')
        ax.text(i+.18,.2,'0',ha='center')
    ax.set(xticks=x,xticklabels=['1.2 m','1.8 m','2.4 m'],ylim=(0,13),ylabel='frames (12 per marker)',
        xlabel='robot-front marker; NOT lens-forward ground truth')
    ax.legend(loc='upper left',fontsize=8)
    ax.set_title('F10 supplement: chair range availability, DQK classroom 2026-11-09\nYOLOv8n 0.25 / glossy contact: 0 accepted distances in 36 frames',fontsize=10)
    ax.grid(axis='y',alpha=.2)
    fig.savefig(OUT/'figures/F10_availability_1109.png',dpi=180)
    plt.close(fig)


def write_report(m):
    lines=['# HNHL — bổ sung giữa kỳ từ bằng chứng mới DQK, 10/11/2026','',
        'Nguồn PR99 head45416e7 và PR102 head8ec3598, đều chưa merge. HNHL đọc numeric evidence/review code, không chạy robot hoặc inference. [Registry](update-2026-11-10.json), [provenance](team-evidence-2026-11-10/provenance.json). Các snapshot trước giữ nguyên.','',
        '## Vật cản: bổ sung kết quả thất bại thay vì chỉ subset có distance','',
        '| Marker từ đầu robot | Frames | Detection | Distance hợp lệ | Median error |','| --: | --: | --: | --: | :-- |']
    for r in m['chairs']:
        lines.append('| %.1f m | %d | %d | %d | chưa đo |'%(r['front_marker_m'],r['frames'],r['detected'],r['ranged']))
    lines += ['', 'Một ghế khung kim loại trên sàn glossy lớp09/11; pose1109_4, YOLOv8n confidence0,25. Bốn detections ở1,8m đều reflection_unresolved. Giữ median/error=null, không coi0 distances là0 error. Tape từ đầu robot tới điểm ghế gần nhất; source nói skid khoảng1,46m từ lens khi marker1,2m, nên không cộng offset tùy ý hoặc gộp với8/9 IDs F10 trước. Không full T1≥20 IDs.','',
        '![F10 supplement: range availability](figures/F10_availability_1109.png)','',
        'Offline JPEG sweep (12 frames/mốc) khác sampling của live: base1,8m có6 detections thay vì4. YOLOv8s:5/0,1/0,12/5 detection/distance theo1,2/1,8/2,4m; YOLO-World0/0,8/0,12/0. SegFormer không cải thiện; v8s+SegFormer bằng v8s. Median2,21m của5/12 far-frame v8s không đủ distance coverage và truth chưa cùng gốc. Không chọn model thắng chỉ vì nhiều bbox hơn.','',
        '## Person range: những lựa chọn đã thử','',
        'DQK đã thử DA-V2 Metric Indoor Small/Base/Large, Depth Pro, ZoeDepth; zoom/calibration không chuyển được sang set1,25m. Relative-depth floor anchor cũng không ổn định giữa hai sets≈1,8m. Đây là failed local comparisons, không kết luận mọi depth model đều bất khả thi. Raw model/dataset hashes và scripts đầy đủ chưa đi kèm; không chạy lại/download chỉ để tái tạo các số này.','',
        '| Tape dưới lens | Gated frames | Trunk0,50 raw median bias | Smooth median bias | Smooth frames trong±0,15m |','| --: | --: | --: | --: | --: |']
    for doc in m['temporal'].values():
        lines.append('| %.2f m | %d/%d | %+.3f m | %+.3f m | %.1f%% |'%(doc['tape_m'],doc['gated'],doc['frames'],doc['raw']['median_signed_error_m'],doc['smoothed']['median_signed_error_m'],100*doc['smoothed']['frame_fraction_within_15cm']))
    lines += ['', 'Tính lại từ arrays nguồn (748 gated frames nhưng chỉ một người/ba sets), không chép tỷ lệ làm tròn của README nguồn: bảng README ghi smooth29%/100%/32%, khác32,7%/100%/29,5% tính từ JSON. Cần tác giả đối chiếu script/labels trước khi chốt. Noise nhỏ không đồng nghĩa accuracy; smoothing không bỏ per-set bias. Round8 dùng prior0,49m, median trunk bias≈+0,13/−0,05/+0,12m (3/3 set medians trong±0,15m); khác round7 prior0,50m và không phải mọi frame đều đạt. Fusion với foot-row tệ hơn trunk đơn lẻ. Cue chọn sau khi xem các sets; không độc lập. Row người2,4m từng dùng nhầm stock sample đã bị DQK rút, không sử dụng.','',
        'PR99 thêm --range-source trunk, default vẫn foot, prior0,50m; chưa chạy robot cho trunk. Không dùng kết quả0,49m làm validation cho config0,50m. Cần nhiều người khác ở1,2/1,8/2,4m, posture/roll/occlusion và fallback tests. Không đổi detector/ranging mặc định của HNHL.','',
        '## Pursuit, camera và phần còn chờ','',
        'Các run tile_1_1/tile_2_1 là lớp học glossy0,6m tiles, không home. Tape lúc hold≈1,7m nhưng log≈1,28–1,33m; tile2 không HOLD dù người đứng. p2_dry_1 là dry-run, không motor outcome. Source PR102 nói tile_3_1 có21 HOLD frames nhưng không tìm thấy log/summary trong hai head; chỉ giữ là owner-reported, không đưa vào figure hoặc acceptance. DQK quy pitch change cho mount/handling; chưa đo độc lập, không suy ra repaired socket là nguyên nhân.','',
        'Review lại PR99:45 CPU tests passed/17,54s; config/main-path/pose-cap fixes đã có, vẫn tái hiện overwrite x_3 khi thiếu x_2 và full-run coverage bị cap sai denominator. PR102 live sender cleanup/cutoff/trial4 vẫn chưa sửa. PR101 giữ head969a5e0 và findings09/11. PR100 HNHL chờ DQK; không có PR đủ điều kiện merge tại lần kiểm tra này. [Review99](../reviews/PR-99-2026-11-10.md), [review102](../reviews/PR-102-2026-11-10.md), [test log](../reviews/PR-99-2026-11-10-tests.log). [21 evidence/source CPU tests passed/4,21s](../week-06/tests_evidence_2026-11-10.log); gồm null distance/error, frame accuracy khác median bias, invalid samples và historical-source guards.','',
        '## HNHL cần tiếp tục, tránh làm lại phần DQK đã thử','',
        '- Đưa failed chair coverage/model comparisons vào Chương5/7; không chỉ giữ error của các estimate tốt. Editor dùng addendum này cùng F10 gốc.',
        '- DQK đang làm Experiment B/contact/reflection/ORG; chưa có candidate đạt chair+table+empty-floor diagnostic. HNHL nhận scripts/config/model/data hashes và raw held-out samples khi có, review labels/protocol rồi đánh giá; không hạ reflection threshold trên chính36 ảnh và tự báo PASS.',
        '- D3 two-person reviewed IDs, gallery≥5 identities, D5 session độc lập, world poses/door range/F11, clock-synced raw latency/F7 và combined RTX4050 vẫn thiếu. Person depth sets không thay các bộ dữ liệu này.',
        '- Converter D3 và paired F18 đã có trong PR100; plan còn ghi chưa viết/chưa đo là stale. Buổi DQK một mình09/11 không thay graded session/ESP32/Phase2/T2 của nhóm.',
        '- Giữ mốc16/11 figures,18/11 draft,23/11 submit; phần chưa đo ghi in progress. Matte removal/higher camera/ORG còn là scope/design proposals chưa merge; không tự đổi gate. Source đặt nhãn một số rounds là10/11 evening/night; exact execution time chưa được HNHL xác minh.','']
    (OUT/(NAME+'.md')).write_text('\n'.join(lines),encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-source',action='store_true')
    if parser.parse_args().import_source:
        import_source()
    metrics = collect_nov10()
    (OUT/(NAME+'.json')).write_text(json.dumps(metrics,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    plot_availability(metrics)
    write_report(metrics)
    from tools.build_midterm_hnhl_nov09 import chapter_text,collect_update
    (OUT/'chapter-05-current.md').write_text(chapter_text(collect_update()),encoding='utf-8')
    print('Built10/11 addendum from archived source; no inference or motors')


if __name__=='__main__':
    main()
