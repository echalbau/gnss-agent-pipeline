"""WGS84 ECEF <-> geodetic and ENU covariance propagation."""

from __future__ import annotations

import math

import numpy as np

A = 6378137.0
F = 1.0 / 298.257223563
E2 = F * (2.0 - F)


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Return (lat_deg, lon_deg, h_m)."""
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - E2))
    h = 0.0
    for _ in range(10):
        n = A / math.sqrt(1.0 - E2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1.0 - E2 * n / (n + h)))
    return math.degrees(lat), math.degrees(lon), h


def enu_rotation(lat_deg: float, lon_deg: float) -> np.ndarray:
    sl, cl = math.sin(math.radians(lat_deg)), math.cos(math.radians(lat_deg))
    so, co = math.sin(math.radians(lon_deg)), math.cos(math.radians(lon_deg))
    return np.array([
        [-so, co, 0.0],
        [-sl * co, -sl * so, cl],
        [cl * co, cl * so, sl],
    ])


def cov_ecef_to_enu(cov: np.ndarray, lat_deg: float, lon_deg: float) -> np.ndarray:
    """cov: (..., 3, 3) ECEF covariance -> ENU covariance."""
    r = enu_rotation(lat_deg, lon_deg)
    return np.einsum("ij,...jk,lk->...il", r, cov, r)
