"""09/11 teammate evidence/corrections. Offline; no robot or model calls."""
import argparse
import csv
import io
import json
import subprocess

import numpy as np

from tools.build_midterm_hnhl import ROOT, OUT, evidence_bytes
from tools.build_midterm_hnhl_team_update import COLUMNS, digest, summarize_rows, collect_team, team_chapter_text

ARCHIVE = OUT/'team-evidence-2026-11-09'
P99 = '969c06d3fda2f14a03e607b11c81ddaa78bc676a'
P101 = '4d733af9a8447e8159314430c3450d4f63b1799c'
P102 = '3f9cd936d4e7adcf8de923ed219615ce2f1d567e'
HOME = 'reports/DoanQuocKien/week-05/home_1107/'
LINK = 'reports/DoanQuocKien/week-05/home_1107_link_safety/'


def import_source():
    if ARCHIVE.exists(): raise FileExistsError('historical archive exists; do not overwrite')
    files = [('home/'+name, P99, HOME+name) for name in ['README.md',
        'pose/camera_pose_self_1108_1.json', 'pose/camera_pose_self_1108_2.json',
        'pose/camera_pose_self_1108_3.json', 'height_marks_1108_box_heights.json']]
    files += [('home/pursuit/'+run+'/'+name, P99, HOME+'pursuit/'+run+'/'+name)
              for run in ('home_5_1', 'home_6_1', 'static_1p8_0108_1') for name in ('log.csv', 'summary.json')]
    files += [('link/'+name, P102, LINK+name) for name in ('README.md', 'summary.json', 'trials.csv')]
    files += [('kr/phase3_replay_summary.json', P101, 'reports/kouun-rokku/week-06/phase3_replay_summary.json'),
              ('kr/chapter5_source.md', P101, 'reports/midterm_report_draft.md'),
              ('plan/carryover_source.md', P102, 'docs/Implementation Plan.md'),
              ('plan/classroom_source.md', P102, 'docs/Classroom Tasks Week 6.md')]
    pending, registry = [], []
    for archive, commit, path in files:
        original = subprocess.run(['git', 'show', commit+':'+path], cwd=ROOT, capture_output=True,
                                  check=True).stdout.replace(b'\r\n', b'\n')
        data, transformation = original, 'verbatim numeric/text source'
        if path.endswith('log.csv'):
            rows = list(csv.DictReader(io.StringIO(original.decode('utf-8-sig'))))
            out = io.StringIO(newline='')
            writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator='\n')
            writer.writeheader()
            writer.writerows({k:r[k] for k in COLUMNS} for r in rows)
            data, transformation = out.getvalue().encode(), 'retain numeric/control columns; omit raw track IDs/boxes'
        elif path.endswith('summary.json') and archive.startswith('home/'):
            value = json.loads(original)
            value.pop('target_id', None)
            data = (json.dumps(value, indent=2, allow_nan=False)+'\n').encode()
            transformation = 'omit target_id; source fractions remain unaccepted diagnostics'
        elif archive=='kr/chapter5_source.md':
            text = original.decode('utf-8')
            data = (('# Chương 5'+text.split('# Chương 5',1)[1].split('# Chương 6',1)[0]).rstrip()+'\n').encode()
            transformation = 'Chapter 5 excerpt only; trim trailing boundary blank lines; source assertions/links not endorsed'
        elif archive=='plan/carryover_source.md':
            text = original.decode('utf-8')
            excerpt = text.split('### Week 6 (',1)[1].split('### Week 7 (',1)[0]
            d5 = next(line for line in text.splitlines() if line.startswith('| D5 |'))
            data = ('### Week 6 ('+excerpt+'\n'+d5+'\n').encode()
            transformation = 'Week 6 and D5 scope excerpts; unmerged proposals retained as source'
        elif archive=='plan/classroom_source.md':
            data = '\n'.join(original.decode('utf-8').splitlines()[:10]).encode()
            transformation = 'top scheduling/banner excerpt only'
        pending.append((archive,data))
        registry.append(dict(archive=archive, source_commit=commit, source_path=path,
            source_url='https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/blob/'+commit+'/'+path.replace(' ','%20'),
            original_sha256=digest(original), archive_sha256=digest(data), transformation=transformation))
    ARCHIVE.mkdir(parents=True)
    for path,data in pending:
        dest=ARCHIVE/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(data)
    (ARCHIVE/'provenance.json').write_text(json.dumps(dict(imported_date='2026-11-09',
        source_prs={99:P99,101:P101,102:P102}, merged=False, files=registry),indent=2)+'\n',encoding='utf-8')


