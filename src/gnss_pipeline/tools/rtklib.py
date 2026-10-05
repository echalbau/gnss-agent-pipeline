"""rnx2rtkp configuration writer, runner and .pos parser."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np


class EngineError(Exception):
    pass


def _signed_sq(s: float) -> float:
    """RTKLIB writes off-diagonal covariances as sign(c) * sqrt(|c|)."""
    return s * abs(s)


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def write_conf(options: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{k:<20}={_fmt(v)}\n" for k, v in options.items()))
    return path


def run_rnx2rtkp(exe: str, conf: str | Path, out_pos: str | Path, inputs: list[str],
                 timeout: float) -> None:
    """inputs: rover obs first, then (base obs), nav, sp3, clk ... as rnx2rtkp expects."""
    binary = shutil.which(exe) or (exe if Path(exe).is_file() else None)
    if binary is None:
        raise EngineError(f"rnx2rtkp not found ('{exe}'); install RTKLIB or set RNX2RTKP")
    cmd = [binary, "-k", str(conf), "-o", str(out_pos), *map(str, inputs)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              check=False)
    except subprocess.TimeoutExpired as exc:
        raise EngineError(f"rnx2rtkp timed out after {timeout} s") from exc
    if proc.returncode != 0:
        raise EngineError(f"rnx2rtkp exit {proc.returncode}: {proc.stderr.strip()[-500:]}")
    if not Path(out_pos).exists() or not parse_pos(out_pos)["q"].size:
        raise EngineError("rnx2rtkp produced no solutions")


def parse_pos(path: str | Path) -> dict[str, np.ndarray]:
    """Parse an RTKLIB .pos file written with out-solformat=xyz.

    Columns: date time x y z Q ns sdx sdy sdz sdxy sdyz sdzx age ratio.
    Off-diagonal sd's are signed square roots: c = sd * |sd|.
    """
    t, xyz, q, ns, cov, ratio = [], [], [], [], [], []
    with open(path) as f:
        for line in f:
            if not line.strip() or line.startswith("%"):
                continue
            p = line.split()
            if len(p) < 13:
                continue
            t.append(np.datetime64(f"{p[0].replace('/', '-')}T{p[1]}"))
            xyz.append([float(v) for v in p[2:5]])
            q.append(int(p[5]))
            ns.append(int(p[6]))
            sx, sy, sz, sxy, syz, szx = (float(v) for v in p[7:13])
            cxy, cyz, czx = _signed_sq(sxy), _signed_sq(syz), _signed_sq(szx)
            cov.append([[sx**2, cxy, czx], [cxy, sy**2, cyz], [czx, cyz, sz**2]])
            ratio.append(float(p[14]) if len(p) > 14 else 0.0)
    return {
        "t": np.array(t, dtype="datetime64[ms]"),
        "xyz": np.array(xyz, dtype=float).reshape(-1, 3),
        "q": np.array(q, dtype=int),
        "ns": np.array(ns, dtype=int),
        "cov": np.array(cov, dtype=float).reshape(-1, 3, 3),
        "ratio": np.array(ratio, dtype=float),
    }
