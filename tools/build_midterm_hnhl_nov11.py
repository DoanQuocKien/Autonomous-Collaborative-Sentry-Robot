"""Post-merge HNHL midterm update and attributed Experiment B evidence, 11/11."""
import argparse
import csv
import hashlib
import io
import json
import subprocess

import numpy as np

from tools.build_midterm_hnhl import ROOT, OUT, evidence_bytes
from tools.build_midterm_hnhl_nov10 import range_stats

MAIN = 'c14db20ab472d58964946c3c643c85dab70f54e1'
B_HEAD = 'e13dca7e0b4d0a996b3a7685e0de5529fb515707'
B_PATH = 'reports/DoanQuocKien/week-06/experiment_B/'
CLASS = 'reports/DoanQuocKien/week-06/classroom_1109/'
ARCHIVE = OUT/'experiment-B-evidence-2026-11-11'
NAME = 'update-2026-11-11'


def git_bytes(commit,path):
    return subprocess.run(['git','show',commit+':'+path],cwd=ROOT,capture_output=True,check=True).stdout.replace(b'\r\n',b'\n')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def import_source():
    if ARCHIVE.exists():
        raise FileExistsError('historical archive exists; do not overwrite')
    paths = ['README.md']+['results/'+n+'.json' for n in ('train_log','eval_org_ft',
        'judge_configured','judge_org_ft','judge_org_ft_freespace')]
    pending = [(path,git_bytes(B_HEAD,B_PATH+path)) for path in paths]
    ARCHIVE.mkdir(parents=True)
    entries = []
    for path,data in pending:
        dest = ARCHIVE/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(data)
        entries.append(dict(archive=path,source_commit=B_HEAD,source_path=B_PATH+path,
            source_url='https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/blob/'+B_HEAD+'/'+B_PATH+path,
            sha256=digest(data),transformation='CRLF to LF only; owner-reported experiment, not approved code'))
    (ARCHIVE/'provenance.json').write_text(json.dumps(dict(source_head=B_HEAD,
        branch='DoanQuocKien/w06-experiment-b',merged=False,files=entries),indent=2)+'\n',encoding='utf-8')


def judge_summary(doc):
    objects = {(name,oid):row for name,s in doc['sets'].items() for oid,row in s.get('objects',{}).items()}
    found = {key:row for key,row in objects.items() if row['found_fraction']>=.5}
    errors = [abs(row['median_error_m']) for row in found.values()]
    summary = doc['summary']
    assert len(objects)==summary['objects'] and len(found)==summary['found_in_half_the_frames']
    median = round(float(np.median(errors)),3) if errors else None
    reported_median=summary['median_abs_error_m_of_found']
    # Per-object values were rounded before serialization; their recomputed
    # median can differ by one last reported digit from the raw summary.
    assert (median is None)==(reported_median is None)
    if median is not None:
        assert abs(median-reported_median)<=.00100001
    near = {key for key,row in objects.items() if row['tape_m']<=1.2}
    return dict(objects=len(objects),found=len(found),missed=len(objects)-len(found),
        median_abs_error_m_of_found=reported_median,recomputed_from_rounded_rows_m=median,
        within_15cm_of_found=sum(e<=.15 for e in errors),
        chairs_found=sum(row['label']=='chair' for row in found.values()),
        near_objects=len(near),near_found=len(near & found.keys()),
        far_found=sum(row['tape_m']>1.2 for row in found.values()),
        source_matching_gates=summary['gates'],acceptance=False)


def temporal_scopes(doc):
    return dict(tape_m=doc['tape'],all_smoothed=range_stats(doc['smoothed'],doc['tape']),
        full_window=range_stats(doc['smoothed'][9:],doc['tape']),warmup_samples_excluded=9)


