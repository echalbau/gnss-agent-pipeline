"""Convergence plot + PDF report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .metrics import enu_sigmas


def convergence_plot(sol: dict[str, np.ndarray], out: Path) -> Path:
    sig, _ = enu_sigmas(sol)
    hours = (sol["t"] - sol["t"][0]) / np.timedelta64(1, "h")
    fig, ax = plt.subplots(figsize=(7, 3))
    for i, lab in enumerate(("East", "North", "Up")):
        ax.semilogy(hours, sig[:, i] * 100, lw=1, label=lab)
    ax.set_xlabel("Time since first epoch [h]")
    ax.set_ylabel("Formal sigma [cm]")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(frameon=False, ncol=3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def _table(rows: list[list[Any]], widths=None) -> Table:
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def build_pdf(out: Path, *, state: dict[str, Any], metrics: dict[str, Any],
              summary: str, plot: Path | None) -> Path:
    styles = getSampleStyleSheet()
    qc = state.get("qc", {})
    products = state.get("products", {})
    x, y, z = metrics["final_xyz"]
    lat, lon, h = metrics["final_llh"]
    se, sn, su = (v * 100 for v in metrics["sigma_enu_m"])

    story = [
        Paragraph(f"GNSS processing report: {qc.get('marker') or 'station'}", styles["Title"]),
        Paragraph(f"Mode {state['mode']} | {qc.get('first_epoch', '?')} to "
                  f"{qc.get('last_epoch', '?')} GPST | status {state.get('status', '')}",
                  styles["Normal"]),
        Spacer(1, 0.4 * cm),
        Paragraph("Final coordinates (frame of the precise products, epoch of observation)",
                  styles["Heading2"]),
        _table([
            ["", "Value", "Sigma"],
            ["X [m]", f"{x:.4f}", ""], ["Y [m]", f"{y:.4f}", ""], ["Z [m]", f"{z:.4f}", ""],
            ["Latitude", f"{lat:.9f} deg", f"N {sn:.1f} cm"],
            ["Longitude", f"{lon:.9f} deg", f"E {se:.1f} cm"],
            ["Ellipsoidal h", f"{h:.4f} m", f"U {su:.1f} cm"],
        ], widths=[3.5 * cm, 5.5 * cm, 3 * cm]),
        Spacer(1, 0.4 * cm),
        Paragraph("Summary", styles["Heading2"]),
        Paragraph(summary, styles["BodyText"]),
    ]
    if plot and plot.exists():
        story += [Spacer(1, 0.3 * cm), Image(str(plot), width=16 * cm, height=6.9 * cm)]

    story += [
        Paragraph("Input quality control", styles["Heading2"]),
        _table([
            ["Item", "Value"],
            ["RINEX version", qc.get("version")],
            ["Receiver / antenna", f"{qc.get('receiver', '')} / {qc.get('antenna', '')}"],
            ["Epochs / interval", f"{qc.get('n_epochs')} / {qc.get('interval_s')} s"],
            ["Duration", f"{qc.get('duration_h', 0):.2f} h"],
            ["Missing epochs", f"{qc.get('gap_ratio', 0):.1%}"],
            ["Warnings", "; ".join(qc.get("warnings", [])) or "none"],
        ], widths=[4 * cm, 12 * cm]),
        Paragraph("Products", styles["Heading2"]),
        _table([["Kind", "Files"]] + [
            [k, "\n".join(Path(p).name for p in products.get(k, []))]
            for k in ("orbit", "clock", "atx", "brdc") if products.get(k)
        ], widths=[2.5 * cm, 13.5 * cm]),
        Paragraph("Processing attempts", styles["Heading2"]),
        _table([["#", "Changes", "sigma_h [cm]", "sigma_v [cm]", "Fix ratio", "Accepted"]] + [
            [h["attempt"],
             ", ".join(f"{k}={v}" for k, v in h.get("changes", {}).items()) or "baseline",
             f"{h['metrics']['sigma_h_m']*100:.1f}" if h.get("metrics") else "-",
             f"{h['metrics']['sigma_v_m']*100:.1f}" if h.get("metrics") else "-",
             f"{h['metrics']['fix_ratio']:.0%}" if h.get("metrics") else "-",
             "yes" if h.get("accepted") else "no"]
            for h in state.get("history", [])
        ]),
    ]
    SimpleDocTemplate(str(out), pagesize=A4, title="GNSS processing report",
                      leftMargin=2 * cm, rightMargin=2 * cm).build(story)
    return out
