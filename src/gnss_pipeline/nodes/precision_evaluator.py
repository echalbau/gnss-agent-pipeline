"""Node 4: precision evaluator (deterministic acceptance + LLM-proposed retuning)."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..llm.client import LLMClient
from ..llm.prompts import EVALUATOR_SYSTEM
from ..state import PipelineState
from ..tools import tuning
from ..tools.metrics import assess, summarize
from ..tools.rtklib import parse_pos

log = logging.getLogger(__name__)


def propose_changes(state: PipelineState, settings: dict[str, Any], metrics: dict[str, Any],
                    reasons: list[str], history: list[dict]) -> tuple[dict, str, str]:
    """Return (changes, diagnosis, source). Never returns an option set already tried."""
    current = dict(state.get("engine_options", {}))
    llm = LLMClient(settings["llm"])
    if llm.enabled:
        prompt = json.dumps({
            "mode": state["mode"],
            "failed_criteria": reasons,
            "metrics": metrics,
            "current_overrides": current,
            "base_options": {**settings["engine"]["options"]["common"],
                             **settings["engine"]["options"][state["mode"]]},
            "history": [{"overrides": h["options"], "metrics": h.get("metrics")} for h in history],
            "allowed": {
                k: list(v[1]) if v[0] == "enum" else {"type": v[0], "min": v[1], "max": v[2]}
                for k, v in tuning.TUNABLE.items()
            },
        }, default=str)
        try:
            reply = llm.complete_json(EVALUATOR_SYSTEM, prompt)
            changes = tuning.validate(reply.get("changes", {}))
            if changes and not tuning.already_tried({**current, **changes}, history):
                return changes, str(reply.get("diagnosis", "")), "llm"
        except Exception as exc:
            log.warning("evaluator LLM failed, using heuristic: %s", exc)

    changes = tuning.heuristic(state["mode"], state["attempt"])
    return changes, "; ".join(reasons), "heuristic"


def evaluate_precision(state: PipelineState, settings: dict[str, Any]) -> dict[str, Any]:
    cfg = settings["evaluation"]
    sol = parse_pos(state["solution"]["pos_path"])
    metrics = summarize(sol, cfg)
    accepted, reasons = assess(metrics, state["mode"], cfg)

    history = list(state.get("history", []))
    history[-1] = {**history[-1], "metrics": metrics, "accepted": accepted, "reasons": reasons}

    evaluation: dict[str, Any] = {"metrics": metrics, "accepted": accepted, "reasons": reasons,
                                  "changes": {}}
    update: dict[str, Any] = {"history": history}

    if accepted:
        evaluation["decision"] = "accept"
    elif state["attempt"] >= cfg["max_attempts"]:
        evaluation["decision"] = "exhausted"
    else:
        changes, diagnosis, source = propose_changes(state, settings, metrics, reasons, history)
        evaluation.update(decision="retry", changes=changes, diagnosis=diagnosis, source=source)
        update["engine_options"] = {**state.get("engine_options", {}), **changes}

    update["evaluation"] = evaluation
    return update
