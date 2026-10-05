"""Lightweight RINEX 2/3/4 observation reader for QA/QC (header + epoch timeline)."""

from __future__ import annotations

import gzip
import re
import shutil
import statistics
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any


class RinexError(Exception):
    """File is unreadable, truncated or not a RINEX observation file."""


@dataclass
class RinexHeader:
    version: float = 0.0
    file_type: str = ""
    sat_system: str = ""
    marker_name: str = ""
    receiver: str = ""
    antenna: str = ""
    approx_xyz: tuple[float, float, float] | None = None
    interval: float | None = None
    first_obs: datetime | None = None
    obs_types: dict[str, list[str]] = field(default_factory=dict)
    n_lines: int = 0


# RINEX 2 epoch record: (1X,I2.2,5(1X,I2),F11.7,2X,I1,...)
_V2_EPOCH = re.compile(
    r"^ (\d\d) ([ \d]\d) ([ \d]\d) ([ \d]\d) ([ \d]\d)([ \d]{2}\d\.\d{7})  ([0-6])"
)


def _is_hatanaka(name: str) -> bool:
    low = name.lower()
    return low.endswith(".crx") or re.search(r"\.\d\dd$", low) is not None


def prepare_rinex(path: str | Path, work_dir: str | Path) -> Path:
    """Decompress (.gz/.Z) and de-Hatanaka (CRX) into work_dir. Returns plain RINEX path."""
    path, work_dir = Path(path), Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    if path.suffix in (".gz", ".Z"):
        out = work_dir / path.stem
        with open(out, "wb") as dst:
            if path.suffix == ".gz":
                with gzip.open(path, "rb") as src:
                    shutil.copyfileobj(src, dst)
            else:
                subprocess.run(["gzip", "-dc", str(path)], stdout=dst, check=True)
        path = out

    if _is_hatanaka(path.name):
        exe = shutil.which("crx2rnx") or shutil.which("CRX2RNX")
        if not exe:
            raise RinexError("Hatanaka-compressed RINEX (CRX) needs crx2rnx on PATH")
        name = re.sub(r"\.crx$", ".rnx", path.name, flags=re.IGNORECASE)
        name = re.sub(r"\.(\d\d)d$", r".\1o", name, flags=re.IGNORECASE)
        out = work_dir / name
        with open(path, "rb") as src, open(out, "wb") as dst:
            subprocess.run([exe, "-"], stdin=src, stdout=dst, check=True)
        path = out
    return path


def _floats(s: str) -> list[float]:
    return [float(v) for v in s.split()]


def read_header(path: str | Path) -> RinexHeader:
    hdr = RinexHeader()
    last_sys: str | None = None
    with open(path, errors="replace") as f:
        for i, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            content, label = line[:60], line[60:].strip()

            if label == "RINEX VERSION / TYPE":
                hdr.version = float(content[:9])
                hdr.file_type = content[20:21]
                hdr.sat_system = content[40:41].strip() or "G"
            elif label == "MARKER NAME":
                hdr.marker_name = content.strip()
            elif label == "REC # / TYPE / VERS":
                hdr.receiver = content[20:40].strip()
            elif label == "ANT # / TYPE":
                hdr.antenna = content[20:40].strip()
            elif label == "APPROX POSITION XYZ":
                x, y, z = _floats(content)[:3]
                hdr.approx_xyz = (x, y, z)
            elif label == "INTERVAL":
                hdr.interval = float(content.split()[0])
            elif label == "TIME OF FIRST OBS":
                p = content[:43].split()
                hdr.first_obs = datetime(*map(int, p[:5])) + timedelta(seconds=float(p[5]))
            elif label == "SYS / # / OBS TYPES":  # RINEX 3/4
                if content[0] != " ":
                    last_sys = content[0]
                    hdr.obs_types[last_sys] = content[7:].split()
                elif last_sys:
                    hdr.obs_types[last_sys] += content[7:].split()
            elif label == "# / TYPES OF OBSERV":  # RINEX 2
                hdr.obs_types.setdefault("*", []).extend(content[6:].split())
            elif label == "END OF HEADER":
                hdr.n_lines = i
                return hdr
            if i > 5000:
                break
    raise RinexError("END OF HEADER not found: file truncated or not RINEX")


