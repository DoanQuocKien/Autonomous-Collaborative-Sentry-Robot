"""Draw F13 from aggregate D2 pilot metrics; no face images or vectors are read."""
import argparse
import json
from pathlib import Path


def run(metrics, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    report = json.loads(Path(metrics).read_text(encoding='utf-8'))
    if report['status'] != 'REAL_D2_SAME_SESSION_PILOT_NOT_T1':
        raise ValueError('expected real D2 pilot metrics')
    face = report['face']
    curve = face['descriptive_roc']
    point = face['fixed_config_threshold']
    fig, ax = plt.subplots(figsize=(7.5, 5.5), layout='constrained')
    ax.plot([p['far'] for p in curve], [p['tar'] for p in curve], label='Supplied face embeddings')
    ax.scatter([point['far']], [point['tar']], color='#bd3030', zorder=3,
               label=f"Config cosine {point['threshold']:.2f}: FAR {point['far']:.1%}, TAR {point['tar']:.1%}")
    ax.plot([0, 1], [0, 1], '--', color='0.7', linewidth=1)
    ax.set(xlabel='False accept rate (query level)', ylabel='True accept rate',
           xlim=(-.02, 1.02), ylim=(-.02, 1.02),
           title='F13: D2 cafe face verification pilot\n3 people, 1 session; automatic labels, NOT T1 acceptance')
    ax.grid(alpha=.2)
    ax.legend(loc='lower right', fontsize=9)
    fig.supxlabel(f"Leave one member out; first-entry enrollment; {face['genuine_queries']} genuine / "
                  f"{face['impostor_queries']} impostor queries. Correlated frames; threshold unchanged.", fontsize=8)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--metrics', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    run(args.metrics, args.out)


if __name__ == '__main__':
    main()
