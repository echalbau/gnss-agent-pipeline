from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from gnss_pipeline.config import load_settings


def _h(content: str, label: str) -> str:
    return f"{content:<60}{label}\n"


def write_rinex3(path: Path, *, hours: float = 2.0, interval: float = 30.0,
                 gap: tuple[int, int] | None = None, dual: bool = True) -> Path:
    types = "C1C L1C C2W L2W" if dual else "C1C L1C"
    n_types = len(types.split())
    lines = [
        _h("     3.04           OBSERVATION DATA    M", "RINEX VERSION / TYPE"),
        _h("TEST", "MARKER NAME"),
        _h(f"{'1':<20}{'SEPT POLARX5':<20}{'5.4':<20}", "REC # / TYPE / VERS"),
        _h(f"{'1':<20}{'LEIAR25.R4      LEIT':<20}", "ANT # / TYPE"),
        _h("  4919393.5000   -29351.8000  4050045.1000", "APPROX POSITION XYZ"),
        _h(f"G  {n_types:3d} {types}", "SYS / # / OBS TYPES"),
        _h(f"{interval:10.3f}", "INTERVAL"),
        _h("  2024     1    15     0     0    0.0000000     GPS", "TIME OF FIRST OBS"),
        _h("", "END OF HEADER"),
    ]
    t0 = datetime(2024, 1, 15)
    n = int(hours * 3600 / interval) + 1
    for i in range(n):
        if gap and gap[0] <= i < gap[1]:
            continue
        t = t0 + timedelta(seconds=i * interval)
        lines.append(f"> {t:%Y %m %d %H %M} {t.second + t.microsecond / 1e6:10.7f}  0  1\n")
        lines.append("G01" + "  23619095.450  " * n_types + "\n")
    path.write_text("".join(lines))
    return path


def write_pos(path: Path, *, n: int = 240, sigma_end: float = 0.01, q: int = 6) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = datetime(2024, 1, 15)
    rows = ["% program : fake\n",
            "%  GPST   x-ecef(m) y-ecef(m) z-ecef(m) Q ns sdx sdy sdz sdxy sdyz sdzx age ratio\n"]
    for i, s in enumerate(np.geomspace(1.0, sigma_end, n)):
        t = t0 + timedelta(seconds=30 * i)
        rows.append(
            f"{t:%Y/%m/%d %H:%M:%S}.000  4919393.5000  -29351.8000  4050045.1000"
            f"  {q} 10 {s:8.4f} {s:8.4f} {s:8.4f} {s/3:8.4f} {s/4:8.4f} {-s/5:8.4f}   0.00    0.0\n"
        )
    path.write_text("".join(rows))
    return path


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = load_settings()
    s["paths"]["work_root"] = str(tmp_path / "jobs")
    s["paths"]["product_cache"] = str(tmp_path / "products")
    return s
