"""Monthly job: python -m enso.run

1. Download the latest NOAA data.
2. If a new month of data is in, back-test every model, train on everything,
   and forecast the next 11 seasons.
3. Save the forecast under docs/data/forecasts/<month>.json. Old forecasts
   are never overwritten: they are the public track record.
4. Score every past forecast against what actually happened.
"""

import argparse
import json
import math
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import data, hindcast
from .features import LEADS, build_dataset, features_at, latest_issue_month
from .models import ENSEMBLE_OF, all_models

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "data"
EL_NINO, LA_NINA = 0.5, -0.5

warnings.filterwarnings("ignore", category=RuntimeWarning)  # nanmean of empty slices
warnings.filterwarnings("ignore", message=".*Stochastic Optimizer.*")  # MLP convergence chatter


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1), encoding="utf-8")


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def r2(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 2)


def normal_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def probabilities(mean, sigma):
    """Chance of La Niña / neutral / El Niño, treating the forecast error as
    normal with the spread measured in the back-test at that lead."""
    p_nino = 1 - normal_cdf((EL_NINO - mean) / sigma)
    p_nina = normal_cdf((LA_NINA - mean) / sigma)
    return {"la_nina": round(p_nina, 3), "neutral": round(1 - p_nino - p_nina, 3),
            "el_nino": round(p_nino, 3)}


def strength(v):
    a = abs(v)
    if a < 0.5:
        return "Neutral"
    kind = "El Niño" if v > 0 else "La Niña"
    label = "weak" if a < 1 else "moderate" if a < 1.5 else "strong" if a < 2 else "very strong"
    return f"{label.capitalize()} {kind}"


def make_forecast(d, M, sigma, n_nets):
    months, X, Y = build_dataset(d, last=M)
    Y = hindcast.masked_targets(months, Y, M)
    x_now = features_at(d, M)[None, :]
    per_model = {}
    for model in all_models(LEADS, n_nets):
        model.fit(X, Y)
        per_model[model.name] = model.predict(x_now)[0]
    ens = np.nanmean([per_model[n] for n in ENSEMBLE_OF], axis=0)
    seasons = [data.season_ending(M + k) for k in range(1, LEADS + 1)]
    return {
        "issued": data.month_label(M),
        "data_through": f"{data.MONTH_NAMES[M % 12]} {M // 12}",
        "made_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "latest_observed": {"season": data.season_ending(M), "roni": d["roni"][M]},
        "seasons": seasons,
        "ensemble": [r2(v) for v in ens],
        "sigma": [r2(s) for s in sigma],
        "models": {k: [r2(v) for v in vals] for k, vals in per_model.items()},
        "probabilities": [probabilities(m, s) for m, s in zip(ens, sigma)],
        "category": [strength(v) for v in ens],
    }


def scorecard(d, forecasts):
    """Every past live forecast next to what was later observed."""
    rows = []
    for f in forecasts:
        M = data.month_index(*map(int, f["issued"].split("-")))
        for k, season in enumerate(f["seasons"], start=1):
            obs = d["roni"].get(M + k)
            if obs is None:
                continue
            rows.append({"issued": f["issued"], "lead": k, "season": season,
                         "forecast": f["ensemble"][k - 1],
                         "persistence": f["models"]["Persistence"][k - 1],
                         "observed": obs})
    n = len(rows)
    summary = None
    if n:
        mae = sum(abs(r["forecast"] - r["observed"]) for r in rows) / n
        mae_p = sum(abs(r["persistence"] - r["observed"]) for r in rows) / n
        summary = {"n": n, "mae": round(mae, 3), "mae_persistence": round(mae_p, 3)}
    return {"summary": summary, "rows": rows}


def truncate(d, M):
    """The data as it stood at the end of month M: everything later is removed."""
    return {name: {m: v for m, v in series.items() if m <= M} for name, series in d.items()}