def collect_nov11():
    registry = {}
    def source(key,path,commit=None):
        data = git_bytes(commit,path) if commit else evidence_bytes(ROOT/path)
        registry[key] = dict(path=path,sha256=digest(data))
        if commit:
            registry[key]['git_commit']=commit
        return data
    provenance = json.loads((ARCHIVE/'provenance.json').read_text(encoding='utf-8'))
    for i,entry in enumerate(provenance['files']):
        data = source('B%d'%i,(ARCHIVE/entry['archive']).relative_to(ROOT).as_posix())
        assert digest(data)==entry['sha256'],'B source drift'
    source('B-provenance',(ARCHIVE/'provenance.json').relative_to(ROOT).as_posix())
    for name in ('README.md','scripts/PROVENANCE.md','scripts/anthro_temporal.py',
                 'pursuit/tile_3_1/log.csv','pursuit/tile_3_1/summary.json'):
        source('merged-'+name,CLASS+name,MAIN)
    source('safety-note','reports/DoanQuocKien/week-05/home_1107_link_safety/README.md',MAIN)
    reviews = {}
    for n in (99,102,103):
        prefix='reports/HuynhNguyenHoaiLoc/reviews/PR-%d-2026-11-11'%n
        for suffix in ('.md','.json','-merge.json','-tests.log'):
            data=source('review%d%s'%(n,suffix),prefix+suffix)
            if suffix=='-merge.json':
                reviews[str(n)]=json.loads(data)
                assert reviews[str(n)]['merged']
    log103=source('PR103-integrated-tests','reports/HuynhNguyenHoaiLoc/reviews/PR-103-2026-11-11-integrated-tests.log')
    assert b'667 passed, 3 skipped, 4 deselected in 56.96s' in log103
    merged103=reviews['103']['merge_commit_sha']
    for path in ('tools/org_seg.py','tools/org_seg_judge.py','tests/test_org_seg.py',B_PATH+'README.md'):
        source('PR103-final-'+path,path,merged103)
    log=source('combined-tests','reports/HuynhNguyenHoaiLoc/reviews/combined-2026-11-11-tests.log')
    assert b'661 passed, 3 skipped, 4 deselected in 51.51s' in log
    own_log=source('hnhl-fulltests','reports/HuynhNguyenHoaiLoc/week-06/tests_merged_2026-11-11.log')
    assert b'705 passed, 2 skipped, 4 deselected in 51.48s' in own_log
    final_log=source('hnhl-final-tests','reports/HuynhNguyenHoaiLoc/week-06/tests_final_2026-11-11.log')
    assert b'711 passed, 2 skipped, 4 deselected in 51.06s' in final_log
    source('hnhl-before-workspace-config','reports/HuynhNguyenHoaiLoc/week-06/tests_before_workspace_config_2026-11-11.log')
    source('initial-failure','reports/HuynhNguyenHoaiLoc/reviews/PR-99-2026-11-11-before-fix-tests.log')
    rows=list(csv.DictReader(io.StringIO(git_bytes(MAIN,CLASS+'pursuit/tile_3_1/log.csv').decode())))
    hold=[r for r in rows if r['mode']=='HOLD']
    groups=[]
    for r in hold:
        t=float(r['t'])
        if not groups or t-groups[-1]['last_t']>.2:
            groups.append(dict(first_t=t,last_t=t,rows=1))
        else:
            groups[-1]['last_t']=t
            groups[-1]['rows']+=1
    band=[r for r in rows if 3.4<=float(r['t'])<=7.4]
    a=json.loads(source('merged-temporal-json',CLASS+'experiment_A_anthro_temporal.json',MAIN))
    def b_read(name):
        return json.loads((ARCHIVE/'results'/(name+'.json')).read_text(encoding='utf-8'))
    configured,obstacle,free=[b_read(n) for n in ('judge_configured','judge_org_ft','judge_org_ft_freespace')]
    reports={k:judge_summary(v) for k,v in [('configured',configured),('obstacle',obstacle),('freespace',free)]}
    near_union=set()
    for doc in (obstacle,free):
        near_union.update((name,oid) for name,s in doc['sets'].items() for oid,r in s.get('objects',{}).items()
                          if r['tape_m']<=1.2 and r['found_fraction']>=.5)
    org=b_read('eval_org_ft')
    assert sum(s['images'] for s in org['per_scene'].values())==org['images']
    return dict(snapshot_date='2026-11-11',main_sha=merged103,evidence=registry,merged_prs=reviews,
        pr101_status='CHANGES_REQUESTED at969a5e0; no new head',pr100_status='open; DQK independent review pending',
        validation=dict(cpu_passed=661,skipped=3,gpu_deselected=4,seconds=51.51,motor_commands_sent=0),
        hnhl_validation_before103=dict(cpu_passed=705,skipped=2,gpu_deselected=4,seconds=51.48),
        hnhl_validation=dict(cpu_passed=711,skipped=2,gpu_deselected=4,seconds=51.06,
            skip_reasons=['checkerboard data missing','entrance D1 classroom data missing'],
            yolo_config_dir='data/ultralytics',yolo_autoinstall=False,
            new_gpu_benchmark=False,robot_commands_sent=0),
        tile3=dict(rows=len(rows),hold_rows=len(hold),hold_episodes=groups,
            stopped_pursue_rows_3p4_to_7p4=len(band),
            all_band_rows_stopped_pursue=all(r['mode']=='PURSUE' and float(r['v'])==float(r['w'])==0 for r in band),
            acceptance=False),
        temporal_scopes={k:temporal_scopes(v) for k,v in a.items()},
        experiment_B=dict(source_head=B_HEAD,code_merged=True,reviewed_head=reviews['103']['head_sha'],
            code_merge_sha=merged103,model_adopted=False,org_eval=org,
            d1=reports,posthoc_near_union_found=len(near_union),posthoc_union_is_frozen_rule=False,
            true_empty_floor_control_available=False,glare_failure='DQK reports24/24 frames in two chair marks; owner evidence only',
            independent_T1=False),
        acceptance=dict(d3=False,reid=False,independent_d5=False,map_world_truth=False,
            raw_latency=False,combined4050=False,pursuit_hold=False))


