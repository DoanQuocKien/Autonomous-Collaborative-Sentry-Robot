"""06/11 report update after DQK's camera-repair commit; no inference/HIL."""
import hashlib
import json
import re
import subprocess

from tools.build_midterm_hnhl import ROOT, OUT, evidence_bytes
from tools.build_midterm_hnhl_followup import collect_followup, current_chapter_text

# Pin the reachable cherry-pick so deleting the old DQK branch cannot break QA.
REPAIR_COMMIT = 'ae28fd6ddaf0fccfae43683b963de579ecf422e7'
ORIGINAL_REPAIR_COMMIT = '87db1bafdaa88c01b815648040d2b90e173126ad'
HNHL = 'reports/HuynhNguyenHoaiLoc/'
SOURCES = {
    'R01': ('docs/Implementation Plan.md', REPAIR_COMMIT),
    'R02': ('docs/Home Session Checklist 2026-11-04.md', REPAIR_COMMIT),
    'R03': ('docs/Classroom Tasks Week 6.md', REPAIR_COMMIT),
    'R04': ('docs/JetBot Notes.md', REPAIR_COMMIT),
    'R05': (HNHL+'midterm/github-2026-11-06.json', None),
    'R06': (HNHL+'reviews/PR-scan-2026-11-06.md', None),
    'R07': ('tools/prepare_d3_recording.py', None),
    'R08': (HNHL+'week-06/tests_recovery_2026-11-06.log', None),
}


def collect_recovery():
    raw, registry = {}, {}
    for key, (path, commit) in SOURCES.items():
        data = (subprocess.run(['git', 'show', commit+':'+path], cwd=ROOT, capture_output=True,
                              check=True).stdout.replace(b'\r\n', b'\n') if commit else evidence_bytes(ROOT/path))
        registry[key] = dict(path=path, sha256=hashlib.sha256(data).hexdigest())
        if commit:
            registry[key]['git_commit'] = commit
        raw[key] = json.loads(data) if path.endswith('.json') else data.decode('utf-8-sig')
    assert 'Robot camera repaired (2026-11-05' in raw['R01']
    assert 'no module was replaced' in raw['R01']
    assert all('Camera repaired (2026-11-05)' in raw[k] for k in ('R02', 'R03'))
    match = re.search(r'(\d+) passed in ([\d.]+)s', raw['R08'])
    if not match:
        raise ValueError('completed targeted test log required')
    github = raw['R05']
    assert [p['number'] for p in github['pull_requests']] == [99, 100]
    assert not any(p['merged'] for p in github['pull_requests'])
    return dict(snapshot_date='2026-11-06', timezone='Asia/Bangkok', evidence=registry,
        repair_original_commit=ORIGINAL_REPAIR_COMMIT, repair_integrated_commit=REPAIR_COMMIT,
        evidence_hash_policy='SHA256 after CRLF to LF; repair documents at explicit DQK commit',
        github=github, camera=dict(repair_reported_date='2026-11-05', reporter='DQK',
            original_socket_resoldered=True, module_replaced=False, video_restored_reported=True,
            hn_hl_hardware_verified=False, raw_repair_log_available=False,
            pose_remeasurement_verified=False, height_recheck_verified=False,
            reported_check=dict(frames=60, approximate_seconds=3.2, approximate_fps=18.6,
                                skipped_frames=1, dimensions=[640, 480], formal_latency_test=False)),
        d3_preparation=dict(tool='tools.prepare_d3_recording', preserves_capture_timestamps=True,
            splits_sequence_or_clock_resets=True, reviewed_labels=False,
            real_d3_available=False, new_recording=False),
        validation=dict(targeted_cpu_passed=int(match[1]), seconds=float(match[2]),
            scope='recording adapter, tracking/evaluator and historical source guards',
            full_suite_rerun=False, inference_rerun=False, hardware_trials=False),
        acceptance=dict(d3_id_switches_per_minute=None, target_relock_accuracy=None, reid_rank1=None,
            independent_d5_t1=False, real_map_vantage=False, g2_passed=False,
            rtx4050_combined_budget=False, new_t1_or_t2_pass=False),
        motor_commands_sent=0)


