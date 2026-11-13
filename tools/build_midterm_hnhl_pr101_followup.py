"""Account for KR's PR101 revision without replacing the earlier 09/11 snapshot."""
import argparse
import hashlib
import json
import subprocess

from tools.build_midterm_hnhl import ROOT, OUT, evidence_bytes

HEAD = '969a5e0b61a804784344741f868c57fb2ecbd508'
NAME = 'followup-pr101-2026-11-09'
REVIEW = 'reports/HuynhNguyenHoaiLoc/reviews/PR-101-2026-11-09-r2'
ARCHIVE = OUT/'team-evidence-pr101-2026-11-09-r2'
SOURCE_PATHS = (
    'sentry/app/phase3_runner.py', 'tests/test_phase3_runner.py',
    'reports/midterm_report_draft.md', 'tools/check_midterm_page_budget.py',
    'reports/kouun-rokku/week-06.md',
    'reports/kouun-rokku/week-06/phase3_replay_summary.json',
)


def import_source():
    """Archive unmerged sources so later offline checks need no unmerged Git objects."""
    if ARCHIVE.exists():
        raise FileExistsError('historical archive exists; do not overwrite')
    pending, entries = [], []
    for path in SOURCE_PATHS:
        data = subprocess.run(['git', 'show', HEAD+':'+path], cwd=ROOT,
                              check=True, capture_output=True).stdout.replace(b'\r\n', b'\n')
        original_sha256 = hashlib.sha256(data).hexdigest()
        data = b'\n'.join(line.rstrip() for line in data.splitlines()).rstrip()+b'\n'
        relative = path+'.txt'
        pending.append((relative, data))
        entries.append(dict(source_path=path, source_commit=HEAD, archive=relative,
            original_sha256=original_sha256,
            sha256=hashlib.sha256(data).hexdigest(),
            source_url='https://github.com/DoanQuocKien/Autonomous-Collaborative-Sentry-Robot/blob/'+HEAD+'/'+path,
            transformation='CRLF to LF; trim trailing whitespace/EOF blank lines; source claims not endorsed'))
    ARCHIVE.mkdir(parents=True)
    for relative, data in pending:
        destination = ARCHIVE/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    (ARCHIVE/'provenance.json').write_text(json.dumps(dict(source_head=HEAD,
        source_pr=101, merged=False, files=entries), indent=2)+'\n', encoding='utf-8')


def collect_followup():
    registry = {}
    provenance_path = ARCHIVE/'provenance.json'
    provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
    assert provenance['source_head'] == HEAD and not provenance['merged']
    assert tuple(row['source_path'] for row in provenance['files']) == SOURCE_PATHS
    for index, entry in enumerate(provenance['files']):
        path = (ARCHIVE/entry['archive']).relative_to(ROOT).as_posix()
        data = evidence_bytes(ROOT/path)
        assert hashlib.sha256(data).hexdigest() == entry['sha256'], 'archived source drift'
        registry['K%d' % index] = dict(path=path, source_commit=HEAD,
            source_path=entry['source_path'], sha256=entry['sha256'])
    registry['provenance'] = dict(path=provenance_path.relative_to(ROOT).as_posix(),
        sha256=hashlib.sha256(evidence_bytes(provenance_path)).hexdigest())
    local = {}
    for suffix in ('.md', '.json', '-tests.log', '-reproductions.json'):
        path = REVIEW+suffix
        data = evidence_bytes(ROOT/path)
        local[suffix] = data
        registry['review'+suffix] = dict(path=path, sha256=hashlib.sha256(data).hexdigest())
    review = json.loads(local['.json'])
    reproduction = json.loads(local['-reproductions.json'])
    assert review['head_sha'] == HEAD and review['state'] == 'CHANGES_REQUESTED'
    assert reproduction['head'] == HEAD and reproduction['motor_commands_sent'] == 0
    assert b'58 passed in 14.73s' in local['-tests.log']
    return dict(snapshot_date='2026-11-09', source_pr=101, source_head=HEAD,
        source_pr_merged=False, main_sha='4c041b647529153debd4679f5669905206c3aea6',
        review_url=review['review_url'], review_state=review['state'],
        evidence=registry, validation=dict(tests_passed=58, seconds=14.73,
            reproductions=reproduction),
        fixed=['single-sample cached observation false HOLD',
               'cached position across FIFO identity handoff',
               'finite command projection example and sweep',
               'five original image links', 'most HNHL result scope corrections'],
        remaining=['external observation API not consumed',
                   'HOLD/controller divergence after no-tick observation gap',
                   'NaN projector becomes full-forward motion',
                   'distance T1 PASS claim, vector destination, missing F18/pilot caveats'],
        new_experimental_data=False,
        acceptance=dict(d3=False, reid=False, independent_d5=False, world_map=False,
            latency_cdf=False, rtx4050_combined=False, pursuit_hold=False))


