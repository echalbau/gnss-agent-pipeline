"""Node 2: IGS product downloader (tool-using agent with deterministic safety net)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..config import RTK_MODES
from ..gnss_time import days_spanned
from ..llm.client import LLMClient
from ..llm.prompts import DOWNLOADER_SYSTEM
from ..state import PipelineState
from ..tools.igs_products import KINDS, REQUIRED_PPP, ProductFetcher

log = logging.getLogger(__name__)


def _agent_tools(fetcher: ProductFetcher) -> tuple[list[dict], dict]:
    tools = [
        {
            "name": "download_product",
            "description": "Download one product kind for all session days from one mirror. "
                           "Returns ok/paths or the error (not found, timeout, login page...).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "solution": {"type": "string", "enum": list(fetcher.cfg["catalog"])},
                    "mirror": {"type": "string", "enum": list(fetcher.mirrors)},
                },
                "required": ["kind"],
            },
        },
        {
            "name": "product_status",
            "description": "Which products are present/missing and the session days.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "finish",
            "description": "Stop the agent.",
            "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}},
                             "required": ["summary"]},
        },
    ]
    handlers = {"download_product": fetcher.fetch, "product_status": fetcher.status}
    return tools, handlers


def acquire_products(state: PipelineState, settings: dict[str, Any]) -> dict[str, Any]:
    qc = state["qc"]
    days = days_spanned(datetime.fromisoformat(qc["first_epoch"]),
                        datetime.fromisoformat(qc["last_epoch"]))
    fetcher = ProductFetcher(settings["products"], days, settings["paths"]["product_cache"])

    if state["mode"] in RTK_MODES:
        required: tuple[str, ...] = () if state.get("nav_path") else ("brdc",)
        wanted = list(required)
    else:
        required = REQUIRED_PPP
        wanted = [*REQUIRED_PPP, *([] if state.get("nav_path") else ["brdc"])]

    agent_summary = None
    llm = LLMClient(settings["llm"])
    if llm.enabled and wanted:
        tools, handlers = _agent_tools(fetcher)
        prompt = (f"Session days: {fetcher.status()['days']}. Needed: {wanted}. "
                  f"Solutions in preference order: {settings['products']['solutions']}. "
                  f"Mirrors in preference order: {list(fetcher.mirrors)}.")
        try:
            agent_summary = llm.run_tools(DOWNLOADER_SYSTEM, prompt, tools, handlers)
        except Exception as exc:  # API outage must not kill the pipeline
            log.warning("downloader agent failed, using fallback: %s", exc)

    still_missing = [k for k in wanted if k not in fetcher.products]
    if still_missing:
        fetcher.fetch_with_fallback(still_missing)

    return {
        **fetcher.products,
        "solution": fetcher.solution,
        "complete": not fetcher.missing(required),
        "missing": fetcher.missing(required),
        "agent_summary": agent_summary,
        "log": fetcher.log,
    }


def download_products(state: PipelineState, settings: dict[str, Any]) -> dict[str, Any]:
    products = acquire_products(state, settings)
    alerts = list(state.get("alerts", []))
    if not products["complete"]:
        tried = sorted({f"{e.get('kind')}@{e.get('mirror')}" for e in products["log"]})
        alerts.append(f"Missing products {products['missing']} after trying {tried}")
    return {"products": products, "alerts": alerts}