def summarize_link(rows):
    if not rows: raise ValueError('nonempty trial table required')
    values=np.array([float(r['stop_seen_after_s']) for r in rows])
    held=[int(r['r1_still_held']) for r in rows]
    if not np.isfinite(values).all() or (values<0).any() or any(v not in (0,1) for v in held):
        raise ValueError('finite nonnegative timing and binary R1 observations required')
    return dict(trials=len(rows), min_video_proxy_ms=float(values.min()*1000),
        median_video_proxy_ms=float(np.median(values)*1000), max_video_proxy_ms=float(values.max()*1000),
        r1_not_held_at_end_trials=[int(r['trial']) for r in rows if int(r['r1_still_held'])==0],
        limit_350ms_proven=False, violation_proven=False, mechanical_stop_measured=False)


def collect_update():
    registry={}
    provenance=json.loads((ARCHIVE/'provenance.json').read_text())
    def source(key,path):
        data=evidence_bytes(ROOT/path)
        registry[key]=dict(path=path,sha256=digest(data))
        return data
    for i,entry in enumerate(provenance['files']):
        data=source('U%02d'%i,(ARCHIVE/entry['archive']).relative_to(ROOT).as_posix())
        assert digest(data)==entry['archive_sha256'], 'archived teammate source changed'
    source('U-provenance',(ARCHIVE/'provenance.json').relative_to(ROOT).as_posix())
    github=json.loads(source('U-github','reports/HuynhNguyenHoaiLoc/midterm/github-2026-11-09.json'))
    for n in (99,101,102):
        source('U-review-%d'%n,'reports/HuynhNguyenHoaiLoc/reviews/PR-%d-2026-11-09.md'%n)
        source('U-tests-%d'%n,'reports/HuynhNguyenHoaiLoc/reviews/PR-%d-2026-11-09-tests.log'%n)
    test_log = source('U-evidence-tests', 'reports/HuynhNguyenHoaiLoc/week-06/tests_evidence_2026-11-09.log')
    assert b'14 passed' in test_log
    readme=(ARCHIVE/'home/README.md').read_text(encoding='utf-8')
    assert 'Withdrawn:' in readme and 'mount slipped' in readme and 'foot stance explains' in readme
    poses=[dict(file=p.name,**json.loads(p.read_text())) for p in sorted((ARCHIVE/'home/pose').glob('*.json'))]
    trials=list(csv.DictReader((ARCHIVE/'link/trials.csv').open(encoding='utf-8',newline='')))
    link=summarize_link(trials)
    runs={}
    for run in ('home_5_1','home_6_1','static_1p8_0108_1'):
        folder=ARCHIVE/'home/pursuit'/run
        rows=list(csv.DictReader((folder/'log.csv').open(encoding='utf-8',newline='')))
        summary=json.loads((folder/'summary.json').read_text())
        assert len(rows)==summary['frames']
        runs[run]=dict(stats=summarize_rows(rows),source_summary=summary,acceptance=False)
    plan=(ARCHIVE/'plan/carryover_source.md').read_text(encoding='utf-8')
    assert 'offered, not written' in plan and 'matte dropped' in plan
    kr=json.loads((ARCHIVE/'kr/phase3_replay_summary.json').read_text())
    return dict(snapshot_date='2026-11-09',evidence=registry,github=github,
        all_new_source_prs_merged=False,camera_poses=poses,runs=runs,link_video_proxy=link,
        source_corrections=dict(mount_slip_cause_withdrawn=True,foot_stance_cause_withdrawn=True,
            new_pitch_estimate_deg=-.64,physical_cause_known=False,
            home6_operator_tape_forward_m=1.77,home6_reported_estimate_m=1.27,
            ankle_and_box_height_not_adopted=True),
        kr_phase3=dict(source_status=kr['status'],tier=kr.get('evaluation_tier'),
            source_metrics=kr['metrics'],review_state='CHANGES_REQUESTED',robot_acceptance=False),
        plan_proposals=dict(classroom_nov9_postponed=True,replacement_date_confirmed=False,
            matte_scope_removal_proposed=True,merged=False,
            hnhl_converter_already_implemented=True,f18_already_measured=True),
        acceptance=dict(d3=False,reid=False,independent_d5=False,world_map=False,
            latency_cdf=False,rtx4050_combined=False,pursuit_hold=False),
        inference_rerun=False,motor_commands_sent=0)


