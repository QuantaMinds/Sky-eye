"""Render the 7-dimensional score bar chart as a base64-encoded PNG.

Truth-first (CLAUDE.md Rule 3): a dimension with value=None renders as a
gray "Unavailable" stub, NOT as a zero-width bar. Showing a zero bar for
missing data would silently teach readers that the dimension scored 0.
"""
from __future__ import annotations

import base64
import io
from typing import Sequence

import matplotlib
matplotlib.use("Agg")  # No display backend — required for server-side use.
import matplotlib.pyplot as plt

_BAR_COLOR = "#2563eb"          # blue-600
_UNAVAILABLE_COLOR = "#cbd5e1"  # slate-300
_TEXT_COLOR = "#0f172a"         # slate-900


def render_dimensions_bar(
    dimensions: Sequence[dict],
    *,
    width_in: float = 6.4,
    # 6.4 × 2.0 aspect: at template width=100% (~7.3" content area on
    # Letter) the chart renders ~2.3" tall. Earlier 3.2 height pushed
    # the narrative off page 1 even for median-length text — Phase 3
    # forensic finding §3.1. See [[feedback-two-page-overflow-contract]].
    height_in: float = 2.0,
    dpi: int = 150,
) -> str:
    """Return base64-encoded PNG of a horizontal bar chart.

    Each dim is a dict with keys: label (str), value (float|None).
    None values draw a faint full-width gray bar labeled "Unavailable".
    """
    labels = [d["label"] for d in dimensions]
    values = [d.get("value") for d in dimensions]
    colors = [_UNAVAILABLE_COLOR if v is None else _BAR_COLOR for v in values]
    plot_values = [1.0 if v is None else float(v) for v in values]

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    y_pos = range(len(labels))
    ax.barh(list(y_pos), plot_values, color=colors, height=0.6)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, color=_TEXT_COLOR, fontsize=10)
    ax.set_xlim(0, 1.0)
    ax.set_xticks([0.0, 0.25, 0.5, 0.75, 1.0])
    ax.invert_yaxis()
    ax.tick_params(axis="x", colors=_TEXT_COLOR, labelsize=9)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#94a3b8")

    for i, v in enumerate(values):
        if v is None:
            ax.text(0.02, i, "Unavailable", va="center", ha="left",
                    color="#475569", fontsize=9, fontstyle="italic")
        else:
            ax.text(float(v) + 0.01, i, f"{float(v):.2f}",
                    va="center", ha="left", color=_TEXT_COLOR, fontsize=9)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")
