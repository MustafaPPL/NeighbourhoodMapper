from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from build_weighted_priority_map import build_parks_and_gardens_legend_handle
from project_paths import OUTPUT_DIR


ROOT = Path(__file__).resolve().parent
OUTPUT_PNG = OUTPUT_DIR / "weighted_map_legend.png"


def main() -> None:
    handles = [
        build_parks_and_gardens_legend_handle(),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="none",
            markeredgecolor="#2B6F8A",
            markeredgewidth=0.8,
            markersize=7,
            label="Library",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="#5C677D",
            markeredgecolor="white",
            markeredgewidth=0.5,
            markersize=8,
            label="Civic centre",
        ),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#D81B60", markeredgecolor="white", markeredgewidth=0.4, markersize=7, label="GP practice"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#1F77B4", markeredgecolor="white", markeredgewidth=0.4, markersize=7, label="Community pharmacy"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#2CA02C", markeredgecolor="white", markeredgewidth=0.4, markersize=7, label="Family hub"),
        Line2D([0], [0], marker="^", color="none", markerfacecolor="#243B53", markeredgecolor="white", markeredgewidth=0.5, markersize=8, label="Acute Trust"),
        Line2D([0], [0], marker="D", color="none", markerfacecolor="#B7791F", markeredgecolor="white", markeredgewidth=0.5, markersize=7.5, label="Specialist Trust"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="#6B46C1", markeredgecolor="white", markeredgewidth=0.5, markersize=7.5, label="Mental Health Trust"),
    ]

    fig, ax = plt.subplots(figsize=(4.2, 3.3), dpi=220)
    ax.axis("off")
    legend = ax.legend(
        handles=handles,
        loc="center",
        frameon=False,
        fontsize=10,
        handlelength=0.8,
        handletextpad=0.6,
        borderaxespad=0.0,
    )
    for text in legend.get_texts():
        text.set_fontstyle("italic")

    OUTPUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PNG, dpi=220, bbox_inches="tight", transparent=True, pad_inches=0.05)
    plt.close(fig)
    print(f"Created: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
