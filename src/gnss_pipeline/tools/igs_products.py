"""IGS product resolution and fetching across mirrors. Used as agent tools and as fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..gnss_time import GnssDay
from .download import DownloadError, fetch

DAILY_KINDS = ("orbit", "clock", "brdc")
KINDS = (*DAILY_KINDS, "atx")
REQUIRED_PPP = ("orbit", "clock", "atx")


class ProductFetcher:
    def __init__(self, cfg: dict[str, Any], days: list[GnssDay], cache_dir: str | Path):
        self.cfg = cfg
        self.days = days
        self.cache = Path(cache_dir)
        self.mirrors = {m["name"]: m for m in cfg["mirrors"]}
        self.products: dict[str, list[str]] = {}
        self.solution: str | None = None
        self.log: list[dict[str, Any]] = []

    # ---- tool surface -------------------------------------------------
    def fetch(self, kind: str, solution: str | None = None, mirror: str | None = None) -> dict:
        """Fetch one product kind for every day of the session from one mirror."""
        if kind not in KINDS:
            return self._record(kind, solution, mirror, False, error=f"unknown kind {kind}")
        if kind == "atx":
            return self._fetch_atx()
        if kind in ("orbit", "clock"):
            solution = solution or self.cfg["solutions"][0]
            if solution not in self.cfg["catalog"]:
                return self._record(kind, solution, mirror, False, error="unknown solution")
            if self.solution and solution != self.solution and "orbit" in self.products:
                # orbit and clock must be consistent
                return self._record(kind, solution, mirror, False,
                                    error=f"orbits already from {self.solution}; "
                                          "use the same solution")
        mirror = mirror or next(iter(self.mirrors))
        if mirror not in self.mirrors:
            return self._record(kind, solution, mirror, False, error="unknown mirror")

        m = self.mirrors[mirror]
        paths = []
        for day in self.days:
            if kind == "brdc":
                url = m["daily_url"].format(**day.fmt()) + self.cfg["brdc"].format(**day.fmt())
                subdir = self.cache / "brdc"
            else:
                tmpl = self.cfg["catalog"][solution][kind]
                url = m["products_url"].format(**day.fmt()) + tmpl.format(**day.fmt())
                subdir = self.cache / str(day.week)
            try:
                paths.append(str(fetch(url, subdir, self.cfg["timeout_s"])))
            except DownloadError as exc:
                return self._record(kind, solution, mirror, False, url=url, error=str(exc))

        self.products[kind] = paths
        if kind in ("orbit", "clock"):
            self.solution = solution
        return self._record(kind, solution, mirror, True, paths=paths)

    def status(self) -> dict:
        return {
            "have": {k: len(v) for k, v in self.products.items()},
            "missing": self.missing(),
            "solution": self.solution,
            "days": [f"{d.year}-{d.doy:03d} (week {d.week})" for d in self.days],
        }

    # ---- deterministic fallback ---------------------------------------
    def missing(self, required: tuple[str, ...] = REQUIRED_PPP) -> list[str]:
        return [k for k in required if k not in self.products]

    def fetch_with_fallback(self, kinds: list[str]) -> None:
        if "atx" in kinds and "atx" not in self.products:
            self._fetch_atx()
        if "brdc" in kinds and "brdc" not in self.products:
            for mirror in self.mirrors:
                if self.fetch("brdc", mirror=mirror)["ok"]:
                    break
        precise = [k for k in ("orbit", "clock") if k in kinds and k not in self.products]
        if not precise:
            return
        solutions = [self.solution] if self.solution else self.cfg["solutions"]
        for solution in solutions:
            for kind in ("orbit", "clock"):
                if kind in self.products:
                    continue
                for mirror in self.mirrors:
                    if self.fetch(kind, solution, mirror)["ok"]:
                        break
            if "orbit" in self.products and "clock" in self.products:
                return
            # inconsistent partial set: drop and try next solution
            self.products.pop("orbit", None)
            self.products.pop("clock", None)
            self.solution = None

    # ---- internals ----------------------------------------------------
    def _fetch_atx(self) -> dict:
        err = None
        for url in self.cfg["atx_urls"]:
            try:
                path = fetch(url, self.cache / "atx", self.cfg["timeout_s"])
                self.products["atx"] = [str(path)]
                return self._record("atx", None, url, True, paths=[str(path)])
            except DownloadError as exc:
                err = str(exc)
        return self._record("atx", None, None, False, error=err)

    def _record(self, kind, solution, mirror, ok, **extra) -> dict:
        entry = {"kind": kind, "solution": solution, "mirror": mirror, "ok": ok, **extra}
        self.log.append(entry)
        return entry
