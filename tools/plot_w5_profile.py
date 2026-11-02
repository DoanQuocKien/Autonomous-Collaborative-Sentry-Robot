"""F9: plot aggregate W5 runtime workload results, without private frames."""
import argparse
import json
from pathlib import Path


def run(root, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    root = Path(root)
    names = ['All / every frame', 'XFeat / every frame', 'All / door requested 5 Hz']
    files = ['pipeline_both.json', 'pipeline_xfeat.json', 'pipeline_both_5hz.json']
    results = [json.loads((root / f).read_text(encoding='utf-8')) for f in files]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.5), layout='constrained')
    for ax, key, title, limit in zip(axes, ['fps', 'device_used_peak_gib'],
                                   ['Workload throughput (FPS)', 'Sampled total device memory (GiB)'], [15, 5500000000 / 2**30]):
        bars = ax.bar(range(3), [r[key] for r in results], color=['#405a80', '#668d81', '#bf8741'])
        ax.axhline(limit, color='#a52f2f', linestyle='--', label='Plan limit 15 FPS' if key == 'fps' else 'Plan limit 5.5 GB = 5.12 GiB')
        ax.set_xticks(range(3), names, rotation=18, ha='right', fontsize=9)
        ax.set_title(title)
        ax.bar_label(bars, fmt='%.2f', padding=3)
        ax.set_ylim(0, max(limit, *(r[key] for r in results)) * 1.22)
        ax.legend(fontsize=9)
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle('F9: Models resident together on RTX 5060 Laptop\n100 iterations; runtime workload, not RTX 4050 / D3 acceptance', fontsize=13)
    frequency = results[2]['actual_door_hz']
    fig.supxlabel('Body/face work padded to >=2 crops; DINO FP16, other torch models FP32.\n'
                  f'Scheduled run achieved {frequency:.2f} door updates/s; NVML includes ORT, driver and other processes.', fontsize=9)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    run(a.root, a.out)


if __name__ == '__main__':
    main()
