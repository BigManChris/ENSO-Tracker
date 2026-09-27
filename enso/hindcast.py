"""Honest back-testing ("hindcasting").

We pretend to stand at each month since START_YEAR and forecast using only
what was known then: models are retrained every January on data whose
targets had already been observed by that date. That is the only fair way
to measure skill; testing on data the model trained on flatters it.
"""

import numpy as np

from .features import LEADS, build_dataset
from .models import ENSEMBLE_OF, all_models

START_YEAR = 1998
RETRAIN_EVERY_YEARS = 2


def masked_targets(months, Y, cutoff):
    """Hide every target that was not yet observed at issue month `cutoff`."""
    Y = Y.copy()
    for lead in range(Y.shape[1]):
        Y[months + lead + 1 > cutoff, lead] = np.nan
    return Y


def run_hindcast(d, n_nets=10, start_year=START_YEAR, log=print):
    months, X, Y = build_dataset(d)
    names = [m.name for m in all_models(LEADS, n_nets)]
    preds = {n: np.full(Y.shape, np.nan) for n in names}

    last_year = months[-1] // 12
    for year in range(start_year, last_year + 1, RETRAIN_EVERY_YEARS):
        cutoff = year * 12  # January of `year`
        block = (months >= cutoff) & (months < cutoff + 12 * RETRAIN_EVERY_YEARS)
        train = months < cutoff
        if not block.any() or train.sum() < 60:
            continue
        Yt = masked_targets(months[train], Y[train], cutoff)
        for model in all_models(LEADS, n_nets):
            model.fit(X[train], Yt)
            preds[model.name][block] = model.predict(X[block])
        log(f"  hindcast {year}-{year + RETRAIN_EVERY_YEARS - 1} done")

    preds["Ensemble"] = np.nanmean([preds[n] for n in ENSEMBLE_OF], axis=0)
    keep = months >= start_year * 12
    return months[keep], Y[keep], {n: p[keep] for n, p in preds.items()}


def skill(Y, preds):
    """Correlation and RMSE per model per lead, plus a 'climatology' baseline (always 0)."""
    out = {}
    for name, P in list(preds.items()) + [("Climatology", np.zeros_like(Y))]:
        rows = []
        for lead in range(Y.shape[1]):
            ok = ~np.isnan(Y[:, lead]) & ~np.isnan(P[:, lead])
            y, p = Y[ok, lead], P[ok, lead]
            corr = float(np.corrcoef(y, p)[0, 1]) if name != "Climatology" and ok.sum() > 2 else None
            rows.append({"lead": lead + 1, "n": int(ok.sum()),
                         "corr": None if corr is None else round(corr, 3),
                         "rmse": round(float(np.sqrt(np.mean((y - p) ** 2))), 3)})
        out[name] = rows
    return out


def skill_by_start_month(months, Y, P):
    """Correlation for each (calendar month of issue, lead): shows the spring barrier."""
    grid = []
    for cal in range(12):
        row = []
        for lead in range(Y.shape[1]):
            ok = (months % 12 == cal) & ~np.isnan(Y[:, lead]) & ~np.isnan(P[:, lead])
            row.append(round(float(np.corrcoef(Y[ok, lead], P[ok, lead])[0, 1]), 3)
                       if ok.sum() > 4 else None)
        grid.append(row)
    return grid
