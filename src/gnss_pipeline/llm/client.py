"""Thin Anthropic wrapper: JSON completions and a tool-use agent loop."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.enabled = bool(cfg.get("enabled", True) and os.getenv("ANTHROPIC_API_KEY"))
        self._client = None
        if self.enabled:
            import anthropic

            self._client = anthropic.Anthropic()

    def _create(self, **kwargs):
        return self._client.messages.create(
            model=self.cfg["model"], max_tokens=self.cfg["max_tokens"], **kwargs
        )

    def complete_text(self, system: str, prompt: str) -> str:
        resp = self._create(system=system, messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def complete_json(self, system: str, prompt: str) -> dict[str, Any]:
        text = self.complete_text(system + "\nRespond with a single JSON object only.", prompt)
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        return json.loads(text)

    def run_tools(self, system: str, prompt: str, tools: list[dict],
                  handlers: dict[str, Callable[..., Any]], stop_tool: str = "finish") -> str:
        """Run a tool-use loop until the model calls `stop_tool` or stops using tools."""
        messages: list[dict] = [{"role": "user", "content": prompt}]
        for _ in range(self.cfg["agent_max_turns"]):
            resp = self._create(system=system, tools=tools, messages=messages)
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                return "".join(b.text for b in resp.content if b.type == "text")

            results, finished = [], None
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                if block.name == stop_tool:
                    finished = block.input.get("summary", "")
                    out: Any = {"ok": True}
                else:
                    try:
                        out = handlers[block.name](**block.input)
                    except Exception as exc:  # report tool errors back to the model
                        out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                log.info("agent tool %s(%s) -> %s", block.name, block.input, out)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(out, default=str)})
            messages.append({"role": "user", "content": results})
            if finished is not None:
                return finished
        return "agent turn limit reached"
