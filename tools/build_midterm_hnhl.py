"""Build HNHL mid-term figures and an evidence snapshot from existing reports.

No inference, raw images or new accuracy claims. Missing experiments stay null.
Run from the repo root; Word export is a separate optional document-runtime step.
"""
import hashlib
import json
from pathlib import Path
import re

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'reports/HuynhNguyenHoaiLoc/midterm'
HNHL = 'reports/HuynhNguyenHoaiLoc/'
SOURCES = {
    'E01': HNHL + 'week-02/issue-43/chairs_semantic.json',
    'E02': HNHL + 'week-04/d5_corrected_validation.json',
    'E03': HNHL + 'week-04/d2_pilot.json',
    'E04': HNHL + 'week-05/d2_tracking_runtime.json',
    'E05': HNHL + 'week-05/pipeline_both.json',
    'E06': HNHL + 'week-05/pipeline_xfeat.json',
    'E07': HNHL + 'week-05/pipeline_both_5hz.json',
    'E08': HNHL + 'week-04/d5_onnx_real_parity.json',
    'E09': 'reports/DoanQuocKien/week-04/edge_parity/parity_results.json',
    'E10': HNHL + 'week-01/gpu_baseline.json',
    'E11': HNHL + 'week-05/pytest_cpu.log',
    'E12': HNHL + 'week-05/pytest_gpu.log',
}


def evidence_bytes(path):
    """Canonical text bytes so Git CRLF conversion does not invalidate evidence."""
    return Path(path).read_bytes().replace(b'\r\n', b'\n')


def collect():
    raw, registry = {}, {}
    for key, relative in SOURCES.items():
        path = ROOT / relative
        data = evidence_bytes(path)
        raw[key] = json.loads(data) if path.suffix == '.json' else data.decode('utf-8')
        registry[key] = dict(path=relative, sha256=hashlib.sha256(data).hexdigest())
    chairs = raw['E01']
    rows = [dict(clip=clip, obstacle_id=identity, **item)
            for clip, group in chairs['clips'].items() for identity, item in group.items()]
    valid = [r for r in rows if r['median_forward_m'] is not None]
    held = [r for r in valid if r['clip'] == 'chairs_c']
    if len(rows) != chairs['obstacle_ids'] or len(valid) != chairs['distance_ids']:
        raise ValueError('chair coverage differs from saved report')
    if not valid or not held:
        raise ValueError('chair evidence has no estimates/held-out subset')
    metrics = dict(
        snapshot_date='2026-11-01', evidence=registry,
        evidence_hash_policy='SHA256 after CRLF to LF; all other source bytes preserved',
        distance=dict(ids=len(rows), ids_with_distance=len(valid), missing_ids=[r['obstacle_id'] for r in rows if r not in valid],
                      median_pct=100 * chairs['distance_median_relative_error'],
                      p90_pct=100 * chairs['distance_p90_relative_error'],
                      held_ids=len(held), held_median_pct=100 * float(np.median([r['median_relative_error'] for r in held])),
                      held_p90_pct=100 * float(np.percentile([r['median_relative_error'] for r in held], 90)),
                      formal_t1_passed=False),
        d5=dict(train_images=raw['E02']['provenance']['split_counts']['train'],
                val_images=raw['E02']['provenance']['split_counts']['val'],
                sessions=raw['E02']['provenance']['capture_sessions'],
                models={size: {k: model[k] for k in ('map50', 'map50_95', 'classes')}
                        for size, model in raw['E02']['models'].items()}, t1_passed=False),
        face=dict(frames=raw['E03']['walker_frames'], entries=raw['E03']['entries'], identities=raw['E03']['identities'],
                  **raw['E03']['face']['fixed_config_threshold'], t1_passed=False),
        reid=dict(body_crops=raw['E03']['person_crops'], models=raw['E03']['models'],
                  rank1=None, recommended_model=None, t1_passed=False),
        tracking=dict(frames=raw['E04']['frames_total'], id_switches=None, t1_passed=False),
        gpu=[dict(name=name, fps=raw[key]['fps'], p95_ms=raw[key]['p95_ms'],
                  peak_gib=raw[key]['device_used_peak_gib'], door_hz=raw[key].get('actual_door_hz'),
                  evidence=key, target_rtx4050_verified=False)
             for key, name in [('E05', 'All every frame'), ('E06', 'XFeat every frame'), ('E07', 'All scheduled door')]],
        single_models=[{k: m[k] for k in ('model', 'fps', 'p95_latency_ms', 'peak_allocated_mib', 'peak_reserved_mib')}
                       for m in raw['E10']['models'] if m.get('status') == 'measured'],
        tests=dict(cpu_passed=int(re.search(r'(\d+) passed', raw['E11']).group(1)),
                   gpu_passed=int(re.search(r'(\d+) passed', raw['E12']).group(1))),
        pending=['F7 real robot CDF samples', 'F11 measured map/vantage', 'F14 valid re-ID gallery and D3',
                 'F18 paired FP32/FP16 accuracy', 'RTX4050 budget', 'real-robot T2', 'Wire target'],
    )
    return raw, rows, metrics


