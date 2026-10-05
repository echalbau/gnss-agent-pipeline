"""Node 1: RINEX inspector (pure Python QA/QC)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import PPP_MODES, RTK_MODES
from ..state import PipelineState
from ..tools.rinex import RinexError, prepare_rinex, quality_check


def inspect_rinex(state: PipelineState, settings: dict[str, Any]) -> dict[str, Any]:
    work = Path(state["job_dir"]) / "rinex"
    alerts = list(state.get("alerts", []))
    mode = state["mode"]

    if mode in RTK_MODES and not state.get("base_path"):
        alerts.append(f"Mode '{mode}' needs a base station RINEX file")
        return {"qc": {"passed": False, "errors": alerts[-1:]}, "alerts": alerts}

    try:
        obs = prepare_rinex(state["obs_path"], work)
        base = prepare_rinex(state["base_path"], work) if state.get("base_path") else None
        nav = prepare_rinex(state["nav_path"], work) if state.get("nav_path") else None
    except (RinexError, OSError) as exc:
        alerts.append(f"Could not open input: {exc}")
        return {"qc": {"passed": False, "errors": [str(exc)]}, "alerts": alerts}

    qc = quality_check(obs, settings["rinex_qc"], require_dual_freq=mode in PPP_MODES)
    if base is not None:
        base_qc = quality_check(base, settings["rinex_qc"], require_dual_freq=False)
        qc["base"] = base_qc
        if not base_qc["passed"]:
            qc["passed"] = False
            qc["errors"] = qc["errors"] + [f"base: {e}" for e in base_qc["errors"]]

    if not qc["passed"]:
        alerts += [f"RINEX QC: {e}" for e in qc["errors"]]
    return {
        "qc": qc,
        "obs_path": str(obs),
        "base_path": str(base) if base else None,
        "nav_path": str(nav) if nav else None,
        "alerts": alerts,
    }