def update_chapter(text):
    text=text.replace('Phần HNHL cập nhật 10/11/2026','Phần HNHL cập nhật 11/11/2026')
    old=next(line for line in text.splitlines() if line.startswith('DQK bổ sung thử lớp'))
    return text.replace(old,
        'PR99/102/103 đã review, sửa cleanup/R1 validity/metric guards và merge11/11; code tests không thay T2. '
        'Tile_3_1 đã có902 rows:21 HOLD rows trong hai đoạn ngắn, còn80 rows3,4–7,4s là stopped PURSUE. '
        'Nguồn script giải thích trunk smooth score bỏ9 mẫu warm-up; ghi riêng full-series và full-window, không coi khác biệt đó là lỗi số liệu. '
        'Tooling Experiment B đã merge qua PR103; ORG fine-tune SegFormer-B0 có D1 coverage8/24 obstacle-route,6/24 free-space so với configured1/24; '
        'error0,041m chỉ trên8 objects đã tìm được. ORG false components≈1,87/ảnh, chair/glare/range failures và empty-floor control vẫn thiếu. '
        'Không đổi detector mặc định; code đã review, còn model accuracy chưa được HNHL đánh giá độc lập. Retest ghế cũ0/36 distances vẫn giữ; tape gốc khác lens-forward. '
        'PR101 còn findings09/11, PR100 chờ DQK. D3/gallery/D5 độc lập/F11/raw latency/combined4050/T2 chưa đủ. '
        '[Bổ sung11/11 và nội dung nhóm đã làm](update-2026-11-11.md). Chốt hình16/11, draft18/11, nộp23/11.')