def figures(raw, rows, metrics):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.titlesize': 10,
                         'axes.labelsize': 9, 'legend.fontsize': 8})
    folder = OUT / 'figures'
    folder.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 2.75), layout='constrained', gridspec_kw={'width_ratios': [1.05, 1]})
    ax, bars = axes
    for clip, symbol, color, label in [('chairs_a', 'o', '#4e647a', 'a / b development'),
                                      ('chairs_b', 'o', '#4e647a', None), ('chairs_c', 'D', '#ae6329', 'c held out')]:
        group = [r for r in rows if r['clip'] == clip and r['median_forward_m'] is not None]
        ax.scatter([r['tape_forward_m'] for r in group], [r['median_forward_m'] for r in group], marker=symbol, c=color, label=label, s=28)
    ax.plot([.2, 2.05], [.2, 2.05], '--', c='.65', linewidth=1)
    missing = [r for r in rows if r['median_forward_m'] is None]
    for r in missing:
        ax.plot(r['tape_forward_m'], .03, 'x', color='#a12f2f', transform=ax.get_xaxis_transform())
    ax.annotate('ID21: no distance', (.32, .03), xycoords=ax.get_xaxis_transform(), xytext=(.45, .16), textcoords='axes fraction', fontsize=8,
                arrowprops=dict(arrowstyle='-', color='#a12f2f'))
    ax.set(xlim=(.2, 2.05), ylim=(.2, 2.05), xlabel='Tape forward Z (m)', ylabel='Median estimated Z (m)', title='F10  Chair distance on glossy floor')
    ax.legend(loc='upper left', frameon=False)
    d = metrics['distance']
    x = np.arange(2)
    for offset, values, color, label in [(-.17, [d['median_pct'], d['held_median_pct']], '#4e647a', 'Median error'),
                                         (.17, [d['p90_pct'], d['held_p90_pct']], '#ae6329', 'p90 error')]:
        rects = bars.bar(x + offset, values, width=.32, color=color, label=label)
        bars.bar_label(rects, fmt='%.2f', fontsize=8, padding=2)
    bars.set(xticks=x, xticklabels=['8 estimated IDs', '3 held-out IDs'], ylabel='Absolute relative error (%)', ylim=(0, 31), title='Coverage 8 of 9 IDs  No full T1 pass')
    bars.legend(loc='upper left', frameon=False)
    for a in axes:
        a.grid(alpha=.18)
        a.set_axisbelow(True)
    fig.savefig(folder / 'F10_distance.png', dpi=240)
    plt.close(fig)
    face = raw['E03']['face']
    point = face['fixed_config_threshold']
    fig, ax = plt.subplots(figsize=(6.5, 2.7), layout='constrained')
    ax.plot([r['far'] * 100 for r in face['descriptive_roc']], [r['tar'] * 100 for r in face['descriptive_roc']], color='#4e647a')
    ax.scatter(point['far'] * 100, point['tar'] * 100, c='#a12f2f', zorder=3)
    ax.annotate(f"cosine {point['threshold']:.2f}\nTAR {point['tar']:.2%} / FAR {point['far']:.2%}",
                (point['far'] * 100, point['tar'] * 100), xytext=(55, 42), arrowprops=dict(arrowstyle='-', color='#a12f2f'))
    ax.plot([0, 100], [0, 100], '--', c='.7', linewidth=1)
    ax.set(xlim=(-1, 101), ylim=(-1, 102), xlabel='False accept rate (%)', ylabel='True accept rate (%)',
           title='F13  D2 pilot  3 people  Automatic labels  Not T1 acceptance')
    ax.grid(alpha=.18)
    fig.savefig(folder / 'F13_face_roc.png', dpi=240)
    plt.close(fig)
    gpu = metrics['gpu']
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 2.7), layout='constrained')
    labels = ['All\neach frame', 'XFeat\neach frame', 'All\ndoor scheduled']
    for ax, field, title, limit in zip(axes, ['fps', 'peak_gib'], ['F9  RTX5060 workload FPS', 'Sampled device-used (GiB)'], [15, 5.5e9 / 2**30]):
        rects = ax.bar(range(3), [r[field] for r in gpu], color=['#4e647a', '#728d81', '#ae6329'])
        ax.bar_label(rects, fmt='%.2f', padding=2, fontsize=9)
        ax.axhline(limit, color='#a12f2f', linestyle='--', label='15 FPS limit' if field == 'fps' else '5.5 GB limit')
        ax.set(xticks=range(3), xticklabels=labels, title=title, ylim=(0, max(limit, *(r[field] for r in gpu)) * 1.22))
        ax.grid(axis='y', alpha=.18)
        ax.set_axisbelow(True)
        ax.legend(frameon=False, loc='upper left')
    fig.savefig(folder / 'F9_gpu.png', dpi=240)
    plt.close(fig)


def write_registry(metrics):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'metrics.json').write_text(json.dumps(metrics, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    lines = ['# Danh mục bằng chứng HNHL', '', 'Snapshot biên soạn 01/11/2026; không chạy lại model. Số đo giữ phạm vi và điều kiện gốc. SHA256 dùng source bytes sau chuẩn hóa CRLF thành LF; các byte khác giữ nguyên, nên checkout Windows/Linux cho cùng hash.', '',
             '| Mã | Nguồn trong repo | SHA256 |', '| :-- | :-- | :-- |']
    for key, source in metrics['evidence'].items():
        relative = '../../../' + source['path']
        lines.append(f"| {key} | [{Path(source['path']).name}]({relative}) | `{source['sha256']}` |")
    lines += ['', 'Không đổi pilot/dev-val thành T1. F10 dùng 8 ID có estimate và báo ID21 thiếu; điểm scatter là median khoảng cách theo ID, thống kê error giữ cách tổng hợp của report gốc.',
              'F9 single-model W1 dùng PyTorch allocator; F9 combined W5 dùng NVML toàn thiết bị. Không ghép hai số memory thành cùng loại phép đo.',
              'metrics.json ghi null cho rank-1/ID switches chưa đo. Số nhãn tự động D2 chưa được coi là ground truth đã nghiệm thu.', '']
    (OUT / 'evidence.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    raw, rows, metrics = collect()
    figures(raw, rows, metrics)
    write_registry(metrics)
    print('Built F9/F10/F13 and evidence snapshot:', OUT)


if __name__ == '__main__':
    main()
