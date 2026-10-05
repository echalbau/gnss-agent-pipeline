"""Shared LangGraph state passed between nodes."""

from __future__ import annotations

from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    # inputs
    job_dir: str
    mode: str                      # ppp-static | ppp-kine | static | kinematic
    obs_path: str                  # rover RINEX obs (plain after node 1)
    nav_path: str | None
    base_path: str | None          # RTK base RINEX obs

    # 1. RINEX inspector
    qc: dict[str, Any]

    # 2. IGS downloader
    products: dict[str, Any]       # {"complete", "solution", "orbit": [...], "clock": [...], ...}

    # 3. Engine / 4. Evaluator loop
    engine_options: dict[str, Any]  # overrides on top of settings.engine.options
    attempt: int
    solution: dict[str, Any]       # {"pos_path", "conf_path", "error"}
    evaluation: dict[str, Any]     # {"decision", "metrics", "accepted", "reasons", ...}
    history: list[dict[str, Any]]  # one entry per engine attempt

    # 5. Report
    coordinates: dict[str, Any]
    summary: str
    report_pdf: str

    # bookkeeping
    alerts: list[str]
    status: str                    # running | completed | completed_with_warnings | failed
