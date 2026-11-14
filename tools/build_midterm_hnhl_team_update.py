"""Archive/recompute numeric DQK pilot evidence for HNHL's 07/11 report.

Source PR #99 is unmerged and request-changes. No models or motors run here.
Raw track IDs/boxes are omitted from the archived telemetry/summary copies.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess

import numpy as np

from tools.build_midterm_hnhl import ROOT, OUT, evidence_bytes
from tools.build_midterm_hnhl_recovery import recovery_chapter_text

COMMIT = 'bb9f34115760edc40d16de4cece6edfdb40e1524'
REMOTE = 'reports/DoanQuocKien/week-05/home_1107/'
ARCHIVE = OUT/'team-evidence-2026-11-07'
RUNS = ('mark_A_1', 'mark_B_2', 'mark_C_1', 'home_1_3', 'home_3_1', 'home_4_1')
COLUMNS = ('t', 'dist_m', 'forward_m', 'left_m', 'yaw_err', 'v', 'w', 'mode', 'event')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def import_source():
    if ARCHIVE.exists():
        raise FileExistsError('source snapshot already exists; do not overwrite historical evidence')
    paths = ['README.md', 'floor_marks_1107_b_foot_pixels.json']
    paths += ['pose/camera_pose_self_%s.json' % s for s in ('1106_1', '1107_1', '1107_2')]
    paths += ['pursuit/%s/%s' % (run, name) for run in RUNS for name in ('log.csv', 'summary.json')]
    pending, registry = [], []
    for relative in paths:
        original = subprocess.run(['git', 'show', COMMIT+':'+REMOTE+relative], cwd=ROOT,
                                  capture_output=True, check=True).stdout.replace(b'\r\n', b'\n')
        archived, transformation = original, 'verbatim numeric/text evidence'
        if relative.endswith('log.csv'):
            rows = list(csv.DictReader(io.StringIO(original.decode('utf-8-sig'))))
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator='\n')
            writer.writeheader()
            writer.writerows({k: r[k] for k in COLUMNS} for r in rows)
            archived = stream.getvalue().encode()
            transformation = 'retain numeric/control columns only; omit track_id, tracks, feet_cut'
        if relative.endswith('summary.json'):
            value = json.loads(original)
            value.pop('target_id', None)
            archived = (json.dumps(value, indent=2, allow_nan=False)+'\n').encode()
            transformation = 'omit target_id; preserve source metrics including withdrawn/uncertified fractions'
        pending.append((relative, archived))
        registry.append(dict(archive=relative, source_path=REMOTE+relative, source_commit=COMMIT,
            source_url='https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/blob/'+COMMIT+'/'+REMOTE+relative,
            original_sha256=digest(original), archive_sha256=digest(archived), transformation=transformation))
    ARCHIVE.mkdir(parents=True)
    for relative, data in pending:
        path = ARCHIVE/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (ARCHIVE/'provenance.json').write_text(json.dumps(dict(owner='DQK', imported_date='2026-11-07',
        source_pr=99, source_pr_merged=False, source_commit=COMMIT,
        hash_policy='SHA256 after CRLF to LF; archived transformed files described per source', files=registry), indent=2)+'\n', encoding='utf-8')


def summarize_rows(rows):
    if not rows:
        raise ValueError('nonempty numeric telemetry required')
    t = np.array([float(r['t']) for r in rows])
    if not np.isfinite(t).all() or (np.diff(t) <= 0).any():
        raise ValueError('finite strictly increasing processed timestamps required')
    fwd = np.array([float(r['forward_m']) for r in rows if r['forward_m']])
    if not len(fwd) or not np.isfinite(fwd).all():
        raise ValueError('finite distance samples required')
    events = [dict(t=float(r['t']), event=r['event']) for r in rows if r['event']]
    gaps = np.diff(t)
    return dict(rows=len(rows), processed_span_s=float(t[-1]-t[0]),
        median_forward_m=float(np.median(fwd)), max_processed_gap_s=float(gaps.max()) if len(gaps) else None,
        processed_gaps_over_300ms=int((gaps > .3).sum()), events=events,
        acceptance=False, timestamps_scope='processed-loop relative wall clock, not camera capture time')


def collect_team():
    provenance = json.loads((ARCHIVE/'provenance.json').read_text(encoding='utf-8'))
    registry = {}
    def source(key, path, commit=None):
        data = (subprocess.run(['git', 'show', commit+':'+path], cwd=ROOT, capture_output=True,
                              check=True).stdout.replace(b'\r\n', b'\n') if commit else evidence_bytes(ROOT/path))
        registry[key] = dict(path=path, sha256=digest(data))
        if commit: registry[key]['git_commit'] = commit
        return data
    for i, row in enumerate(provenance['files']):
        data = source('T%02d' % i, (ARCHIVE/row['archive']).relative_to(ROOT).as_posix())
        assert digest(data) == row['archive_sha256'], 'archived source changed'
    source('T-provenance', (ARCHIVE/'provenance.json').relative_to(ROOT).as_posix())
    source('T-github', 'reports/HuynhNguyenHoaiLoc/midterm/github-2026-11-07.json')
    source('T-review', 'reports/HuynhNguyenHoaiLoc/reviews/PR-99-2026-11-07.md')
    source('T-tests', 'reports/HuynhNguyenHoaiLoc/reviews/PR-99-2026-11-07-tests.log')
    # Existing collaborators' evidence is historical, not new HNHL acceptance.
    pinned = '4c041b647529153debd4679f5669905206c3aea6'
    for key, path in {
        'T-KR-sim': 'reports/kouun-rokku/week-05/sim_pursuit_hold.json',
        'T-KR-hold': 'reports/kouun-rokku/week-05/hold_detector_metrics.json',
        'T-entrance': 'reports/DoanQuocKien/week-02/d1/entrance_bench_2026-10-12.md',
        'T-4050': 'reports/DoanQuocKien/week-01/gpu/gpu_baseline_rtx4050.json',
    }.items(): source(key, path, pinned)
    readme = (ARCHIVE/'README.md').read_text(encoding='utf-8')
    assert 'Distance in-band figure of this run is withdrawn' in readme
    poses = [dict(file=p.name, **json.loads(p.read_text(encoding='utf-8'))) for p in sorted((ARCHIVE/'pose').glob('*.json'))]
    runs = {}
    for run in RUNS:
        folder = ARCHIVE/'pursuit'/run
        with (folder/'log.csv').open(encoding='utf-8', newline='') as stream:
            stats = summarize_rows(list(csv.DictReader(stream)))
        summary = json.loads((folder/'summary.json').read_text(encoding='utf-8'))
        assert stats['rows'] == summary['frames']
        runs[run] = dict(stats=stats, source_summary=summary,
            withdrawn_distance_fraction=run=='home_1_3', not_a_pursuit_test=run=='home_3_1')
    found = re.search(r'\| 1\.2 / 1\.8 / 2\.4 m.*?\| ([\d.]+) / ([\d.]+) / ([\d.]+) \|', readme)
    if not found: raise ValueError('source distance table changed; review extraction')
    marks = json.loads((ARCHIVE/'floor_marks_1107_b_foot_pixels.json').read_text())
    points = []
    for i, truth in enumerate((1.2, 1.8, 2.4), 1):
        pixels = np.asarray(marks[str(truth)], dtype=float)
        if pixels.ndim!=2 or pixels.shape[1]!=2 or not np.isfinite(pixels).all():
            raise ValueError('finite paired foot pixels required')
        reading = float(found[i])
        points.append(dict(tape_forward_m=truth, source_reported_forward_m=reading,
            relative_error_pct=100*abs(reading-truth)/truth, samples=len(pixels),
            median_foot_row_px=float(np.median(pixels[:,1])), sd_foot_row_px=float(np.std(pixels[:,1]))))
    return dict(snapshot_date='2026-11-07', evidence=registry, source_commit=COMMIT, source_owner='DQK',
        source_pr=99, source_pr_merged=False, source_review_state='CHANGES_REQUESTED',
        camera_poses=poses, floor_diagnostic=points, runs=runs,
        hold_tape=dict(run='home_4_1', operator_reported_m=1.25, source_reported_estimate_m=1.37,
            source='archived DQK README, endpoint only; not timestamp-aligned truth', repeats=1),
        limitations=['one home room/person; not classroom, reviewed D3 or independent D5',
            'processed timestamps cannot provide video one-way latency or ID-switch truth',
            'source bbox/centering/in-band metrics affected by open PR99 findings; no acceptance claim',
            '3.5 px feet offset fitted on this session; not universal or furniture calibration',
            'pixel coordinate domain not documented; no new camera-pose fit from those pixels'],
        acceptance=dict(tracking_d3=False, reid=False, independent_d5=False, map_vantage=False,
                        video_latency_cdf=False, rtx4050_combined=False, pursuit_hold=False),
        inference_rerun=False, motor_commands_sent=0)


def plot_pilot():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with (ARCHIVE/'pursuit/home_4_1/log.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    t = [float(r['t']) for r in rows]
    fig, axes = plt.subplots(2, 1, figsize=(8, 5), sharex=True, layout='constrained')
    axes[0].plot(t, [float(r['dist_m']) if r['dist_m'] else np.nan for r in rows], lw=1.1, label='logged estimated planar range')
    axes[0].axhspan(1.0, 1.4, alpha=.12, color='green', label='planned standoff band (not ground truth)')
    axes[0].set(ylabel='estimated range (m)')
    axes[0].legend(fontsize=7, loc='upper right')
    axes[1].plot(t, [float(r['yaw_err'])/2 if r['yaw_err'] else np.nan for r in rows], lw=1, label='rectified offset / full width')
    axes[1].axhspan(-.1, .1, alpha=.12, color='green')
    axes[1].set(xlabel='processed-loop time (s), not capture timestamps', ylabel='centre offset / width')
    axes[1].legend(fontsize=7)
    for row in rows:
        if row['event']=='TARGET_STATIONARY':
            for ax in axes: ax.axvline(float(row['t']), color='#a34b28', ls='--', lw=1)
    for ax in axes: ax.grid(alpha=.2)
    fig.suptitle('F17 supplement  DQK home_4_1, one-person pilot, 2026-11-07\nLogged HOLD trigger; endpoint tape 1.25 m reported separately (not time-aligned)', fontsize=9)
    fig.savefig(OUT/'figures/F17_home_pilot.png', dpi=200)
    plt.close(fig)


def team_chapter_text(metrics):
    text = recovery_chapter_text().replace('Phần HNHL cập nhật 06/11/2026', 'Phần HNHL cập nhật 07/11/2026')
    old = next(line for line in text.splitlines() if line.startswith('Camera JetBot hỏng rồi'))
    new = ('DQK đã bổ sung pose sau sửa và các pilot một người tại nhà 06–07/11, còn ở PR #99 chưa merge. '
        'Pitch mới −4,68 đến −4,49° khác pose 30/10 khoảng 6,8°; roll thay đổi chưa được giải thích. '
        'Một lần HOLD có tape endpoint do DQK báo 1,25 m, nhưng chưa có step response/stop-time truth, hold exit hoặc người thứ hai. '
        'Không dùng pilot này thay D3, re-ID ≥5 identities hoặc T2 PASS. F7 raw latency, F11 world truth, independent D5 và combined RTX4050 vẫn thiếu. '
        'PR #99 tại head bb9f341 vẫn request-changes; #100 chờ DQK review. '
        '[Bảng đối chiếu bằng chứng của các thành viên và pilot mới](update-2026-11-07.md). '
        'Chốt hình 16/11, full draft 18/11, nộp 23/11; các mục chưa có bằng chứng giữ chưa đo.')
    text = text.replace(old, new)
    return text


def write_report(m):
    lines = ['# HNHL — bổ sung từ bằng chứng DQK/KR, 07/11/2026', '',
        'Đã kiểm tra PR và các nhánh/report của nhóm. Phần mới của DQK ở head `bb9f341` của PR #99, **chưa merge và đang request-changes**; đây là evidence được owner báo/commit, không phải HNHL chạy robot hoặc chứng nhận code đó đúng. [Registry và metrics](update-2026-11-07.json), [archive có provenance](team-evidence-2026-11-07/provenance.json), [re-review #99](../reviews/PR-99-2026-11-07.md).', '',
        '## Camera pose và distance diagnostic mới', '',
        '| Pose DQK sau sửa | Pitch ° | Roll ° | Spread ° | Marker frames |', '| :-- | --: | --: | --: | --: |']
    for p in m['camera_poses']:
        lines.append(f"| {p['file']} | {p['pitch_down_deg']:.2f} | {p['camera_roll_deg']:.2f} | {p['pitch_spread_deg']:.3f} | {p['marker_frames']} |")
    lines += ['', 'Height cơ khí giữ 0,100 m; self-pose ghi passed=true trong source, chưa là độc lập distance validation. Pose 30/10 pitch +2,15° khác sau sửa khoảng 6,8°; không áp pose cũ lên ảnh mới hoặc ngược lại. Pitch ba lần gần nhau; roll từ −2,08 đến +1,03° chưa giải thích. HNHL không fit lại pose hay suy ra repair là nguyên nhân chắc chắn.', '',
        '| Tape forward m | Reading forward DQK báo m | Absolute relative error % | Foot-row median px / samples |',
        '| --: | --: | --: | --: |']
    for p in m['floor_diagnostic']:
        lines.append(f"| {p['tape_forward_m']:.2f} | {p['source_reported_forward_m']:.2f} | {p['relative_error_pct']:.2f} | {p['median_foot_row_px']:.2f} / {p['samples']} |")
    lines += ['', 'Readings lấy từ bảng README DQK, không phải ước lượng HNHL mới; median pixel tính lại từ numeric source. Domain raw/rectified của pixel chưa được ghi rõ nên không chiếu lại hoặc fit pitch từ các điểm này. 1,8→2,4 m thật chỉ làm reading 1,57→1,63 m; đây là dấu hiệu độ nhạy/box contact, không phải detector T1. Offset 3,5 px là tuning của một floor/người, không chuyển sang D1/furniture/D5 hoặc dùng làm validation độc lập.', '',
        '## Pilot pursuit/HOLD mới của DQK — F17 bổ sung', '',
        '![F17 home pilot](figures/F17_home_pilot.png)', '',
        '`home_4_1`: 362 log rows, operator nói robot bắt đầu khoảng 2 m, logged TARGET_STATIONARY tại 7,45 s tính từ đầu run; một tape hold endpoint 1,25 m, source estimate khoảng 1,37 m. Endpoint tape không có timestamp alignment nên không vẽ thành ground-truth time series. Event time không phải dwell kể từ lúc người thật dừng. Bbox centring được đổi đơn vị half-width→full-width trên hình; chưa biến nó thành time-weighted acceptance.', '',
        '**Giữ nguyên rút kết quả:** `home_1_3` distance-in-band bị DQK withdraw vì true distance và estimate mâu thuẫn; `home_3_1` bắt đầu sẵn gần target nên không là pursuit test. Các fraction trong summary chỉ là source diagnostics, không dùng báo PASS. Không có walk-back/side-step chuẩn, real stop time, hold exit, re-centering time hoặc người thứ hai. Video gaps và command/pose bugs trong PR #99 làm hạn chế thêm các diễn giải.', '',
        '## Phần HNHL thiếu — người khác đã làm tới đâu?', '',
        '| Phần | Evidence của nhóm đã có | Bổ sung hợp lệ / còn thiếu |', '| :-- | :-- | :-- |',
        '| Camera pose/distance | DQK home_1107 pose/tape/pixel và pilot mới | Bổ sung bảng trên; chưa thay distance T1 ≥20 IDs/floors |',
        '| Tracking D3 / target re-lock | HNHL code/runtime; DQK home có một người; KR ByteTrack T0 | Vẫn thiếu reviewed JetBot ≥60s hai người, identity/visibility và target-event truth. Telemetry home không phải D3 labels |',
        '| Re-ID F14 | HNHL có hai OSNet runtime; D2 gallery thiếu | Chưa ai cung cấp gallery/query ≥5 người hợp lệ; rank-1 giữ null |',
        '| Map/vantage F11 | HNHL grid/vantage code; KR localization/F15 endpoints | Endpoint ArUco và simulated map không phải D1 sweep có poses/obstacle/door world truth |',
        '| F7 latency CDF | DQK W1 đã có p50/p95/max; home log chỉ processed-loop t | Không có raw t_cap/t_rx clock-synced mới trong gói này; không dựng CDF từ quantiles hoặc processed gaps |',
        '| F9 / F18 | DQK RTX4050 single-model, HNHL RTX5060 full mix + paired D5 precision | Đã đưa các kết quả có sẵn vào addenda trước; còn combined target RTX4050/independent accuracy |',
        '| D5 | DQK cung cấp session 24/10, HNHL sửa/train/dev-val | Gói home mới chỉ người/footpoint, chưa là D5 độc lập có nhãn class/empty controls |',
        '| Pursuit/HOLD / F17 | KR simulation/T0; DQK n=1 tape endpoint trên robot | Bổ sung pilot này, không gọi full T2 hoặc ID accuracy |',
        '| Cửa/edge F12/F20/F21 | KR/DQK đã có entrance bake-off, engine parity và Nano runtime | Dùng nguồn đã có, giữ per-door/optimistic threshold và freshness limits; không yêu cầu HNHL làm lại |', '',
        'Nguồn đã đối chiếu: [KR simulation](../../../reports/kouun-rokku/week-05/sim_pursuit_hold.json), [KR hold T0](../../../reports/kouun-rokku/week-05/hold_detector_metrics.json), [entrance bake-off](../../../reports/DoanQuocKien/week-02/d1/entrance_bench_2026-10-12.md), [RTX4050 baseline](../../../reports/DoanQuocKien/week-01/gpu/gpu_baseline_rtx4050.json). Registry pin các nguồn cũ theo commit; không coi kết quả mô phỏng là thử robot. F20/F21 và F15 đã tổng hợp ở [addendum 03/11](update-2026-11-03.md).', '',
        '## Kiểm chứng và trạng thái PR', '',
        'PR #99 head mới được review: 29 targeted CPU tests passed (10,58 s), integration main conflict-free; các main/sender failure paths vẫn lỗi nên đã REQUEST_CHANGES. Không motor/HIL/inference mới. PR #100 HNHL vẫn chờ DQK review; bổ sung evidence trên chính PR đó. Numeric archive bỏ track IDs/boxes khỏi telemetry/summary, giữ original/source hashes và mô tả chuyển đổi. Kết quả cũ Word/F18 và các null acceptance được bảo toàn.', '']
    (OUT/'update-2026-11-07.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-source', action='store_true')
    args = parser.parse_args()
    if args.import_source: import_source()
    metrics = collect_team()
    (OUT/'update-2026-11-07.json').write_text(json.dumps(metrics, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    plot_pilot()
    write_report(metrics)
    (OUT/'chapter-05-current.md').write_text(team_chapter_text(metrics), encoding='utf-8')
    print('Built 07/11 team-evidence supplement; no inference or hardware')


if __name__=='__main__': main()
