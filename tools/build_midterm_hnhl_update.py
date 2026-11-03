"""Compile the 2026-11-03 HNHL audit/addendum from recorded evidence, offline.

Does not rerun inference or change the reviewed 01/11 Word snapshot. GitHub
metadata is an explicit saved snapshot, not a claim about future PR state.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics

from tools.build_midterm_hnhl import ROOT, OUT, SOURCES, evidence_bytes


EXTRA = {
    'E13': 'reports/DoanQuocKien/week-01/gpu/gpu_baseline_rtx4050.json',
    'E14': 'reports/DoanQuocKien/week-01/link_test_2026-10-04.txt',
    'E15': 'reports/DoanQuocKien/week-01/estop_deadman_2026-10-06.txt',
    'E16': 'reports/DoanQuocKien/week-04/edge_deploy/live_esp32_bench.json',
    'E17': 'reports/DoanQuocKien/week-04/edge_deploy/README.md',
    'E18': 'reports/DoanQuocKien/week-05/f15/README.md',
    'E19': 'reports/DoanQuocKien/week-05/f15/tape_offsets_1030.json',
    'E20': 'reports/HuynhNguyenHoaiLoc/midterm/github-2026-11-03.json',
}


def collect_update():
    raw, registry = {}, {}
    for key, relative in {**SOURCES, **EXTRA}.items():
        data = evidence_bytes(ROOT / relative)
        raw[key] = json.loads(data) if relative.endswith('.json') else data.decode('utf-8-sig')
        registry[key] = dict(path=relative, sha256=hashlib.sha256(data).hexdigest())
    devices = []
    for key in ('E13', 'E10'):
        report = raw[key]
        devices.append(dict(
            evidence=key, gpu=report['environment']['gpu']['name'],
            configuration=report['configuration'],
            runtime=report['environment']['nvidia_smi']['rows'],
            models=[{k: item[k] for k in ('model', 'weights_sha256', 'fps', 'p95_latency_ms',
                                          'peak_allocated_mib', 'peak_reserved_mib')}
                    for item in report['models'] if item.get('status') == 'measured']))
    # Select the real-camera block, never a synthetic-video run earlier in E14.
    camera = raw['E14'].split('# Real camera, 60 s:', 1)[1].split('## O.', 1)[0]
    video = re.search(r'video: (\d+) frames in ([\d.]+) s -> ([\d.]+) fps; missing (\d+) of (\d+)', camera)
    latency = re.search(r'one-way latency ms[^\n]*p50 (\d+)\s+p95 (\d+)\s+max (\d+)', camera)
    watchdog = re.search(r'watchdog: last packet -> motors stop, per cycle \(ms\): ([\d, ]+)', raw['E14'])
    if not all((video, latency, watchdog)):
        raise ValueError('real-camera/watchdog source format changed; review extraction')
    cuts = [int(x) for x in re.findall(r'motors CUT in (\d+) ms', raw['E15'].split('## Test 2:', 1)[0])]
    if not cuts:
        raise ValueError('no valid first-cycle e-stop records')
    bench = raw['E16']
    metrics = dict(
        snapshot_date='2026-11-03', evidence=registry, single_model_devices=devices,
        evidence_hash_policy='SHA256 after CRLF to LF; all other source bytes preserved',
        d5_640=raw['E02']['models']['640']['classes'], github=raw['E20'],
        link=dict(frames=int(video[1]), seconds=float(video[2]), fps=float(video[3]),
                  sequence_missing=int(video[4]), sequence_expected=int(video[5]),
                  p50_ms=int(latency[1]), p95_ms=int(latency[2]), max_ms=int(latency[3]),
                  latency_target_ms=50, latency_target_met=int(latency[2]) < 50,
                  raw_frame_latency_samples_available=False,
                  watchdog_ms=[int(x.strip()) for x in watchdog[1].split(',')],
                  watchdog_scope='robot_udp dry-run log response; not mechanical stopping time',
                  estop_first_cycle_cut_ms=cuts,
                  estop_scope='real robot wheels raised; daemon-reported cut duration'),
        jetson=dict(frames=bench['frames'], seconds=bench['seconds'], fps=bench['fps'],
                    e2e_p95_ms=bench['stage_ms']['e2e']['p95'], door_runs=bench['door_runs'],
                    door_hz=bench['door_runs']/bench['seconds'],
                    esp_frames=bench['door_live']['esp_frames'], esp_fps=bench['door_live']['esp_fps'],
                    wheels_moving=False, identity_accuracy_measured=False),
        acceptance=dict(w5_code_merged=True, w5_fully_accepted=False,
                        d3_id_switches_per_minute=None, target_relock_accuracy=None,
                        rtx4050_combined_budget_accepted=False,
                        osnet_fp16_rank1=None, real_map_vantage_accepted=False),
    )
    return metrics


def plot_single_models(metrics, folder):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), layout='constrained')
    labels, rows = [], []
    for device, short in zip(metrics['single_model_devices'], ('4050', '5060')):
        for model in device['models']:
            labels.append(short + '\n' + model['model'].replace('.pt', ''))
            rows.append(model)
    for ax, field, title in zip(axes, ('fps', 'p95_latency_ms'), ('Single-model FPS', 'p95 predict latency (ms)')):
        bars = ax.bar(range(4), [r[field] for r in rows], color=['#4e647a']*2+['#ae6329']*2)
        ax.bar_label(bars, fmt='%.1f', padding=3, fontsize=8)
        ax.set_xticks(range(4), labels, fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.set_ylim(0, max(r[field] for r in rows)*1.22)
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle('F9 supplement  Separate recorded runs  FP32 640 batch 1\n80 W vs 20 W recorded limits; not a controlled GPU comparison', fontsize=9)
    folder.mkdir(parents=True, exist_ok=True)
    fig.savefig(folder/'F9_single_models.png', dpi=240)
    plt.close(fig)


def write_update(metrics, out):
    out.mkdir(parents=True, exist_ok=True)
    (out/'update-2026-11-03.json').write_text(json.dumps(metrics, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    lines = ['# Bổ sung giữa kỳ HNHL ngày 03/11/2026', '',
        'Bản bổ sung cho snapshot Word/Markdown 01/11; không sửa số đo hoặc tự ghi nhận T1/T2 mới. Editor đọc cả hai bản khi ghép Chương 3/5/7. Các bảng dưới được tạo từ evidence, không chạy lại model.', '',
        '## GPU từng model trên hai laptop', '',
        '![F9 single models](figures/F9_single_models.png)', '',
        '| GPU / model | FPS | p95 ms | Peak allocated / reserved MiB | Nguồn |',
        '| :-- | --: | --: | --: | :-- |']
    for device in metrics['single_model_devices']:
        name = device['gpu'].replace('NVIDIA GeForce ', '')
        for m in device['models']:
            lines.append(f"| {name} / {m['model']} | {m['fps']:.2f} | {m['p95_latency_ms']:.2f} | {m['peak_allocated_mib']:.2f} / {m['peak_reserved_mib']:.0f} | {device['evidence']} |")
    lines += ['', '640, batch 1, FP32, ảnh BGR tổng hợp cùng seed 532, 10 warmup/100 iterations; FPS gồm predict preprocessing/postprocessing. Enforced power limit ghi nhận RTX4050 80 W và RTX5060 20 W; nguồn AC/battery chưa xác nhận, drivers và clock khác nhau. Không suy ra GPU này nhanh hơn GPU kia theo kiến trúc, không lấy single-model FPS thay ngân sách toàn pipeline. Memory bảng này là PyTorch allocator; F9 workload W5 dùng sampled NVML toàn thiết bị.', '',
        '## D5 precision và recall phải tách riêng', '',
        'D5-640 là development validation đã dùng chọn checkpoint/input size: 307 train/90 val trong cùng session glossy. Các class không đạt vẫn được giữ nguyên. E02.', '',
        '| Class | Precision % | Recall % | So gate P/R của nhóm class bắt buộc |', '| :-- | --: | --: | :-- |']
    for cls, row in metrics['d5_640'].items():
        if cls in ('leg', 'footwear', 'backpack', 'bag'):
            met = row['recall'] >= .9 and row['precision'] >= .8
            status = ('P/R đạt trên dev-val' if met else 'Chưa đạt') + ' / R≥90%, P≥80%'
        elif cls == 'wire':
            status = 'Chưa đạt R≥80%; gate ≤1 alarm/20 empty frames chưa đo'
        else:
            status = 'Chưa đặt gate P/R tại bảng này'
        lines.append(f"| {cls} | {100*row['precision']:.2f} | {100*row['recall']:.2f} | {status} |")
    lines += ['', 'Backpack recall là 100%; khoảng 91,84% là precision. Footwear và bag đều thiếu cả recall≥90% lẫn precision≥80%; Wire recall 0% dưới 80% và chưa có số false alarms/20 empty-floor frames. Gate lấy từ [Implementation Plan §4.3](../../../docs/Implementation%20Plan.md), bao gồm cả bags. Các class đạt P/R trong dev-val vẫn chưa chứng minh full T1: còn held-out session, distance error và T2 drive-over/collision.', '',
        '## Đường truyền để ghép Chương 3 và Chương 7', '']
    link = metrics['link']
    wd = link['watchdog_ms']
    cuts = link['estop_first_cycle_cut_ms']
    lines += ['| Phép đo | Kết quả và phạm vi | Nguồn |', '| :-- | :-- | :-- |',
        f"| Video camera thật 60 s | {link['frames']} frames / {link['seconds']:.1f}s; {link['fps']:.1f} FPS; seq missing {link['sequence_missing']}/{link['sequence_expected']}; latency p50/p95/max {link['p50_ms']}/{link['p95_ms']}/{link['max_ms']} ms | E14, block Real camera 60 s |",
        f"| Watchdog, 5 chu kỳ | {', '.join(map(str, wd))} ms; median {statistics.median(wd):.0f}, max {max(wd)} ms; robot_udp --dry-run trên robot, đo từ packet cuối tới log zero | E14, block O |",
        f"| Dead-man/e-stop đầu tiên | {min(cuts)}–{max(cuts)} ms theo daemon khi wheels off ground; không phải thời gian dừng cơ học khi robot đang chạy | E15, Test 1 |", '',
        'p95 video 53 ms vượt target <50 ms; ghi chưa đạt tiêu chí latency. Seq gaps bằng 0 trong run này không chứng minh mọi mạng có packet loss 0%. Log chỉ chứa aggregate quantiles, không có raw per-frame latency samples: F7 CDF còn chờ, không nội suy CDF từ ba quantiles. Watchdog đạt giới hạn log-response ≤350 ms trong dry-run; không đánh đồng với HIL đo dừng cơ học. Quy tắc gamepad hiện tại cần lấy từ code/config hiện hành, không dùng câu hướng dẫn arming lịch sử như lệnh vận hành mới.', '',
        '## Jetson và ESP32 để phối hợp mục 5.x của DQK', '']
    jetson = metrics['jetson']
    lines += [f"Run 28/10 trên pin, wheels still: {jetson['frames']:,} frames/{jetson['seconds']:.1f}s, {jetson['fps']:.2f} FPS, capture-to-result p95 {jetson['e2e_p95_ms']:.2f} ms; {jetson['door_runs']:,} door runs (khoảng {jetson['door_hz']:.2f} Hz). Nhưng chỉ {jetson['esp_frames']:,} ESP frames mới, {jetson['esp_fps']:.2f} FPS: nhiều door runs dùng lại frame, không phải 5Hz thông tin độc lập. Đây là compute/runtime benchmark, chưa phải accuracy nhận diện danh tính hoặc driving under load. E16–E17.", '',
        'README của DQK ghi RAM max 2,11 GB, nhiệt độ max 33°C và pin min 11,83 V, lấy từ tegrastats/battery logs; đây là RAM hệ thống Jetson, không phải NVML VRAM laptop. Firmware ESP32 cải thiện lên khoảng 9 FPS sau run này nhưng chưa re-bench cùng workload. Khi editor dùng các số phụ này, giữ link README/raw logs của DQK và điều kiện wheels still. G1 compute evidence không thay Stage A/G2 obstacle/control trials hoặc accuracy D1/D2.', '',
        '## F15 mới và trạng thái tích hợp', '',
        'Dùng [F15 đo điểm cuối của DQK](../../DoanQuocKien/week-05/f15/F15_dead_reckoning.png) và [giải thích nguồn](../../DoanQuocKien/week-05/f15/README.md), đã merge qua PR #94. Chỉ có end poses và tape offsets; không có per-frame poses nên không dựng quỹ đạo giữa chúng. Hai run 3m: open-loop error khoảng 186/158 cm (không/có mốc), closed-loop khoảng 98/14,5 cm. Chưa đủ 5 lượt T2, run tốt còn phụ thuộc vị trí board đo tay; các speed-scale khác cho khoảng 15,5–17,3 cm. Deployment 30/10 là protocol khác, không cộng chung thành 5 lượt 3m. E18–E19.', '',
        'PR #92 HNHL đã merge; PR #93 KR đang có bản sửa sau review, chưa merge tại thời điểm snapshot E20. Kết quả hold/controller/ByteTrack trên nhánh KR là T0/simulation và còn phải review đúng head mới, không dùng làm T2 hoặc D3 accuracy. F15 không thay F11 occupancy/vantage của HNHL.', '',
        '## Nguồn mở rộng E13–E20', '', 'SHA256 chuẩn hóa CRLF thành LF để không đổi khi Git checkout trên Windows/Linux; các source bytes khác giữ nguyên.', '', '| Mã | File | SHA256 |', '| :-- | :-- | :-- |']
    for key in EXTRA:
        e = metrics['evidence'][key]
        lines.append(f"| {key} | [{Path(e['path']).name}](../../../{e['path']}) | `{e['sha256']}` |")
    lines += ['', 'Nguồn E01–E12 và snapshot Word giữ tại [evidence.md](evidence.md). Bản số liệu đầy đủ của phụ lục: [update-2026-11-03.json](update-2026-11-03.json). Chạy lại `python -m tools.build_midterm_hnhl_update` để tạo bảng/hình từ các nguồn đã lưu; không tự fetch GitHub hoặc suy ra data mới.', '']
    (out/'update-2026-11-03.md').write_text('\n'.join(lines), encoding='utf-8')
    plot_single_models(metrics, out/'figures')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    write_update(collect_update(), args.out)
    print('Built 03/11 addendum and F9 single-model figure:', args.out)


if __name__ == '__main__':
    main()