def backtest_and_forecast(d, M, n_nets):
    """Back-test on data up to M (for the error bars), then forecast from M."""
    print(f"back-testing with data through {data.month_label(M)} (a couple of minutes)...")
    hm, hY, hP = hindcast.run_hindcast(d, n_nets=n_nets)
    sk = hindcast.skill(hY, hP)
    sigma = [row["rmse"] for row in sk["Ensemble"]]
    skill_json = {
        "period": f"{data.month_label(hm[0])} to {data.month_label(hm[-1])}",
        "by_model": sk,
        "barrier": hindcast.skill_by_start_month(hm, hY, hP["Ensemble"]),
        "month_names": data.MONTH_NAMES,
    }
    return make_forecast(d, M, sigma, n_nets), skill_json


def replay(full, label, docs, n_nets):
    """Pretend it's the end of month `label`: forecast using only data up to
    then, and compare with what actually happened afterwards."""
    M = data.month_index(*map(int, label.split("-")))
    d = truncate(full, M)
    M = latest_issue_month(d)  # in case one file was missing that month
    fc, _ = backtest_and_forecast(d, M, n_nets)
    fc["replay"] = True
    fc["made_at"] = "replay"
    fc["observed"] = [full["roni"].get(M + k) for k in range(1, LEADS + 1)]
    rows = [(f, o, p) for f, o, p in zip(fc["ensemble"], fc["observed"], fc["models"]["Persistence"])
            if o is not None]
    if rows:
        fc["summary"] = {
            "n": len(rows),
            "mae": round(sum(abs(f - o) for f, o, _ in rows) / len(rows), 3),
            "mae_persistence": round(sum(abs(p - o) for _, o, p in rows) / len(rows), 3),
            "max_error": round(max(abs(f - o) for f, o, _ in rows), 3),
        }
    out = docs / "replays" / f"{data.month_label(M)}.json"
    save(out, fc)
    save(docs / "replays" / "index.json",
         sorted(p.stem for p in (docs / "replays").glob("*.json") if p.stem != "index"))
    for s, f, o in zip(fc["seasons"], fc["ensemble"], fc["observed"]):
        print(f"  {s}: forecast {f:+.2f}  observed {'   -  ' if o is None else f'{o:+.2f}'}")
    if rows:
        print(f"  average error {fc['summary']['mae']:.2f} vs {fc['summary']['mae_persistence']:.2f} for 'no change'")


def main(argv=None, fetcher=data.fetch, docs=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-run even if nothing new")
    ap.add_argument("--nets", type=int, default=10, help="neural nets per bag")
    ap.add_argument("--as-of", nargs="+", metavar="YYYY-MM",
                    help="replay mode: forecast as if it were the end of these months "
                         "and compare with what happened next")
    args = ap.parse_args(argv)
    docs = docs or DOCS

    d = data.load_all(fetcher)
    if args.as_of:
        for label in args.as_of:
            replay(d, label, docs, args.nets)
        return True
    M = latest_issue_month(d)
    label = data.month_label(M)
    state = load(docs / "state.json", {})
    print(f"latest complete month: {label} ({data.season_ending(M)} RONI = {d['roni'][M]})")

    if state.get("issued") == label and not args.force:
        print("no new data, nothing to do")
        return False

    fc, skill_json = backtest_and_forecast(d, M, args.nets)
    save(docs / "skill.json", skill_json)
    archive = docs / "forecasts" / f"{label}.json"
    if not archive.exists():  # the first forecast for a month is the one that counts
        save(archive, fc)
    save(docs / "latest.json", fc)

    past = [load(p, None) for p in sorted((docs / "forecasts").glob("*.json"))]
    past = [p for p in past if p]
    save(docs / "scorecard.json", scorecard(d, past))
    save(docs / "index.json", [p["issued"] for p in past])

    start = M - 12 * 6
    save(docs / "observed.json", [
        {"end": data.month_label(m), "season": data.season_ending(m), "roni": v}
        for m, v in sorted(d["roni"].items()) if m >= start])

    state["issued"] = label
    save(docs / "state.json", state)
    print("forecast:", ", ".join(f"{s} {v:+.2f}" for s, v in zip(fc["seasons"], fc["ensemble"])))
    return True


if __name__ == "__main__":
    main()
