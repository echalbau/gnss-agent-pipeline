"""LangGraph wiring of the pipeline (see README diagram)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import PipelineState


def route_after_qc(state: PipelineState) -> str:
    return "ok" if state.get("qc", {}).get("passed") else "fail"


def route_after_download(state: PipelineState) -> str:
    return "ok" if state.get("products", {}).get("complete") else "fail"


def route_after_engine(state: PipelineState) -> str:
    return "fail" if state.get("solution", {}).get("error") else "ok"


def route_after_evaluation(state: PipelineState) -> str:
    return state["evaluation"]["decision"]  # accept | retry | exhausted


def _bind(fn: Callable, settings: dict[str, Any]) -> Callable[[PipelineState], dict]:
    def node(state: PipelineState) -> dict:
        return fn(state, settings)

    node.__name__ = fn.__name__
    return node


def build_graph(settings: dict[str, Any]):
    g = StateGraph(PipelineState)
    for name in ("inspect_rinex", "download_products", "run_engine",
                 "evaluate_precision", "generate_report", "raise_alert"):
        g.add_node(name, _bind(getattr(nodes, name), settings))

    g.add_edge(START, "inspect_rinex")
    g.add_conditional_edges("inspect_rinex", route_after_qc,
                            {"ok": "download_products", "fail": "raise_alert"})
    g.add_conditional_edges("download_products", route_after_download,
                            {"ok": "run_engine", "fail": "raise_alert"})
    g.add_conditional_edges("run_engine", route_after_engine,
                            {"ok": "evaluate_precision", "fail": "raise_alert"})
    g.add_conditional_edges("evaluate_precision", route_after_evaluation,
                            {"retry": "run_engine", "accept": "generate_report",
                             "exhausted": "generate_report"})
    g.add_edge("generate_report", END)
    g.add_edge("raise_alert", END)
    return g.compile()