def read_epochs(path: str | Path, hdr: RinexHeader) -> tuple[list[datetime], int]:
    """Return (epoch times, malformed epoch-record count). Event epochs (flag > 1) skipped."""
    times: list[datetime] = []
    malformed = 0
    with open(path, errors="replace") as f:
        for _ in range(hdr.n_lines):
            next(f)
        for line in f:
            if hdr.version >= 3:
                if not line.startswith(">"):
                    continue
                p = line[1:].split()
                try:
                    if int(p[6]) > 1:
                        continue
                    times.append(datetime(*map(int, p[:5])) + timedelta(seconds=float(p[5])))
                except (IndexError, ValueError):
                    malformed += 1
            else:
                m = _V2_EPOCH.match(line)
                if not m or int(m.group(7)) > 1:
                    continue
                yy = int(m.group(1))
                year = yy + (2000 if yy < 80 else 1900)
                try:
                    t = datetime(year, *(int(m.group(k)) for k in range(2, 6)))
                    times.append(t + timedelta(seconds=float(m.group(6))))
                except ValueError:
                    malformed += 1
    return times, malformed


def _is_dual_frequency(obs_types: dict[str, list[str]]) -> bool:
    for sys, types in obs_types.items():
        if sys not in ("G", "E", "C", "J", "*"):
            continue
        bands = {t[1] for t in types if len(t) >= 2 and t[0] in "CLP"}
        if len(bands) >= 2:
            return True
    return False


def quality_check(path: str | Path, cfg: dict[str, Any], require_dual_freq: bool) -> dict[str, Any]:
    """QA/QC report. `passed` is False if any error was found."""
    errors: list[str] = []
    warnings: list[str] = []
    report: dict[str, Any] = {"path": str(path)}

    try:
        hdr = read_header(path)
        times, malformed = read_epochs(path, hdr)
    except (RinexError, OSError, ValueError, IndexError) as exc:
        return {**report, "passed": False, "errors": [f"Unreadable RINEX: {exc}"], "warnings": []}

    if int(hdr.version) not in cfg["supported_major_versions"]:
        errors.append(f"Unsupported RINEX version {hdr.version}")
    if hdr.file_type != "O":
        errors.append(f"Not an observation file (type '{hdr.file_type}')")
    if not hdr.obs_types:
        errors.append("No observation types declared in header")
    if require_dual_freq and not _is_dual_frequency(hdr.obs_types):
        errors.append("Dual-frequency observations required for iono-free PPP")
    if hdr.approx_xyz is None or all(abs(v) < 1.0 for v in hdr.approx_xyz):
        warnings.append("APPROX POSITION XYZ missing or zero")
    if malformed:
        warnings.append(f"{malformed} malformed epoch records skipped")

    n = len(times)
    report.update(
        version=hdr.version, marker=hdr.marker_name, receiver=hdr.receiver,
        antenna=hdr.antenna, approx_xyz=hdr.approx_xyz, obs_types=hdr.obs_types,
        n_epochs=n,
    )
    if n < 2:
        errors.append(f"Only {n} epochs found: file empty or truncated")
        return {**report, "passed": False, "errors": errors, "warnings": warnings}

    if any(b <= a for a, b in pairwise(times)):
        errors.append("Epochs not strictly increasing (corrupt or concatenated file)")

    diffs = [(b - a).total_seconds() for a, b in pairwise(times)]
    interval = hdr.interval or statistics.median(diffs)
    duration = (times[-1] - times[0]).total_seconds()
    expected = round(duration / interval) + 1 if interval > 0 else n
    gap_ratio = max(0.0, 1.0 - n / expected) if expected else 0.0
    largest_gap = max(diffs)

    report.update(
        interval_s=interval,
        first_epoch=times[0].isoformat(),
        last_epoch=times[-1].isoformat(),
        duration_h=duration / 3600.0,
        gap_ratio=gap_ratio,
        largest_gap_s=largest_gap,
    )
    if n < cfg["min_epochs"]:
        errors.append(f"{n} epochs < minimum {cfg['min_epochs']}")
    if duration / 3600.0 < cfg["min_duration_hours"]:
        errors.append(f"Session {duration / 3600:.2f} h < minimum {cfg['min_duration_hours']} h")
    if gap_ratio > cfg["max_gap_ratio"]:
        errors.append(f"Data gaps: {gap_ratio:.1%} of epochs missing")
    elif largest_gap > 10 * interval:
        warnings.append(f"Largest gap {largest_gap:.0f} s (> 10x interval)")

    return {**report, "passed": not errors, "errors": errors, "warnings": warnings}