def update_chapter(text):
    return text.replace(
        'PR #101 thêm Phase3 và báo cáo nhóm nhưng còn lỗi stale/handoff/legality;',
        'PR #101 head969a5e0 đã sửa các ví dụ stale/handoff/projector hữu hạn và figure links; '
        'review lại còn lỗi observation API, HOLD sau gap và projector NaN. '
        '[Theo dõi bản sửa KR](followup-pr101-2026-11-09.md);')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-source', action='store_true')
    if parser.parse_args().import_source:
        import_source()
    result = collect_followup()
    (OUT/(NAME+'.json')).write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    text = '''# HNHL — cập nhật sau bản sửa PR101, 09/11/2026

Đối chiếu PR101 head `969a5e0` sau review trước đó cùng ngày. Đây là cập nhật code/bản thảo của KR, **không có dữ liệu thí nghiệm mới**. Snapshot [audit trước](update-2026-11-09.md) giữ nguyên theo head4d733af; đọc trạng thái dưới đây cho bản mới. [Registry](followup-pr101-2026-11-09.json), [review đã đăng](../reviews/PR-101-2026-11-09-r2.md).

## Phần KR đã sửa và HNHL đã đối chiếu

- Single-sample cached observation không còn tự tạo HOLD; FIFO handoff đã reset target/controller caches.
- Projector xử lý đúng ví dụ v0,55/w0,30 và finite grid sweep. Chưa được gọi là an toàn với mọi input: NaN vẫn biến thành full-forward(1,0).
- Năm figure links cũ đã sửa. Audit tìm đủ9 chương/5 ảnh, ước lượng13,1 trang; `rendered_layout_verified=False`, chưa xác nhận layout10–15trang.
- Chương5 đã ghi đúng8/9 IDs, Wire recall0, D5 cùng session, face FAR46,40%, tracker trên laptop và phạm vi RTX5060/4050. Không yêu cầu KR làm lại các sửa đổi đã có.

## Phần vẫn cần sửa trước merge

- `observe_target(..., target_id=...)` rồi `step` không truyền target_pos không cập nhật controller; observation mới bị bỏ qua. Cần consume measurement một lần, giữ timestamp và identity.
- Sau HOLD, nếu mất cả control ticks hơn1s rồi nhận frame mới, controller chuyển PURSUE nhưng state machine còn HOLD; các frame người đi tiếp vẫn bị ép v=0. Cần xử lý TARGET_LOST/gap trước khi thay timestamp.
- Projector phải reject NaN/Inf trước min/max; hiện NaN cho ra(1,0), trái fail-safe.
- Chương7 vẫn gọi distance “ĐẠT T1” dù p90=20,91% và chỉ8/9 IDs, chưa đủ≥20. Chương5.5 vẫn nói gửi appearance vector sang JetBot; thực tế queue/tracker ở laptop. Cần F18 và caveats DQK đã có trong PR100, không suy ra nhận diện người thật từ synthetic parity.

Kiểm chứng: [58 targeted CPU tests passed/14,73s](../reviews/PR-101-2026-11-09-r2-tests.log); [kết quả tái hiện và page audit](../reviews/PR-101-2026-11-09-r2-reproductions.json). Không chạy motor CLI hoặc robot. Các kiểm thử hiện có chưa bao phủ lỗi còn lại; đã REQUEST_CHANGES tại head này, chưa merge.

PR99/102 giữ nguyên các head đã review, chưa có bản sửa; PR100 HNHL chờ DQK. Không có PR mới merge hoặc issue mở ở lần kiểm tra này. D3 reviewed, gallery≥5, D5 độc lập, F11 world truth, F7 raw latency, combined RTX4050 và robot acceptance vẫn thiếu. Các nguồn mới không thay những mục đó.

Đối với editor, dùng [Chương5 hiện hành](chapter-05-current.md), [hàng Chương7](chapter-07-rows.md) và [gói sửa cụ thể](HNHL-EDITOR-CORRECTIONS-1109.md). Ngày chốt hình16/11, draft18/11 và nộp23/11 không đổi. Converter/F18 đã thực hiện trong PR100; không có điểm nghiệm thu mới để chuyển pending thành PASS.
'''
    (OUT/(NAME+'.md')).write_text(text, encoding='utf-8')
    from tools.build_midterm_hnhl_nov09 import chapter_text, collect_update
    (OUT/'chapter-05-current.md').write_text(chapter_text(collect_update()), encoding='utf-8')
    print('Updated PR101 follow-up; no inference or hardware')


if __name__ == '__main__':
    main()