def write_report(m):
    lines=['# HNHL — sau merge PR99/102/103 và kết quả Experiment B, 11/11/2026','',
        'PR99/102/103 đã APPROVE/merge vào main; [registry](update-2026-11-11.json) ghi final heads/merge SHAs. '
        'HNHL tích hợp main vào PR100, giữ snapshot cũ theo đúng thời điểm. PR101 vẫn request-changes; PR100 vẫn chờ DQK.','',
        '## Code và bằng chứng đã được bổ sung','',
        '- PR99: numbering holes/concurrent run claims, denominator full-span và finite preflight đã sửa. Review phát hiện race khi propagate inference failure; HNHL thêm join worker để sender close xong trước khi trả về.50 targeted tests đạt.',
        '- PR102: cleanup/cutoff/invalid-trial checks, trial4/schedule/converter-F18 notes và provenance được sửa. HNHL thêm reject khi R1 đã thả ở end check cùng hồi quy main-path;9 targeted tests đạt. Hai poll không chứng minh continuous hold;350ms/physical braking vẫn chưa nghiệm thu.',
        '- PR103:6 CPU tests riêng và667 integrated tests đạt; HNHL sửa zero-contact thành null, undefined denominators thành null, reject empty eval split và giữ checkpoint/log/tag cũ. Chấp thuận tooling/evidence, không adopt model. [Review103](../reviews/PR-103-2026-11-11.md).',
        '- Tích hợp chung: [661 CPU passed,3 skipped,4 GPU deselected/51,51s](../reviews/combined-2026-11-11-tests.log). Ba skip do checkerboard và XFeat weights thiếu ở isolated checkout. Review/merge evidence: [99](../reviews/PR-99-2026-11-11.md), [102](../reviews/PR-102-2026-11-11.md).',
        '- Trước103: [705 passed,2 skipped,4 GPU deselected/51,48s](../week-06/tests_merged_2026-11-11.log). Sau103: [711 passed,2 skipped,4 GPU deselected/51,06s](../week-06/tests_final_2026-11-11.log). Hai skip do checkerboard và D1 entrance classroom thiếu; local XFeat weights có sẵn nên ca real warped-reference CPU đã chạy. Không benchmark GPU mới, không robot/motor CLI.',
        '- Một lần kiểm tra cuối bị2 lỗi PermissionError khi Ultralytics đọc AppData; [log giữ lại](../week-06/tests_before_workspace_config_2026-11-11.log). Đã chạy lại với YOLO_CONFIG_DIR=data/ultralytics và YOLO_AUTOINSTALL=false trong workspace, không đổi code để bỏ qua các ca tracker.','',
        '## Tile3 và trunk: những khoảng trống nguồn đã được giải quyết','',
        'Tile_3_1 có902 rows,21 HOLD rows trong hai đoạn ngắn (xem JSON);80 rows trong3,4–7,4s cóv=w=0 nhưng modePURSUE/dead-band. Không gọi toàn khoảng đó là HOLD; không suy ra physical dwell/hold success. Source hiện đã có, thay trạng thái thiếu log của addendum10/11.','',
        'Script anthropometric và PROVENANCE mới có8 scripts, versions, hai weight SHA256, model IDs, priors0,50/0,49m và local paths. Một số script trước chưa được lưu, HF revisions không pin; raw person frames/weights vẫn private. Chênh lệch smooth percentages10/11 đã rõ: script chỉ chấm sau khi đầy window10, bỏ9 mẫu đầu. Bảng trước của HNHL dùng toàn series, nên không thể gọi hai tỷ lệ đó là mâu thuẫn. Giữ hai scopes dưới đây; đây là điều chỉnh cách đối chiếu của HNHL.','',
        '| Tape | Tất cả smooth samples: trong±0,15m | Full-window samples | Full-window: trong±0,15m |','| --: | --: | --: | --: |']
    for v in m['temporal_scopes'].values():
        lines.append('| %.2f m | %.1f%% (%d) | %d | %.1f%% |'%(v['tape_m'],100*v['all_smoothed']['frame_fraction_within_15cm'],v['all_smoothed']['samples'],v['full_window']['samples'],100*v['full_window']['frame_fraction_within_15cm']))
    lines += ['', '## Experiment B: DQK đã làm, chưa phải candidate được HNHL chấp thuận','',
        'Kết quả nguồn head e13dca7 được [archive trước review/merge](experiment-B-evidence-2026-11-11/provenance.json). Tooling đã merge qua PR103 head78a12ca sau khi thêm guards; không chạy lại hoặc đổi model/metrics lịch sử. Model chưa được nhận làm configured detector. SegFormer-B0 fine-tune3 classes trên ORG; dataset/weights local, không redistribute. Trên1.709 ORG test images: mIoU0,7924, ground IoU0,953, obstacle IoU0,4515, pixel P/R0,474/0,9046;1.920/2.207 objects found theo≥30%covered,3.190 false components≈1,87/ảnh. Contact median2px trên found objects của ảnh960×540, không phải mét trên D1.','',
        'D1 glossy-tile ruler24 objects (matching gates0,5m forward/0,4m lateral, every2frames). Một object được tính found khi matched≥50%frames; median error chỉ trong found subset, chưa phải complete detection/distance acceptance.','',
        '| Output | Found /24 | Missed | Median abs error của found | Trong±0,15m / found | Chairs found /10 |','| :-- | --: | --: | --: | --: | --: |']
    for name,v in m['experiment_B']['d1'].items():
        lines.append('| %s | %d | %d | %.3f m | %d/%d | %d |'%(name,v['found'],v['missed'],v['median_abs_error_m_of_found'],v['within_15cm_of_found'],v['found'],v['chairs_found']))
    lines += ['', 'Union obstacle/free-space near range tìm10/14 objects≤1,2m, nhưng chọn union sau khi xem kết quả, chưa frozen rule. Không gọi đây là recall của obstacle output đơn lẻ (obstacle7/14). Ngoài1,2m gần như không tìm được; ghế09/11 và glare vẫn fail ở nhiều mốc. Theo README DQK, obstacle-route tìm skid12/12 tại front-marker1,2m nhưng lens truth chưa chắc; free-space báo vật giả0,2–0,3m trong24/24 frames ở hai mốc do glare. Chưa có per-frame artifact để HNHL xác minh riêng kết quả mới đó.','',
        'empty_1 có ghế thật ở mép ảnh theo DQK, nên57/57 free-space components không phải false-stop rate trên sàn trống. Mô hình có tiến bộ gần camera nhưng chưa đủ thay configured detector; không D1/D5 T1/T2 PASS. Cần real empty-floor/table controls, glare/range>1,4m, held-out own-view data và live check. HNHL không train lại hoặc đổi threshold/default chỉ từ những bảng này.','',
        '## Phần HNHL còn thiếu và cách tiếp tục','',
        '- Đã bổ sung: review/code tích hợp, tile3 numeric source, thí nghiệm A provenance/warm-up scope và B comparison. Tránh làm lại các comparisons DQK đã có; nhận weights/raw/config/split hashes qua PR riêng để HNHL QA/evaluate candidate.',
        '- Vẫn thiếu reviewed D3≥60s hai người, gallery≥5 identities, independent D5/accuracy, F11 world truth/door range, F7 clock-synced raw latency, combined RTX4050 và robot T2.ORG cross-building evidence không thay các gate này.',
        '- Chốt hình16/11, draft18/11, submit23/11 giữ nguyên. Word01/11 giữ snapshot đã review; Chương5/7 Markdown hiện hành đã cập nhật. Code merge không nâng các kết quả chưa đo thành PASS.','']
    (OUT/(NAME+'.md')).write_text('\n'.join(lines),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-source',action='store_true')
    if parser.parse_args().import_source:
        import_source()
    m=collect_nov11()
    (OUT/(NAME+'.json')).write_text(json.dumps(m,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    write_report(m)
    from tools.build_midterm_hnhl_nov09 import collect_update,chapter_text
    (OUT/'chapter-05-current.md').write_text(chapter_text(collect_update()),encoding='utf-8')
    print('Built11/11 post-merge/evidence addendum; no inference or hardware')


if __name__=='__main__':
    main()