def recovery_chapter_text():
    text = current_chapter_text(collect_followup())
    old = next(line for line in text.splitlines() if line.startswith('Ngày 05/11 DQK báo camera'))
    replacement = ('Camera JetBot hỏng rồi được DQK báo đã sửa socket gốc ngày 05/11; stream hoạt động lại khoảng 18,6 FPS, '
        'không thay module (R01–R04). HNHL chưa kiểm tra robot hoặc raw log sửa chữa. Trước thu D3/D5 cần kiểm tra '
        'stream, độ bền socket/cáp và đo lại self-pose/height vì mount có thể đã đổi; không mặc định data mới dùng pose cũ. '
        'Việc khôi phục stream chưa cung cấp reviewed D3, gallery ≥5 người, map truth hay nghiệm thu T1/T2. '
        'PR #99 chưa sửa bốn finding và chưa merge tại snapshot 06/11; #100 đang chờ DQK review. '
        'Nếu thiếu evidence trước 16/11 thì ghi chưa đo, dùng simulation/replay có nhãn nguồn, không hạ tiêu chí. '
        'Full draft 18/11, nộp 23/11. [Cập nhật camera và D3 handoff 06/11](update-2026-11-06.md).')
    return text.replace('Phần HNHL cập nhật 05/11/2026', 'Phần HNHL cập nhật 06/11/2026').replace(old, replacement)


