"""Node 3: RTK/PPP engine (RTKLIB rnx2rtkp)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..state import PipelineState
from ..tools.rtklib import EngineError, run_rnx2rtkp, write_conf


def build_options(state: PipelineState, settings: dict[str, Any]) -> dict[str, Any]:
    opts = settings["engine"]["options"]
    options = {**opts["common"], **opts[state["mode"]], **state.get("engine_options", {})}
    atx = state.get("products", {}).get("atx")
    if atx:
        options["file-satantfile"] = atx[0]
        options["file-rcvantfile"] = atx[0]
    return options


def build_inputs(state: PipelineState) -> list[str]:
    products = state.get("products", {})
    inputs = [state["obs_path"]]
    if state.get("base_path"):
        inputs.append(state["base_path"])
    if state.get("nav_path"):
        inputs.append(state["nav_path"])
    else:
        inputs += products.get("brdc", [])
    inputs += products.get("orbit", []) + products.get("clock", [])
    return inputs


def run_engine(state: PipelineState, settings: dict[str, Any]) -> dict[str, Any]:
    attempt = state.get("attempt", 0) + 1
    run_dir = Path(state["job_dir"]) / f"attempt_{attempt:02d}"
    options = build_options(state, settings)
    conf = write_conf(options, run_dir / "rnx2rtkp.conf")
    pos = run_dir / "solution.pos"

    entry = {"attempt": attempt, "options": dict(state.get("engine_options", {})),
             "changes": state.get("evaluation", {}).get("changes", {})}
    history = [*state.get("history", []), entry]
    alerts = list(state.get("alerts", []))
    try:
        run_rnx2rtkp(settings["engine"]["rnx2rtkp"], conf, pos, build_inputs(state),
                     settings["engine"]["timeout_s"])
        solution = {"pos_path": str(pos), "conf_path": str(conf), "error": None}
    except EngineError as exc:
        solution = {"pos_path": None, "conf_path": str(conf), "error": str(exc)}
        alerts.append(f"Engine (attempt {attempt}): {exc}")
    return {"attempt": attempt, "solution": solution, "history": history, "alerts": alerts}
