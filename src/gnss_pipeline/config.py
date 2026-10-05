"""Settings loading: packaged defaults + optional YAML override + env vars."""

from __future__ import annotations

import copy
import os
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

RTK_MODES = {"static", "kinematic"}
PPP_MODES = {"ppp-static", "ppp-kine"}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings(path: str | os.PathLike | None = None) -> dict[str, Any]:
    text = resources.files("gnss_pipeline").joinpath("settings.yaml").read_text()
    settings = yaml.safe_load(text)

    override = path or os.getenv("GNSS_PIPELINE_CONFIG")
    if override:
        settings = _deep_merge(settings, yaml.safe_load(Path(override).read_text()) or {})

    env_map = {
        "GNSS_LLM_MODEL": ("llm", "model"),
        "RNX2RTKP": ("engine", "rnx2rtkp"),
        "GNSS_WORK_ROOT": ("paths", "work_root"),
        "GNSS_PRODUCT_CACHE": ("paths", "product_cache"),
    }
    for env, (section, key) in env_map.items():
        if value := os.getenv(env):
            settings[section][key] = value
    return settings


def available_modes(settings: dict) -> list[str]:
    return [m for m in settings["engine"]["options"] if m != "common"]
