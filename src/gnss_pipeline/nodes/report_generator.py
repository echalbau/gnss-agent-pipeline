"""Node 5: report generator (LLM summary + PDF + result.json)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..llm.client import LLMClient
from ..llm.prompts import REPORT_SYSTEM
from ..state import PipelineState
from ..tools.report_pdf import build_pdf, convergence_plot
from ..tools.rtklib import parse_pos

log = logging.getLogger(__name__)


def template_summary(state: PipelineState, metrics: dict[str, Any]) -> str:
    qc, ev = state["qc"], state["evaluation"]
    se, sn, su = (v * 100 for v in metrics["sigma_enu_m"])
    solution = state["products"].get("solution")
    text = (
        f"Processed {qc['n_epochs']} epochs ({qc['duration_h']:.1f} h at {qc['interval_s']:g} s) "
        f"from station {qc.get('marker') or 'unknown'} in {state['mode']} mode"
        f"{f' with IGS {solution} products' if solution else ''}. "
        f"Final formal precision: E {se:.1f} cm, N {sn:.1f} cm, U {su:.1f} cm "
        f"after {state['attempt']} attempt(s)."
    )
    if metrics.get("convergence_min") is not None:
        text += f" Horizontal convergence after {metrics['convergence_min']:.0f} min."
    if ev["decision"] == "exhausted":
        text += (" WARNING: the precision criteria were not met within the retry budget ("
                 + "; ".join(ev["reasons"]) + "). Use these coordinates with caution.")
    if qc.get("warnings"):
        text += " QC warnings: " + "; ".join(qc["warnings"]) + "."
    return text


def generate_report(state: PipelineState, settings: dict[str, Any]) -> dict[str, Any]:
    job = Path(state["job_dir"])
    metrics = state["evaluation"]["metrics"]
    accepted = state["evaluation"]["decision"] == "accept"
    status = "completed" if accepted else "completed_with_warnings"

    summary = None
    llm = LLMClient(settings["llm"])
    if llm.enabled:
        payload = {k: state.get(k) for k in ("mode", "qc", "attempt", "evaluation")}
        payload["products"] = {k: v for k, v in state["products"].items() if k != "log"}
        payload["history"] = [{k: h.get(k) for k in ("attempt", "changes", "metrics", "accepted")}
                              for h in state.get("history", [])]
        try:
            summary = llm.complete_text(REPORT_SYSTEM, json.dumps(payload, default=str))
        except Exception as exc:
            log.warning("report LLM failed, using template: %s", exc)
    summary = summary or template_summary(state, metrics)

    sol = parse_pos(state["solution"]["pos_path"])
    plot = convergence_plot(sol, job / "convergence.png")
    pdf = build_pdf(job / "report.pdf", state={**state, "status": status},
                    metrics=metrics, summary=summary, plot=plot)

    coordinates = {
        "xyz_m": metrics["final_xyz"],
        "llh": {"lat_deg": metrics["final_llh"][0], "lon_deg": metrics["final_llh"][1],
                "h_m": metrics["final_llh"][2]},
        "sigma_enu_m": metrics["sigma_enu_m"],
    }
    (job / "result.json").write_text(json.dumps({
        "status": status, "coordinates": coordinates, "metrics": metrics,
        "summary": summary, "attempts": state["attempt"],
    }, indent=2))
    return {"coordinates": coordinates, "summary": summary, "report_pdf": str(pdf),
            "status": status}
