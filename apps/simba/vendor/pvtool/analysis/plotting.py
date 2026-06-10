"""
Dark-mode matplotlib helpers — GitHub dark theme.

Usage
-----
>>> from pvtool.analysis.plotting import apply_dark_mode, COLORS
>>> apply_dark_mode()
>>> plt.plot(x, y, color=COLORS["blue"])
"""

import matplotlib.pyplot as plt

# GitHub dark theme palette
COLORS = {
    "bg": "#0d1117",
    "axes": "#161b22",
    "grid": "#30363d",
    "reference": "#8b949e",
    "blue": "#2196F3",
    "green": "#4CAF50",
    "orange": "#FF9800",
    "red": "#F44336",
    "purple": "#AB47BC",
    "light_green": "#8BC34A",
}

RC_PARAMS = {
    "figure.facecolor": COLORS["bg"],
    "axes.facecolor": COLORS["axes"],
    "axes.edgecolor": COLORS["reference"],
    "axes.labelcolor": "#c9d1d9",
    "axes.titlecolor": "#c9d1d9",
    "text.color": "#c9d1d9",
    "xtick.color": "#8b949e",
    "ytick.color": "#8b949e",
    "grid.color": COLORS["grid"],
    "grid.linewidth": 0.8,
    "legend.facecolor": COLORS["axes"],
    "legend.edgecolor": COLORS["grid"],
    "savefig.facecolor": COLORS["bg"],
    "figure.dpi": 120,
}


def apply_dark_mode() -> None:
    """Apply GitHub dark theme to all subsequent matplotlib figures."""
    plt.style.use("dark_background")
    plt.rcParams.update(RC_PARAMS)


def bar_colors(values, positive=COLORS["green"], negative=COLORS["red"]):
    """Return a list of colors based on the sign of each value."""
    return [positive if v >= 0 else negative for v in values]
