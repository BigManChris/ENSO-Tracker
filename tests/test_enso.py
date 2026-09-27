import json

import numpy as np
import pytest

from enso import data, features, hindcast, run
from synthetic import fake_fetcher

# Snippets copied from the real NOAA files, so format changes get caught.
RONI_TXT = """SEAS   YR  ANOM
DJF  1950 -1.19
JFM  1950 -1.08
NDJ  2025 -0.40
JJA  2026  1.36
"""
NINO_TXT = """ YR   MON  NINO1+2  ANOM   NINO3    ANOM   NINO4    ANOM   NINO3.4  ANOM
1950   1   23.01   -1.55   23.56   -2.10   26.94   -1.38   24.55   -1.99
1950   2   24.32   -1.78   24.89   -1.52   26.67   -1.53   25.06   -1.69
"""
HEAT_TXT = """Equtorial Upper 300m temperature Average anomaly based on 1981-2010 Climatology (deg C)
YR    MON   130E-80W   160E-80W   180W-100W
1979    1      .56       .49        .39
2026    8     2.19      2.77       3.23
"""


def test_parse_roni_indexes_by_season_end_month():
    r = data.parse_roni(RONI_TXT)
    assert r[data.month_index(1950, 2)] == -1.19          # DJF 1950 ends Feb 1950
    assert r[data.month_index(2026, 1)] == -0.40          # NDJ 2025 ends Jan 2026
    assert r[data.month_index(2026, 8)] == 1.36
    assert data.season_ending(data.month_index(2026, 8)) == "JJA 2026"
    assert data.season_ending(data.month_index(2026, 1)) == "NDJ 2025"


def test_parse_nino_and_heat():
    n = data.parse_nino(NINO_TXT)
    assert n[data.month_index(1950, 1)] == (-1.55, -2.10, -1.38, -1.99)
    h = data.parse_heat(HEAT_TXT)
    assert h[data.month_index(1979, 1)] == (0.56, 0.49, 0.39)
    assert h[data.month_index(2026, 8)] == (2.19, 2.77, 3.23)


def test_masked_targets_hides_the_future():
    months = np.array([100, 105, 110])
    Y = np.ones((3, 3))
    m = hindcast.masked_targets(months, Y, cutoff=108)
    # month 105: leads 1-3 end at 106, 107, 108 -> all known; month 110: nothing known yet
    assert not np.isnan(m[:2]).any() and np.isnan(m[2]).all()
    assert np.isnan(hindcast.masked_targets(months, Y, cutoff=107)[1, 2])  # 108 not yet seen


def test_hindcast_does_not_peek_at_the_future(monkeypatch):
    """Changing data after 2010 must not change back-tests made in 2008-2009."""
    monkeypatch.setattr(hindcast, "RETRAIN_EVERY_YEARS", 2)
    d = data.load_all(fake_fetcher())
    m1, _, p1 = hindcast.run_hindcast(d, n_nets=1, start_year=2008, log=lambda *a: None)
    cut = data.month_index(2010, 1)
    d2 = {k: dict(v) for k, v in d.items()}
    for m in d2["roni"]:
        if m >= cut:
            d2["roni"][m] += 3.0
    _, _, p2 = hindcast.run_hindcast(d2, n_nets=1, start_year=2008, log=lambda *a: None)
    early = m1 < cut
    for name in p1:
        np.testing.assert_allclose(p1[name][early], p2[name][early])


def test_probabilities_sum_to_one():
    p = run.probabilities(1.2, 0.4)
    assert abs(sum(p.values()) - 1) < 1e-6 and p["el_nino"] > 0.9


def test_full_run_writes_dashboard_files(tmp_path, monkeypatch):
    monkeypatch.setattr(hindcast, "RETRAIN_EVERY_YEARS", 10)
    assert run.main(["--nets", "1"], fetcher=fake_fetcher(last=(2026, 7)), docs=tmp_path)
    assert not run.main(["--nets", "1"], fetcher=fake_fetcher(last=(2026, 7)), docs=tmp_path)  # nothing new
    assert run.main(["--nets", "1"], fetcher=fake_fetcher(last=(2026, 8)), docs=tmp_path)

    fc = json.loads((tmp_path / "latest.json").read_text())
    assert fc["issued"] == "2026-08" and fc["seasons"][0] == "JAS 2026" and len(fc["ensemble"]) == 11
    assert set(fc["models"]) == {"Persistence", "Analog", "Ridge", "Neural net"}
    assert sorted(p.name for p in (tmp_path / "forecasts").iterdir()) == ["2026-07.json", "2026-08.json"]
    score = json.loads((tmp_path / "scorecard.json").read_text())
    assert score["rows"][0]["issued"] == "2026-07" and score["rows"][0]["season"] == "JJA 2026"
    skill = json.loads((tmp_path / "skill.json").read_text())
    assert len(skill["barrier"]) == 12
