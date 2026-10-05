"""Solution quality metrics and acceptance criteria (deterministic part of node 4)."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..config import RTK_MODES
from ..geodesy import cov_ecef_to_enu, ecef_to_geodetic

Q_LABELS = {1: "fix", 2: "float", 3: "sbas", 4: "dgps", 5: "single", 6: "ppp"}


def enu_sigmas(sol: dict[str, np.ndarray]) -> tuple[np.ndarray, tuple[float, float, float]]:
    lat, lon, h = ecef_to_geodetic(*sol["xyz"][-1])
    cov_enu = cov_ecef_to_enu(sol["cov"], lat, lon)
    sig = np.sqrt(np.clip(np.diagonal(cov_enu, axis1=1, axis2=2), 0, None))
    return sig, (lat, lon, h)


def summarize(sol: dict[str, np.ndarray], cfg: dict[str, Any]) -> dict[str, Any]:
    n = int(sol["q"].size)
    if n == 0:
        return {"n_epochs": 0}
    sig, (lat, lon, h) = enu_sigmas(sol)
    sig_h = np.hypot(sig[:, 0], sig[:, 1])

    below = sig_h <= cfg["ppp"]["max_sigma_h_m"]
    bad = np.flatnonzero(~below)
    conv_idx = 0 if bad.size == 0 else int(bad[-1]) + 1
    converged = conv_idx < n
    conv_min = (
        float((sol["t"][conv_idx] - sol["t"][0]) / np.timedelta64(1, "s")) / 60.0
        if converged else None
    )

    values, counts = np.unique(sol["q"], return_counts=True)
    q_counts = {Q_LABELS.get(int(k), str(k)): int(v) for k, v in zip(values, counts, strict=True)}
    x, y, z = (float(v) for v in sol["xyz"][-1])
    return {
        "n_epochs": n,
        "q_counts": q_counts,
        "fix_ratio": float(np.mean(sol["q"] == 1)),
        "mean_nsat": float(np.mean(sol["ns"])),
        "final_xyz": [x, y, z],
        "final_llh": [lat, lon, h],
        "sigma_enu_m": [float(v) for v in sig[-1]],
        "sigma_h_m": float(sig_h[-1]),
        "sigma_v_m": float(sig[-1, 2]),
        "converged": bool(converged),
        "convergence_min": conv_min,
        "last_ratio": float(sol["ratio"][-1]),
    }


def assess(metrics: dict[str, Any], mode: str, cfg: dict[str, Any]) -> tuple[bool, list[str]]:
    if metrics.get("n_epochs", 0) == 0:
        return False, ["no solution epochs"]
    reasons = []
    if mode in RTK_MODES:
        if metrics["fix_ratio"] < cfg["rtk"]["min_fix_ratio"]:
            reasons.append(
                f"fix ratio {metrics['fix_ratio']:.1%} < {cfg['rtk']['min_fix_ratio']:.0%} "
                "(float ambiguities)"
            )
    else:
        if metrics["sigma_h_m"] > cfg["ppp"]["max_sigma_h_m"]:
            reasons.append(f"sigma_h {metrics['sigma_h_m']*100:.1f} cm > "
                           f"{cfg['ppp']['max_sigma_h_m']*100:.1f} cm")
        if metrics["sigma_v_m"] > cfg["ppp"]["max_sigma_v_m"]:
            reasons.append(f"sigma_v {metrics['sigma_v_m']*100:.1f} cm > "
                           f"{cfg['ppp']['max_sigma_v_m']*100:.1f} cm")
        if not metrics["converged"]:
            reasons.append("filter did not converge")
    return not reasons, reasons
