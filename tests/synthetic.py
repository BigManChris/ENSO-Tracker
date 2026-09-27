"""Fake-but-plausible ENSO data for tests (a noisy 'recharge oscillator').

Surface temperature T and subsurface heat h chase each other round a cycle
of a few years, the way real El Niño does, so the models have something
learnable. Output is formatted exactly like NOAA's text files.
"""

import numpy as np

from enso.data import SEASONS, month_index, year_month


def simulate(first_year=1950, last=(2026, 8), seed=1):
    rng = np.random.default_rng(seed)
    n = month_index(*last) - month_index(first_year, 1) + 1
    T, h = np.zeros(n), np.zeros(n)
    for t in range(1, n):
        season = 1 + 0.4 * np.cos(2 * np.pi * ((t % 12) - 11) / 12)  # peaks in winter
        T[t] = T[t - 1] + 0.12 * h[t - 1] - 0.03 * T[t - 1] * season + rng.normal(0, 0.18)
        h[t] = h[t - 1] - 0.12 * T[t - 1] - 0.01 * h[t - 1] + rng.normal(0, 0.10)
    return T, h, month_index(first_year, 1)


def as_noaa_text(T, h, m0, heat_from=1979):
    roni = ["SEAS   YR  ANOM"]
    nino = [" YR   MON  NINO1+2  ANOM   NINO3    ANOM   NINO4    ANOM   NINO3.4  ANOM"]
    heat = ["Equtorial Upper 300m temperature Average anomaly", "YR    MON   130E-80W   160E-80W   180W-100W"]
    for i in range(len(T)):
        y, mo = year_month(m0 + i)
        a34 = T[i]
        nino.append(f"{y} {mo:3d}   24.00 {a34 * 1.3:7.2f}   25.00 {a34 * 1.1:7.2f}   "
                    f"28.00 {a34 * 0.6:7.2f}   26.00 {a34:7.2f}")
        if y >= heat_from:
            heat.append(f"{y} {mo:5d} {h[i] * 0.8:9.2f} {h[i]:9.2f} {h[i] * 1.1:9.2f}")
        if 1 <= i < len(T) - 1:  # season centred on month i
            roni.append(f"{SEASONS[mo - 1]}  {y} {np.mean(T[i - 1:i + 2]):5.2f}")
    return "\n".join(roni), "\n".join(nino), "\n".join(heat)


def fake_fetcher(last=(2026, 8), seed=1):
    from enso import data
    T, h, m0 = simulate(last=last, seed=seed)
    roni, nino, heat = as_noaa_text(T, h, m0)
    files = {data.RONI_URL: roni, data.NINO_URL: nino, data.HEAT_URL: heat, data.NINO_URL_2: ""}
    return lambda url: files[url]
