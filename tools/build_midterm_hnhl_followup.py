"""Build the 05/11 HNHL addendum and F18 from saved measurements, offline."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from tools.build_midterm_hnhl import ROOT, OUT, collect, evidence_bytes
from tools.compare_d5_precision import delta, summarize_latency

BASE = '4c041b647529153debd4679f5669905206c3aea6'
HNHL = 'reports/HuynhNguyenHoaiLoc/'
SOURCES = {
    'N01': ('docs/Implementation Plan.md', BASE),
    'N02': ('docs/Home Session Checklist 2026-11-04.md', BASE),
    'N03': ('docs/Classroom Tasks Week 6.md', BASE),
    'N04': ('docs/JetBot Notes.md', BASE),
    'N05': (HNHL + 'week-06/d5_precision_2026-11-05.json', None),
    'N06': (HNHL + 'midterm/github-2026-11-05.json', None),
    'N07': ('tools/compare_d5_precision.py', None),
    'N08': (HNHL + 'reviews/PR-98-2026-11-05.md', None),
    'N09': (HNHL + 'reviews/PR-99-2026-11-05.md', None),
    'N10': (HNHL + 'week-06/tests_cpu_2026-11-05.log', None),
    'N11': (HNHL + 'week-04/d5_corrected_validation.json', None),
}


def collect_followup():
    raw, registry = {}, {}
    for key, (path, commit) in SOURCES.items():
        if commit:
            data = subprocess.run(['git', 'show', commit + ':' + path], cwd=ROOT,
                                  capture_output=True, check=True).stdout.replace(b'\r\n', b'\n')
        else:
            data = evidence_bytes(ROOT / path)
        registry[key] = dict(path=path, sha256=hashlib.sha256(data).hexdigest())
        if commit:
            registry[key]['git_commit'] = commit
        raw[key] = json.loads(data) if path.endswith('.json') else data.decode('utf-8-sig')
    report, old = raw['N05'], raw['N11']
    assert report['weights_sha256'] == old['models']['640']['weights_sha256']
    assert report['provenance'] == old['provenance']
    assert report['provenance']['split_counts']['val'] == len(report['validation_inputs']) == 90
    assert 'Robot camera damaged (2026-11-05' in raw['N01']
    assert 'cannot pass while Stage A is dropped' in raw['N01']
    assert report['independent_t1_passed'] is False and report['robot_trials'] is False
    assert report['rtx4050_verified'] is False and report['tensorrt_measured'] is False
    assert report['comparison'] == delta(report['precisions']['32'], report['precisions']['16'])
    for bits in (32, 16):
        row = report['precisions'][str(bits)]
        assert row['actual_execution'] == dict(input_dtype='torch.float' + str(bits), parameter_dtype='torch.float' + str(bits), device='cuda:0')
        assert row['weights_sha256'] == report['weights_sha256']
        assert row['latency'] == summarize_latency(row['latency_ms'])
        assert row['accuracy']['images'] == 90
        assert row['validation_forward_calls'] >= 90
        assert row['latency']['samples'] == 90 * report['protocol']['repeats']
    github = raw['N06']
    assert next(p for p in github['pull_requests'] if p['number'] == 98)['merged'] is True
    assert next(p for p in github['pull_requests'] if p['number'] == 99)['merged'] is False
    cpu = re.search(r'(\d+) passed, (\d+) skipped, (\d+) deselected in ([\d.]+)s', raw['N10'])
    if not cpu:
        raise ValueError('completed CPU suite summary required')
    return dict(snapshot_date='2026-11-05', timezone='Asia/Bangkok', base_main_sha=BASE,
        evidence=registry, evidence_hash_policy='SHA256 after CRLF to LF; historical plans use explicit git_commit',
        github=github, camera=dict(robot_video_available=False, incident_date='2026-11-05', source='N01/N04',
                                  repair_verified=False, new_camera_calibration_required_if_replaced=True),
        f18=dict(protocol=report['protocol'], results={k: {f: v[f] for f in ('gpu', 'actual_execution', 'latency',
            'torch_peak_allocated_mib', 'torch_peak_reserved_mib', 'nvml_device_used_peak_mib', 'accuracy')}
            for k, v in report['precisions'].items()}, comparison=report['comparison'],
            same_checkpoint_and_development_dataset_verified=True, tensorrt_measured=False,
            independent_accuracy=False, deployment_precision_changed=False),
        acceptance=dict(w5_fully_accepted=False, d3_id_switches_per_minute=None, target_relock_accuracy=None,
                        reid_rank1=None, independent_d5_t1=False, real_map_vantage=False,
                        raw_latency_cdf=False, rtx4050_combined_budget=False, g2_passed=False),
        deadlines=dict(figures_freeze='2026-11-16', internal_draft='2026-11-18', submission='2026-11-23'),
        validation=dict(cpu_passed=int(cpu[1]), missing_data_skips=int(cpu[2]), gpu_deselected=int(cpu[3]),
                        seconds=float(cpu[4]), cuda_comparison_executed=True, robot_trials=False),
        robot_trials=False, motor_commands_sent=0)


def plot_f18(metrics):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    rows = [metrics['f18']['results'][k] for k in ('32', '16')]
    labels, colors = ['FP32', 'FP16'], ['#365c83', '#bd6a34']
    fig, axes = plt.subplots(2, 2, figsize=(8, 5.8), layout='constrained')
    ax = axes[0, 0]
    bars = ax.bar(labels, [r['latency']['fps'] for r in rows], color=colors)
    ax.bar_label(bars, fmt='%.2f', padding=3)
    ax.set(title='Synchronized predict throughput', ylabel='frames / second', ylim=(0, 155))
    ax = axes[0, 1]
    x = np.arange(2)
    for offset, key, name in [(-.18, 'p50_ms', 'p50'), (.18, 'p95_ms', 'p95')]:
        bars = ax.bar(x + offset, [r['latency'][key] for r in rows], .35, label=name)
        ax.bar_label(bars, fmt='%.2f', padding=3, fontsize=8)
    ax.set(xticks=x, xticklabels=labels, title='Predict wall latency', ylabel='ms', ylim=(0, 21))
    ax.legend(fontsize=8)
    ax = axes[1, 0]
    for offset, key, name in [(-.18, 'torch_peak_allocated_mib', 'allocated'), (.18, 'torch_peak_reserved_mib', 'reserved')]:
        bars = ax.bar(x + offset, [r[key] for r in rows], .35, label=name)
        ax.bar_label(bars, fmt='%.2f', padding=3, fontsize=8)
    ax.set(xticks=x, xticklabels=labels, title='PyTorch allocator peak during predict', ylabel='MiB (not whole-device VRAM)', ylim=(0, 76))
    ax.legend(fontsize=8)
    ax = axes[1, 1]
    for offset, key, name in [(-.18, 'map50', 'mAP50'), (.18, 'map50_95', 'mAP50-95')]:
        bars = ax.bar(x + offset, [100*r['accuracy'][key] for r in rows], .35, label=name)
        ax.bar_label(bars, fmt='%.3f', padding=3, fontsize=8)
    ax.set(xticks=x, xticklabels=labels, title='90 D5 development images', ylabel='AP (%)', ylim=(0, 120))
    ax.legend(fontsize=8, ncol=2)
    for ax in axes.flat:
        ax.grid(axis='y', alpha=.18)
        ax.set_axisbelow(True)
    fig.suptitle('F18  Native PyTorch CUDA on RTX 5060 Laptop\n640 square, batch 1; same checkpoint and labels; not TensorRT or independent T1', fontsize=10)
    fig.savefig(OUT / 'figures/F18_d5_precision.png', dpi=200)
    plt.close(fig)


def write_markdown(m):
    rows, comparison = m['f18']['results'], m['f18']['comparison']
    lines = ['# Bổ sung giữa kỳ HNHL — 05/11/2026', '',
        'Đối chiếu main sau PR #98 (`4c041b6`). Bản này bổ sung các snapshot 01/11 và 03/11; editor dùng trạng thái mới bên dưới khi ghép. Word 01/11 giữ nguyên bản đã render, các số đo lịch sử không bị thay thế. Nguồn N01–N11 và hash/commit: [JSON](update-2026-11-05.json).', '',
        '## Kết quả mới F18: tốc độ, bộ nhớ và accuracy cùng dữ liệu', '',
        '![F18](figures/F18_d5_precision.png)', '',
        '| Native PyTorch CUDA | FPS | p50 / p95 ms | Peak allocated / reserved MiB | mAP50 / mAP50–95 % |',
        '| :-- | --: | --: | --: | --: |']
    for bits in ('32', '16'):
        r = rows[bits]
        lines.append(f"| FP{bits} | {r['latency']['fps']:.2f} | {r['latency']['p50_ms']:.2f} / {r['latency']['p95_ms']:.2f} | {r['torch_peak_allocated_mib']:.2f} / {r['torch_peak_reserved_mib']:.0f} | {100*r['accuracy']['map50']:.3f} / {100*r['accuracy']['map50_95']:.3f} |")
    lines += ['', f"FP16/FP32 throughput ratio **{comparison['predict_speedup']:.3f}×**: FP16 chậm hơn trong lần đo này, không có bằng chứng tăng tốc. Peak allocated giảm **{-comparison['torch_peak_allocated_change_mib']:.2f} MiB**; mAP50 đổi **{comparison['map50_change_pp']:+.5f} điểm phần trăm**, mAP50–95 **{comparison['map50_95_change_pp']:+.5f} điểm phần trăm**. Đây là sai khác số học/thực nghiệm nhỏ trên dev-val, không kết luận FP16 tăng accuracy hoặc tốt hơn khi triển khai.", '',
        '**Protocol:** RTX5060 Laptop, cùng checkpoint YOLOv8n D5-640 và cùng dataset/labels hash của E02; 90 ảnh validation session 24/10. Mỗi precision chạy trong process riêng, thứ tự FP32 rồi FP16, 10 warmup + 3 lượt × 90 ảnh = 270 timing samples. Batch 1, `rect=False`, square 640, TF32 tắt; hook xác nhận cả input và weights thực sự CUDA FP32/FP16. Synchronized wall latency gồm preprocessing/inference/NMS/result của `predict()`, ảnh đã decode trong RAM; không gồm disk/video/control. Hook kiểm tra dtype cũng nằm trong đường timing.', '',
        'Timing dùng conf=0,25; accuracy dùng conf=0,001 để tính AP, NMS IoU=0,7, max_det=300. P/R per class trong JSON là operating point best-F1 của validator, chưa frozen deployment threshold. Hai precision dùng cùng protocol mới; không đối chiếu trực tiếp accuracy này với E02 vốn khác batch/rect. Dataset gốc/checkpoint giữ nguyên; validator chỉ tạo cache trong bản sao private.', '',
        'Đây là native PyTorch, chưa TensorRT; model đơn lẻ, chưa combined workload RTX4050, re-ID hoặc live loop. NVML whole-device sampled peak FP32/FP16 là %.2f/%.2f MiB, có thể gồm process khác và bỏ sót spike; không đồng nhất với allocator. Nguồn AC/battery chưa xác nhận; thứ tự/thermal chưa kiểm soát, không suy ra ưu thế GPU hoặc precision nói chung. [Raw metrics/provenance](../week-06/d5_precision_2026-11-05.json), [cách chạy](../week-06/README.md). F18 có bằng chứng laptop bước đầu; chưa hoàn tất toàn bộ optimization acceptance.' % (rows['32']['nvml_device_used_peak_mib'], rows['16']['nvml_device_used_peak_mib']), '',
        '### Đoạn đề xuất ghép Chương 5', '',
        f"Trên RTX5060 Laptop, chúng tôi so sánh native PyTorch FP32 và FP16 bằng cùng checkpoint D5-640, cùng 90 ảnh/nhãn development và batch 1. Qua 270 mẫu timing mỗi precision, FP32/FP16 đạt {rows['32']['latency']['fps']:.2f}/{rows['16']['latency']['fps']:.2f} FPS; peak allocated của PyTorch là {rows['32']['torch_peak_allocated_mib']:.2f}/{rows['16']['torch_peak_allocated_mib']:.2f} MiB. mAP50 tương ứng {100*rows['32']['accuracy']['map50']:.3f}%/{100*rows['16']['accuracy']['map50']:.3f}%. FP16 giảm bộ nhớ nhưng chưa tăng tốc trong lần đo, nên chưa đổi precision triển khai. Dữ liệu development cùng session đã dùng chọn model; kết quả chưa chứng minh independent accuracy, TensorRT/Nano hoặc ngân sách toàn pipeline trên RTX4050 (F18, N05).", '',
        '## Trạng thái mới cần ghép Chương 7 và phần rủi ro', '',
        '| Mục | Trạng thái ngày 05/11 | Việc còn lại / owner |',
        '| :-- | :-- | :-- |',
        '| Camera JetBot | DQK báo hỏng socket FPC; không có video; chưa xác nhận sửa xong (N01/N04) | DQK sửa/kiểm tra; HNHL dùng đúng calibration theo session khi nhận data |',
        '| Tracking và re-ID | Code có; ID-switch/min, re-lock accuracy, rank-1 vẫn chưa đo hợp lệ | DQK thu D3; HNHL review IDs/timestamps, evaluate; gallery/query ≥5 người |',
        '| D5 | Có dev-val và F18; footwear/bag/wire vẫn chưa đạt full gate, không có session độc lập | Thu session độc lập, QA labels/floor; không train tiếp để hợp thức hóa dev score |',
        '| F7 / F11 | Chưa có raw latency CSV / sweep pose+world truth | DQK/HNHL phối hợp khi camera hoạt động; không dùng quantiles hoặc F15 endpoints để dựng thay |',
        '| F9 / F18 | Có workload RTX5060 và baseline single-model RTX4050; mới có F18 native CUDA D5 | Combined RTX4050, paired independent accuracy và các model còn lại vẫn chờ |',
        '| G2 / Stage A-B | G2 chưa đạt; không làm edge mới trước giữa kỳ theo plan đã merge | Dùng F20/F21 đã có của DQK, không claim on-robot obstacle layer hoặc Edge safety PASS |',
        '| PR #98 / #99 | #98 merge; #99 request changes, chưa merge ở snapshot N06/N09 | Không lấy review/code merge làm T2; runner pursuit mới chưa là nghiệm thu của HNHL |', '',
        'Camera hỏng làm chặn ghi D3/D5 và các thử nghiệm video robot, không chặn viết báo cáo, model inference, replay/simulation hoặc ESP32. Sau sửa camera, DQK kiểm tra frame và đo lại self-pose/height; nếu thay module phải hiệu chuẩn fisheye mới. Các frame D1/D2/D5 cũ tiếp tục gắn calibration/module cũ; không áp calibration mới ngược cho dữ liệu cũ.', '',
        '## Kế hoạch chốt có điều kiện', '',
        '- Camera hoạt động lại trước 07/11: chuẩn bị buổi 09/11; nếu chỉ kịp 13/11 thì 16/11 là buổi robot đầu tiên theo contingency của plan. Đây là kế hoạch, chưa ghi nhận các buổi đã chạy.',
        '- Nếu 16/11 vẫn thiếu camera/data/≥5 identities/reviewed boxes: giữ null/chưa đo cho các chỉ tiêu đó; pursuit/HOLD chỉ trình bày simulation/replay và ghi rõ. Không hạ ngưỡng hoặc dùng D2 runtime thay D3.',
        '- 16/11 chốt hình và thí nghiệm; 18/11 KR ghép full draft; 20/11 freeze PR, 21/11 nhóm kiểm tra tag; 23/11 nộp. F18 đưa vào ngân sách Chương 5 chung 3,5 trang bằng cách rút gọn cùng KR/DQK.', '',
        'Đầu việc HNHL khả thi hiện đã có: bản thảo phương pháp/kết quả/giới hạn, evidence registry, F9/F10/F13/F18, dòng Chương 7, appendix và D3 handoff. [Checklist tiếp tục](update-checklist.md) xác định dữ liệu còn thiếu. Không có motor commands hoặc T2 mới trong lần bổ sung này.', '']
    (OUT/'update-2026-11-05.md').write_text('\n'.join(lines), encoding='utf-8')


def write_current_chapter(m):
    """One current contribution for the editor; the reviewed Word stays frozen."""
    old = collect()[2]
    d, face, rows = old['distance'], old['face'], m['f18']['results']
    lines = ['# Chương 5 — Phần HNHL cập nhật 05/11/2026', '',
        'Bản thảo Markdown hiện hành để KR ghép; Word 01/11 là snapshot lịch sử. Chương 5 chung có ngân sách 3,5 trang, gồm thêm phần cửa của KR và deployment của DQK; editor chọn hình/rút gọn khi dàn trang. Nguồn E01–E20: [evidence gốc](evidence.md), [bổ sung 03/11](update-2026-11-03.md); N01–N11: [bổ sung 05/11](update-2026-11-05.md).', '',
        '## Vật cản, khoảng cách và bản đồ', '',
        'YOLO phát hiện vật cản trên ảnh đã undistort; ray tại contact sàn được chiếu bằng chiều cao camera, pitch và roll theo session. Tape truth là forward từ điểm dưới lens, khác planar range dùng cho repulsion. Sàn bóng có phản chiếu nên bbox bottom không mặc định là contact; bbox cắt mép hoặc contact không rõ bị từ chối. Occupancy grid chỉ nhận FREE từ footprint/seen-floor đã xác nhận; UNKNOWN chặn đường/LOS. Vantage cần reachable, clearance, LOS và cửa có vị trí world đo được.', '',
        f"Trên tập ghế glossy, {d['ids_with_distance']}/{d['ids']} vị trí có estimate, median/p90 relative error {d['median_pct']:.2f}%/{d['p90_pct']:.2f}%; ID21 thiếu do cắt mép. P90 tổng chưa đạt 20%, số ID chưa đủ ≥20; chưa có sweep pose/world truth để nghiệm thu map hoặc dựng F11 thật. [F10](figures/F10_distance.png), E01.", '',
        'D5 có 397 ảnh, split 307 train/90 dev-val, cùng session glossy 24/10 và đã dùng chọn model/input size. YOLOv8n-640 là development candidate; footwear/bag còn thiếu recall, wire recall 0% ở operating point dev và chưa đo empty-floor alarms. 12 wire masks là annotation pilot. Chưa independent T1, distance hoặc collision T2; giữ nguyên target P≥80%/R≥90% cho legs/footwear/backpacks/bags, wire R≥80% và ≤1 alarm/20 empty-floor frames (E02).', '',
        '## Face, re-ID và tracking', '',
        f"Face whitelist dùng SCRFD/MobileFaceNet buffalo_s, embedding 512D chuẩn hóa và max cosine với reference. Pilot D2 có {face['frames']} face frames/{face['entries']} entries/{face['identities']} người; tại threshold {face['threshold']}, TAR {100*face['tar']:.2f}%, FAR {100*face['far']:.2f}%. Chưa đạt TAR95% tại FAR1%; nhãn tự động và queries tương quan cần review. [F13](figures/F13_face_roc.png), E03.", '',
        'OSNet-AIN x1.0 và x0.25 đã chạy, nhưng 23 body crops chưa tạo được gallery/query hợp lệ: thiếu gallery ở 2/3 người. Rank-1/CMC và model thắng vẫn chưa có; gate ≥5 identities/rank-1≥85% giữ nguyên. ByteTrack nối detection theo chuyển động/IoU và confidence; appearance lock/re-lock yêu cầu đúng architecture/weights hash, cosine/margin và hai frame xác nhận. Track ID không phải identity; mất dấu/mơ hồ không xuất target. Replay 822 frame D2 chỉ chứng minh runtime vì timestamp xấp xỉ và chưa có body-ID truth; ≤1 switch/phút và re-lock accuracy trên D3 chưa đo (E03/E04).', '',
        '## Ngân sách GPU và lựa chọn precision', '',
        'Profiler nạp cùng detector, OSNet, pose, face và cửa, pad body/face khi thiếu người; chưa phải hai luồng camera thật. DINO FP16, các Torch model khác FP32; bộ nhớ NVML lấy mẫu gồm cả ORT/driver/process khác. [F9](figures/F9_gpu.png), E05–E07.', '',
        '| RTX5060 workload | FPS | p95 ms | NVML peak GiB |', '| :-- | --: | --: | --: |']
    for row in old['gpu']:
        lines.append(f"| {row['name']} | {row['fps']:.2f} | {row['p95_ms']:.2f} | {row['peak_gib']:.3f} |")
    lines += ['', f"Hai mode mỗi-frame chưa đạt 15 FPS; scheduled door đạt {old['gpu'][2]['door_hz']:.2f} Hz khi yêu cầu 5 Hz. Kết quả RTX5060 chưa thay combined workload RTX4050; baseline từng model hai GPU khác power limits đã được tách riêng trong addendum 03/11. Giới hạn memory là 5,5 GB decimal, không phải 5,5 GiB.", '',
        '![F18](figures/F18_d5_precision.png)', '',
        f"F18 so native PyTorch CUDA FP32/FP16 bằng cùng checkpoint D5-640 và 90 ảnh/nhãn dev-val, 640 square, batch 1; mỗi precision process riêng, 10 warmup/270 timing samples. FPS {rows['32']['latency']['fps']:.2f}/{rows['16']['latency']['fps']:.2f}, p95 {rows['32']['latency']['p95_ms']:.2f}/{rows['16']['latency']['p95_ms']:.2f} ms; Torch peak allocated {rows['32']['torch_peak_allocated_mib']:.2f}/{rows['16']['torch_peak_allocated_mib']:.2f} MiB. mAP50 {100*rows['32']['accuracy']['map50']:.3f}%/{100*rows['16']['accuracy']['map50']:.3f}%. FP16 giảm allocator nhưng chưa tăng tốc, nên chưa đổi precision triển khai. Synchronized predict timing gồm preprocess/NMS và hook kiểm tra dtype, loại disk/video/control; P/R là best-F1 dev operating point. Thứ tự/thermal/nguồn AC chưa kiểm soát; không kết luận FP16 tốt hơn nói chung hoặc thay TensorRT/independent accuracy (N05).", '',
        '## Triển khai và giới hạn thực nghiệm', '',
        'D5 custom export ONNX opset11: 90/90 ảnh cùng bbox count, 294 reference boxes ghép đủ IoU≥0,9 giữa PyTorch CUDA FP32 và ORT CPU; đây là conversion parity, chưa TensorRT accuracy (E08). DQK bổ sung F20/F21 từ bằng chứng Nano đã có; G2/Stage A chưa đạt và không làm edge mới trước giữa kỳ theo plan sau PR #98. KR/DQK bổ sung XFeat/DINOv2 và F12, không dùng timing để suy ra accuracy cửa.', '',
        'Ngày 05/11 DQK báo camera JetBot hỏng; ghi D3/D5 mới và các phép đo video robot bị chặn. Sau sửa cần đo lại pose/height; thay module phải hiệu chuẩn fisheye mới và giữ đúng calibration cho từng session cũ/mới. F7 raw latency, F11 map truth, F14 gallery và T2 còn chờ. Nếu không đủ evidence trước 16/11, ghi chưa đo và dùng simulation/replay có nhãn nguồn; không hạ tiêu chí. Full draft nhóm 18/11, nộp 23/11. PR #99 chưa merge tại snapshot này, không phải bằng chứng pursuit đạt nghiệm thu.', '',
        '[Dòng Chương 7](chapter-07-rows.md), [appendix code](code-appendix.md), [checklist dữ liệu và bàn giao](update-checklist.md).', '']
    (OUT/'chapter-05-current.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    metrics = collect_followup()
    (OUT/'update-2026-11-05.json').write_text(json.dumps(metrics, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    plot_f18(metrics)
    write_markdown(metrics)
    write_current_chapter(metrics)
    print('Built 05/11 addendum and F18 from saved evidence; no inference')


if __name__ == '__main__':
    main()
