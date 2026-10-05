"""Terminal node for unrecoverable failures ([Fin con Alerta])."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..state import PipelineState


def raise_alert(state: PipelineState, settings: dict[str, Any]) -> dict[str, Any]:
    alerts = state.get("alerts") or ["Pipeline stopped without a recorded reason"]
    Path(state["job_dir"], "alert.json").write_text(json.dumps({
        "status": "failed", "alerts": alerts, "qc": state.get("qc"),
    }, indent=2, default=str))
    return {"status": "failed", "alerts": alerts}
