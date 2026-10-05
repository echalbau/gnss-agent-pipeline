"""Whitelisted RTKLIB option retuning: LLM proposals are validated here; heuristics as fallback."""

from __future__ import annotations

from typing import Any

from ..config import RTK_MODES

# key -> ("float"|"int", lo, hi) or ("enum", [values])
TUNABLE: dict[str, tuple] = {
    "pos1-elmask": ("float", 5, 30),
    "pos1-soltype": ("enum", ["forward", "backward", "combined"]),
    "pos1-tropopt": ("enum", ["saas", "est-ztd", "est-ztdgrad"]),
    "pos2-armode": ("enum", ["off", "continuous", "instantaneous", "fix-and-hold"]),
    "pos2-arthres": ("float", 1.5, 5.0),
    "pos2-arlockcnt": ("int", 0, 20),
    "pos2-elmaskar": ("float", 0, 30),
    "stats-prnbias": ("float", 1e-6, 1e-2),
    "stats-prnztd": ("float", 1e-6, 1e-3),
    "stats-eratio1": ("float", 50, 300),
}

HEURISTICS = {
    "ppp": [
        {"pos1-soltype": "combined"},
        {"pos1-elmask": 15, "pos1-tropopt": "est-ztdgrad"},
        {"pos1-elmask": 7, "stats-prnbias": 1e-3},
    ],
    "rtk": [
        {"pos2-arthres": 2.5},
        {"pos1-elmask": 15, "pos2-armode": "continuous"},
        {"pos1-soltype": "combined", "pos2-arlockcnt": 5},
    ],
}


def validate(changes: dict[str, Any]) -> dict[str, Any]:
    """Drop unknown keys, clamp numeric values, reject invalid enums."""
    clean: dict[str, Any] = {}
    for key, value in (changes or {}).items():
        spec = TUNABLE.get(key)
        if spec is None:
            continue
        if spec[0] == "enum":
            if value in spec[1]:
                clean[key] = value
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        v = min(max(v, spec[1]), spec[2])
        clean[key] = round(v) if spec[0] == "int" else v
    return clean


def heuristic(mode: str, attempt: int) -> dict[str, Any]:
    plan = HEURISTICS["rtk" if mode in RTK_MODES else "ppp"]
    return plan[min(attempt - 1, len(plan) - 1)]


def already_tried(options: dict[str, Any], history: list[dict[str, Any]]) -> bool:
    return any(h.get("options") == options for h in history)