def write_update(metrics):
    count, seconds = metrics['validation']['targeted_cpu_passed'], metrics['validation']['seconds']
    text = f'''# Giữa kỳ HNHL — camera đã sửa, cập nhật 06/11/2026

Phạm vi HNHL không đổi: Chương 5 perception/tracking/GPU, kết quả liên quan Chương 7 và phụ lục. Chưa có thêm issue HNHL hoặc dataset mới được xác nhận. Điểm mới là commit DQK `87db1ba` báo camera sửa xong nhưng nằm trên nhánh #98 cũ sau merge; đã tích hợp vào PR #100 để DQK review. [Nguồn R01–R08](update-2026-11-06.json), [biên bản PR](../reviews/PR-scan-2026-11-06.md).

## Thay đổi so với bản 05/11

DQK ghi cửa hàng hàn lại socket gốc cùng ngày 05/11, không thay module; camera service và `/dev/video0` hoạt động. Kiểm tra được báo: 60 frame trong khoảng 3,2 s, khoảng 18,6 FPS, một frame bị bỏ, ảnh 640×480. Đây là số DQK báo trong tài liệu, chưa có raw log mới để HNHL kiểm tra, không phải phép đo latency hoặc tracking accuracy. DQK chưa xác minh độ bền sau va chạm/flex cáp và mount có đổi không; colour cast chưa so ảnh cũ.

**Không còn chặn do camera mất stream theo báo cáo DQK**, nhưng trước run được tính phải recheck stream/socket, chạy self-pose và đo lại lens height. Vì module gốc giữ nguyên, không tự hiệu chuẩn fisheye lại chỉ vì hàn socket; nếu frame/mount/intrinsics có dấu hiệu đổi thì DQK kiểm tra và ghi metadata phù hợp. Camera pose theo floor/session vẫn phải đo lại. Các frame cũ giữ calibration cũ.

| Việc HNHL | Đã làm trong lần cập nhật này | Phần vẫn cần người/data/robot |
| :-- | :-- | :-- |
| Chương 5/7 và kế hoạch | Bản hiện hành phản ánh camera repaired và giữ F18 đã đo | KR/DQK ghép báo cáo chung, review PR #100 |
| D3 handoff | Tool `prepare_d3_recording` chuyển JSONL thật sang replay epochs; kiểm tra JPEG/dimensions/hash, giữ timestamp, không ghi đè | DQK quay D3 ≥60s/hai người; HNHL review đầy đủ bbox/identity/visibility |
| Re-ID F14 | Contract/gallery/hash và evaluator hiện có | ≥5 identities, gallery/query đúng split; rank-1 vẫn null |
| F7/F11/D5 | Protocol và tool hiện có; camera đã phục hồi để chuẩn bị thu | Raw latency, sweep poses/truth, session D5 độc lập; chưa có T1/T2 mới |
| GPU F9/F18 | F18 RTX5060 đã có, không chạy lại để đổi ngày | Combined RTX4050 và accuracy độc lập, các model còn lại |

## Chuẩn bị gói D3 khi nhận recording thật

```powershell
.venv/Scripts/python.exe -m tools.prepare_d3_recording --recording data/D3/<session> --out-dir data/D3/<session>/prepared
```

Input là folder `tools.record` có `jetbot_meta.jsonl` và `jetbot/*.jpg`. Chỉ dùng export đã có `READY.json`. Mỗi `epoch-NNN/frames.json` giữ nguyên `t_cap`, đường dẫn ảnh tương đối tới recording gốc và hash ảnh. Sequence/clock lùi tạo epoch riêng; timestamp trùng hoặc sequence trùng bị từ chối. Gaps không đồng nghĩa packet loss. Không dùng FPS giả hoặc nối timestamp qua restart.

`truth-template.json` có mọi frame và `reviewed=false`, `annotation_template=true`, objects rỗng: đây là **template chưa gán nhãn**, không phải ground truth. HNHL gán bbox/identity/visibility đầy đủ, lưu thành `truth.json`, chỉ đặt reviewed=true sau review thật. Không đổi template thành nghiệm thu bằng cách bật một flag. Từng epoch cần đủ protocol độc lập; không nối hai clip ngắn để đủ ≥60s.

```powershell
.venv/Scripts/python.exe -m tools.track_replay --manifest data/D3/<session>/prepared/epoch-000/frames.json --out data/D3/<session>/prepared/epoch-000/predictions.json
.venv/Scripts/python.exe -m tools.evaluate_tracking --truth data/D3/<session>/prepared/epoch-000/truth.json --predictions data/D3/<session>/prepared/epoch-000/predictions.json --out reports/HuynhNguyenHoaiLoc/week-06/d3_<session>_metrics.json
```

Raw ảnh/metadata/templates/predictions luôn trong `data/`; chỉ aggregate metrics được review mới đưa vào reports. Reference/target NPZ phải đúng model/hash theo [D3 handoff](D3-HANDOFF-HNHL.md). Chưa có dữ liệu D3 thật trong lần này.

## PR và kiểm chứng

- #99 head `87a4a4a` không đổi: REQUEST_CHANGES trước vẫn còn, không merge hoặc đăng review trùng.
- #100 là PR HNHL chưa có approval độc lập: tiếp tục yêu cầu DQK, không tự approve/merge. Nội dung PR được cập nhật theo snapshot mới.
- Targeted CPU: **{count} passed, {seconds:.2f} s**, gồm adapter, tracker/evaluator và source guards; [log](../week-06/tests_recovery_2026-11-06.log). Những JPEG dùng trong T0 là fixture tổng hợp, không phải D3, không có inference/motor/HIL.
- F18/633 CPU tests ngày 05/11 giữ nguyên nguồn và ngày, không ghi như vừa đo lại. Word 01/11 giữ nguyên hash/render; [bản Chương 5 hiện hành](chapter-05-current.md) là Markdown để editor ghép.

Lịch chốt không đổi: 16/11 hình/thí nghiệm, 18/11 full draft, 23/11 nộp. Camera phục hồi không tự hoàn thành ID-switch/re-lock/rank-1, independent D5, map/vantage, G2 hoặc RTX4050 combined budget.
'''
    (OUT/'update-2026-11-06.md').write_text(text, encoding='utf-8')


def main():
    metrics = collect_recovery()
    (OUT/'update-2026-11-06.json').write_text(json.dumps(metrics, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    (OUT/'chapter-05-current.md').write_text(recovery_chapter_text(), encoding='utf-8')
    write_update(metrics)
    print('Built 06/11 camera-recovery addendum; no models/robot executed')


if __name__ == '__main__':
    main()