def chapter_text(metrics):
    text=team_chapter_text(collect_team()).replace('Phần HNHL cập nhật 07/11/2026','Phần HNHL cập nhật 09/11/2026')
    old=next(line for line in text.splitlines() if line.startswith('DQK đã bổ sung pose sau sửa'))
    new=('DQK đã bổ sung các run 08/11 và rút lại giải thích mount-slip/foot-stance; nguyên nhân sai lệch vẫn chưa rõ. '
        'Self-pose pitch estimates đổi từ −4,26° sang −0,64°; đây chưa chứng minh cơ chế phần cứng. '
        'home_6_1 dừng khi log khoảng 1,27 m nhưng tape do DQK báo 1,77 m, nên không lấy in-band estimates làm accuracy hoặc pursuit PASS. '
        'Ankle/box-height ranging thử nghiệm chưa được chọn dùng. PR #102 báo video stop-proxy 481–524 ms; '
        'chưa chứng minh stop≤350 ms hay vi phạm, trial4 có R1 end=0. PR #101 thêm Phase3 và báo cáo nhóm nhưng còn lỗi stale/handoff/legality; '
        'không thay D3 hoặc thử robot. Lịch lớp 09/11 và scope matte đang được đề xuất đổi trong PR #102 chưa merge; '
        'chốt hình 16/11, draft 18/11, nộp 23/11 giữ nguyên. D3/re-ID/D5 độc lập/F11/raw latency/combined RTX4050 vẫn thiếu. '
        '[Audit mới và nội dung sửa cho editor](update-2026-11-09.md).')
    text = text.replace(old,new)
    if (OUT/'followup-pr101-2026-11-09.json').exists():
        from tools.build_midterm_hnhl_pr101_followup import update_chapter
        text = update_chapter(text)
    if (OUT/'update-2026-11-10.json').exists():
        from tools.build_midterm_hnhl_nov10 import update_chapter as update_nov10
        text = update_nov10(text)
    if (OUT/'update-2026-11-11.json').exists():
        from tools.build_midterm_hnhl_nov11 import update_chapter as update_nov11
        text = update_nov11(text)
    return text


