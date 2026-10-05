"""High-level entry point shared by the CLI and the API."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import available_modes, load_settings
from .graph import build_graph
from .state import PipelineState

StageCallback = Callable[[str, dict[str, Any]], None]


def new_job_dir(settings: dict[str, Any]) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    path = Path(settings["paths"]["work_root"]) / f"{stamp}_{uuid.uuid4().hex[:6]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_pipeline(obs: str | Path, *, nav: str | Path | None = None,
                 base: str | Path | None = None, mode: str | None = None,
                 job_dir: str | Path | None = None, settings: dict[str, Any] | None = None,
                 on_stage: StageCallback | None = None) -> PipelineState:
    settings = settings or load_settings()
    mode = mode or settings["engine"]["default_mode"]
    if mode not in available_modes(settings):
        raise ValueError(f"unknown mode '{mode}', choose from {available_modes(settings)}")
    job_dir = Path(job_dir) if job_dir else new_job_dir(settings)
    job_dir.mkdir(parents=True, exist_ok=True)

    state: PipelineState = {
        "job_dir": str(job_dir.resolve()),
        "mode": mode,
        "obs_path": str(Path(obs).resolve()),
        "nav_path": str(Path(nav).resolve()) if nav else None,
        "base_path": str(Path(base).resolve()) if base else None,
        "engine_options": {},
        "attempt": 0,
        "history": [],
        "alerts": [],
        "status": "running",
    }
    final: dict[str, Any] = dict(state)
    graph = build_graph(settings)
    for update in graph.stream(state, config={"recursion_limit": 60}, stream_mode="updates"):
        for node, delta in update.items():
            final.update(delta or {})
            if on_stage:
                on_stage(node, delta or {})
    return final  # type: ignore[return-value]
