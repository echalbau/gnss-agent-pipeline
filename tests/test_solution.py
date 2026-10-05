import numpy as np
from conftest import write_pos

from gnss_pipeline.geodesy import ecef_to_geodetic
from gnss_pipeline.tools import tuning
from gnss_pipeline.tools.metrics import assess, summarize
from gnss_pipeline.tools.rtklib import parse_pos


def test_parse_pos_signed_covariance(tmp_path):
    sol = parse_pos(write_pos(tmp_path / "s.pos", n=10, sigma_end=0.3))
    assert sol["xyz"].shape == (10, 3)
    c = sol["cov"][-1]
    assert np.isclose(c[0, 1], (0.3 / 3) ** 2, rtol=1e-2)
    assert c[2, 0] < 0  # sdzx negative -> negative covariance


def test_geodetic_roundtrip():
    from math import cos, radians, sin, sqrt

    from gnss_pipeline.geodesy import E2, A

    lat0, lon0, h0 = 40.2033, -8.4103, 99.5
    n = A / sqrt(1 - E2 * sin(radians(lat0)) ** 2)
    x = (n + h0) * cos(radians(lat0)) * cos(radians(lon0))
    y = (n + h0) * cos(radians(lat0)) * sin(radians(lon0))
    z = (n * (1 - E2) + h0) * sin(radians(lat0))
    lat, lon, h = ecef_to_geodetic(x, y, z)
    assert abs(lat - lat0) < 1e-10 and abs(lon - lon0) < 1e-10 and abs(h - h0) < 1e-4


def test_ppp_acceptance(tmp_path, settings):
    cfg = settings["evaluation"]
    good = summarize(parse_pos(write_pos(tmp_path / "g.pos", sigma_end=0.005)), cfg)
    bad = summarize(parse_pos(write_pos(tmp_path / "b.pos", sigma_end=0.2)), cfg)
    assert assess(good, "ppp-static", cfg)[0]
    assert good["converged"] and good["convergence_min"] is not None
    ok, reasons = assess(bad, "ppp-static", cfg)
    assert not ok and any("sigma_h" in r for r in reasons)


def test_rtk_fix_ratio(tmp_path, settings):
    cfg = settings["evaluation"]
    fixed = summarize(parse_pos(write_pos(tmp_path / "f.pos", q=1)), cfg)
    floating = summarize(parse_pos(write_pos(tmp_path / "fl.pos", q=2)), cfg)
    assert assess(fixed, "static", cfg)[0]
    assert not assess(floating, "static", cfg)[0]


def test_tuning_validation_clamps_and_filters():
    out = tuning.validate({"pos1-elmask": 80, "pos2-armode": "magic", "rm -rf": 1,
                           "pos2-arlockcnt": "4.6"})
    assert out == {"pos1-elmask": 30.0, "pos2-arlockcnt": 5}