def write_reports(m):
    lines=['# HNHL — đối chiếu PR và cập nhật giữa kỳ 09/11/2026','',
        'Đã review PR #99/#101/#102 tại các head ghi trong [snapshot](github-2026-11-09.json); cả ba có finding và chưa merge. #100 là PR HNHL đang chờ DQK review độc lập. Số đo mới thuộc DQK, Phase3/report draft thuộc KR; HNHL chỉ đối chiếu source/numeric logs, không chạy robot. [Registry](update-2026-11-09.json), [source provenance](team-evidence-2026-11-09/provenance.json).','',
        '## Sửa diễn giải cũ theo source mới','',
        '- DQK rút lại nguyên nhân “mount slipped/jolted trong run” và “foot stance giải thích chênh lệch”. Không biến các giả thuyết đó thành kết luận. Pitch estimate trước/sau run chỉ chênh khoảng 0,22°; các jump frame vẫn thấy nhưng chưa tách detector/motor/gear/link/camera causes.',
        '- Sau đó self-pose estimates ghi −4,26° và −0,64° (khoảng 3,62°). Chưa biết nguyên nhân và chưa xác nhận cơ chế camera vật lý; không suy ra sửa socket gây ra thay đổi.',
        '- home_6_1 báo đến nơi khoảng 1,27 m, nhưng tape forward sau run 1,77 m/left0,02; robot thực chỉ dịch khoảng 0,1 m theo owner. Không coi 28s estimated in-band là tracking hoặc pursuit accuracy. home_5_1 có event HOLD/MOVING/HOLD nhưng thiếu real-stop timestamps và position truth đồng bộ để chấm dwell/exit.',
        '- Ankle floor projection cho khoảng 3,4–4,6 m ở tape1,8 m; box-height cue chỉ được báo ổn định ngoài khoảng2,2 m trên một người, gần hơn có clipping/noise. Hai hướng đều chưa adopted; không tự thêm vào detector của HNHL hoặc claim band1,5–2,2 m đã giải quyết.','',
        '## Link-cut: có dữ liệu mới, chưa đủ safety PASS','',
        '| Trial | Video stop proxy ms | R1 ở cuối trial |','| --: | --: | --: |']
    trials=list(csv.DictReader((ARCHIVE/'link/trials.csv').open(encoding='utf-8',newline='')))
    for r in trials: lines.append(f"| {r['trial']} | {1000*float(r['stop_seen_after_s']):.0f} | {r['r1_still_held']} |")
    lines += ['', 'Median516 ms, range481–524 ms do source gọi là upper bounds từ frame-difference/arrival time. HNHL giữ là **video-derived stop proxy**, không phải motor/mechanical stop đo trực tiếp. Video delay của session này chưa đo; không trừ bound cũ0,16s để tuyên bố≤350ms, cũng không coi proxy>350ms là bằng chứng vi phạm. Trial4 có R1 end=0 trái câu “held for every trial”; chưa biết lúc release nên cause chưa xác nhận. R1-release test riêng vẫn thiếu. Không phải Edge safety/G2. F7 raw latency CDF vẫn chưa có: bảng proxy không thay t_cap/t_rx clock-synced.','',
        '## Phần nhóm đã làm và bản thảo KR cần sửa','',
        '| Phần HNHL | Thành viên khác đã cung cấp | Hành động/bằng chứng còn thiếu |','| :-- | :-- | :-- |',
        '| Camera/tape/pursuit | DQK có pose/run mới và corrections | Đã bổ sung giới hạn, giữ n=1 pilot/không T2; chưa có D3 hai người có nhãn |',
        '| F7/safety | DQK có5 stop-proxy observations | Bổ sung bảng trên; còn capture timestamps/clock sync và R1 trial |',
        '| Phase2→3 | KR có runner/replay T0 và report draft (#101) | Review phát hiện stale/handoff/illegal-command paths; không lấy source PASS làm HIL |',
        '| Chương5/7 | KR đã bắt đầu ghép báo cáo | [Gói sửa HNHL cho editor](HNHL-EDITOR-CORRECTIONS-1109.md) sửa8/9 coverage, D5/Wire, laptop deployment, re-ID/tracking scope, RTX4050 và figure paths |',
        '| Converter/F18 | PR #102 vẫn ghi converter offered/not written và FP16 pending | HNHL đã có prepare_d3_recording +27 tests (06/11), F18 measured (05/11) ở #100; đánh dấu implemented/pending review, không “chưa viết” |',
        '| D5/matte/lịch | PR #102 đề xuất bỏ matte và dời buổi09/11 | Chưa merge; ghi proposal, không tự thay gate hoặc gọi glossy dev-val là independent T1 |',
        '| F14/F11/combined4050 | Chưa tìm thấy nguồn mới đủ protocol | Giữ pending gallery≥5, world poses/truth, combined target GPU; source một người và T0 không thay các mục này |','',
        'Theo proposal #102, buổi lớp09/11 chuyển sang tuần sau, chưa chốt ngày. Mốc16/11 figures/experiments,18/11 draft,23/11 submit không đổi. Đề xuất glossy-only không xóa các điều kiện independent session/room/lighting, per-class P/R, distance và T2; matte comparison không được claim là đã đo.','',
        '## Kiểm chứng review','',
        '- #99:31 targeted tests/12,23s; xác nhận pulse expiry và save-after-end-battery-error đã cải thiện. Còn config/metrics/pose và allocator tên run có thể overwrite khi numbering có lỗ.',
        '- #101:53 targeted tests/12,17s; tái hiện cache A điều khiển khi active=B, false HOLD từ một observation, projector trả illegal command. Có5 broken figure links và claim combined4050 không đúng nguồn.',
        '- #102:1 estimator test/11,26s; live sender thiếu guaranteed cleanup, cutoff/protocol cần sửa. Không chạy motor CLI.',
        '- [Review99](../reviews/PR-99-2026-11-09.md), [review101](../reviews/PR-101-2026-11-09.md), [review102](../reviews/PR-102-2026-11-09.md). Nguồn mới chưa merge; báo cáo không chứng nhận code của các PR đó. Word/F18 và các snapshot cũ giữ nguyên.',
        '- Phần evidence HNHL: [14 CPU tests passed/4,41s](../week-06/tests_evidence_2026-11-09.log), gồm proxy/input guards, aggregate/clock và pinned historical-source checks. Checker riêng đối chiếu hashes, links và missing-acceptance guards; không chạy lại GPU hoặc robot.','']
    (OUT/'update-2026-11-09.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-source',action='store_true')
    args=parser.parse_args()
    if args.import_source: import_source()
    metrics=collect_update()
    (OUT/'update-2026-11-09.json').write_text(json.dumps(metrics,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    (OUT/'chapter-05-current.md').write_text(chapter_text(metrics),encoding='utf-8')
    write_reports(metrics)
    print('Built 09/11 evidence/correction addendum; no inference or hardware')


if __name__=='__main__': main()
