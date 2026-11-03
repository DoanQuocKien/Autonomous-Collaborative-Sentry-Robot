"""Generates Figure F16: Complete Phase 1-3 State Machine Diagram.

Source: sentry/app/state_machine.py
Saves: reports/kouun-rokku/week-05/F16_state_machine.png
"""
from pathlib import Path
import matplotlib.patches as patches
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "reports" / "kouun-rokku" / "week-05" / "F16_state_machine.png"


def draw_state_box(ax, x, y, w, h, text, color="#e8f4f8", border="#2b7bba"):
    box = patches.FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        boxstyle="round,pad=0.08,rounding_size=0.15",
        facecolor=color,
        edgecolor=border,
        linewidth=1.8,
        zorder=3,
    )
    ax.add_patch(box)
    ax.text(x, y, text, ha="center", va="center", fontsize=9.5, fontweight="bold", zorder=4)


def draw_phase_group(ax, x, y, w, h, title, fill="#fafafa", border="#999999"):
    box = patches.FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        boxstyle="round,pad=0.15,rounding_size=0.25",
        facecolor=fill,
        edgecolor=border,
        linewidth=1.2,
        linestyle="--",
        zorder=1,
    )
    ax.add_patch(box)
    ax.text(
        x - w / 2 + 0.2,
        y + h / 2 - 0.25,
        title,
        ha="left",
        va="top",
        fontsize=10.5,
        fontweight="bold",
        color="#444444",
        zorder=2,
    )


def draw_arrow(ax, p1, p2, label="", rad=0.0, color="#333333", offset_y=0.15, label_fs=7.5):
    style = f"arc3,rad={rad}"
    ax.annotate(
        "",
        xy=p2,
        xycoords="data",
        xytext=p1,
        textcoords="data",
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=1.4,
            connectionstyle=style,
            mutation_scale=12,
        ),
        zorder=2,
    )
    if label:
        mx = (p1[0] + p2[0]) / 2
        my = (p1[1] + p2[1]) / 2 + offset_y
        ax.text(
            mx,
            my,
            label,
            ha="center",
            va="center",
            fontsize=label_fs,
            fontweight="semibold",
            color=color,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.85),
            zorder=5,
        )


def main():
    fig, ax = plt.subplots(figsize=(13, 7.5), dpi=200)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 8.5)
    ax.axis("off")

    # Phase 1 Group: SETUP
    draw_phase_group(ax, 3.2, 5.8, 5.8, 4.4, "PHASE 1: SETUP & HANDSHAKE", fill="#f4f9f4", border="#4caf50")
    draw_state_box(ax, 1.6, 7.0, 1.8, 0.7, "EXPLORE", color="#e8f5e9", border="#2e7d32")
    draw_state_box(ax, 4.8, 7.0, 2.2, 0.7, "APPROACH_VANTAGE", color="#e8f5e9", border="#2e7d32")
    draw_state_box(ax, 4.8, 4.8, 2.0, 0.7, "WAIT_CAMERA", color="#e8f5e9", border="#2e7d32")
    draw_state_box(ax, 1.6, 4.8, 1.8, 0.7, "RETRACT", color="#e8f5e9", border="#2e7d32")

    # Phase 1 Transitions
    draw_arrow(ax, (2.5, 7.0), (3.7, 7.0), "ENTRANCE_FOUND", rad=0.0)
    draw_arrow(ax, (3.7, 6.75), (2.5, 6.75), "ENTRANCE_LOST", rad=0.0, color="#d32f2f")
    draw_arrow(ax, (4.8, 6.65), (4.8, 5.15), "VANTAGE_REACHED", rad=0.0)
    draw_arrow(ax, (3.8, 4.8), (2.5, 4.8), "ESP32_VERIFIED", rad=0.0)

    # Phase 2 Group: MONITOR
    draw_phase_group(ax, 2.2, 1.8, 3.8, 2.8, "PHASE 2: MONITOR", fill="#eef7fa", border="#0288d1")
    draw_state_box(ax, 2.2, 1.8, 2.2, 0.9, "STANDBY", color="#e1f5fe", border="#0277bd")

    # Transition Phase 1 -> Phase 2
    draw_arrow(ax, (1.6, 4.45), (1.6, 2.25), "STANDBY_REACHED\n(save_map)", rad=0.0)
    draw_arrow(ax, (2.6, 2.25), (4.2, 4.45), "ESP32_LOST", rad=0.15, color="#d32f2f")

    # Phase 3 Group: INTERCEPT
    draw_phase_group(ax, 9.2, 4.3, 6.8, 7.4, "PHASE 3: INTERCEPT", fill="#fff8e1", border="#f57c00")
    draw_state_box(ax, 7.5, 6.2, 2.0, 0.8, "PURSUE", color="#fff3e0", border="#e65100")
    draw_state_box(ax, 10.9, 6.2, 2.0, 0.8, "HOLD", color="#fff3e0", border="#e65100")
    draw_state_box(ax, 7.5, 2.4, 2.0, 0.8, "EVADE", color="#ffebee", border="#c62828")
    draw_state_box(ax, 10.9, 2.4, 2.0, 0.8, "SEARCH", color="#ede7f6", border="#512da8")

    # Transitions Phase 2 -> Phase 3
    draw_arrow(ax, (3.3, 2.1), (6.5, 6.0), "INTRUDER_QUEUED\n(play: intruder_detected)", rad=0.18, color="#e65100")

    # Phase 3 internal transitions
    draw_arrow(ax, (8.5, 6.4), (9.9, 6.4), "TARGET_STATIONARY\n(< 0.1 m/s for > 2.0s)", rad=0.0, color="#2e7d32")
    draw_arrow(ax, (9.9, 6.0), (8.5, 6.0), "TARGET_MOVING\n(> 0.2 m/s, hysteresis)", rad=0.0, color="#1565c0")

    draw_arrow(ax, (7.2, 5.8), (7.2, 2.8), "STRIKE\n(lunge / rapid area growth)", rad=0.0, color="#c62828")
    draw_arrow(ax, (7.8, 2.8), (7.8, 5.8), "EVADE_COMPLETE\n(after 0.4s pulse + cooldown)", rad=0.0)

    draw_arrow(ax, (10.9, 5.8), (10.9, 2.8), "TARGET_EXITED\n(plan coverage tour)", rad=0.0, color="#512da8")
    draw_arrow(ax, (8.5, 5.8), (10.0, 2.7), "TARGET_EXITED", rad=0.1, color="#512da8")

    draw_arrow(ax, (10.0, 2.4), (8.5, 2.4), "STRIKE", rad=0.0, color="#c62828")
    draw_arrow(ax, (9.9, 2.7), (8.4, 5.9), "TARGET_FOUND\n(re-ID match)", rad=0.15, color="#2e7d32")

    # Exit from SEARCH -> back to STANDBY when exhausted
    draw_arrow(ax, (9.9, 2.1), (3.3, 1.5), "SEARCH_EXHAUSTED / TIMEOUT (next target or standby)", rad=0.25, color="#616161")

    plt.title("Autonomous Collaborative Sentry Robot — Phase 1-3 State Machine Architecture",
              fontsize=13, fontweight="bold", pad=12)
    plt.tight_layout()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_PATH)
    plt.close()
    print(f"[PlotF16] Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
