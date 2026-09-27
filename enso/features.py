"""Turn the raw series into (features, targets) for each "issue month".

An issue month M is the last month for which all data is in. A forecast made
at M predicts RONI for the 3-month seasons ending at M+1, M+2, ..., M+LEADS.
With data through August, lead 1 is JAS, lead 3 is SON, and lead 11 is MJJ
of next year, the same range as the IRI forecast plume.
"""

import math

import numpy as np

LEADS = 11

FEATURE_NAMES = [
    "RONI now", "RONI 1 mo ago", "RONI 2 mo ago", "RONI 3 mo ago", "RONI 6 mo ago",
    "Niño3.4 now", "Niño3.4 1 mo ago", "Niño3.4 2 mo ago",
    "Niño3 now", "Niño4 now", "Niño1+2 now",
    "Heat 130E-80W", "Heat 160E-80W", "Heat 180W-100W", "Heat change 3 mo",
    "sin(month)", "cos(month)",
    "RONI x sin", "RONI x cos", "Heat x sin", "Heat x cos",
]


def features_at(d, M):
    """Feature vector for issue month M, or None if any input is missing."""
    roni, nino, heat = d["roni"], d["nino"], d["heat"]
    try:
        r = [roni[M - k] for k in (0, 1, 2, 3, 6)]
        n12, n3, n4, n34 = nino[M]
        n34_1, n34_2 = nino[M - 1][3], nino[M - 2][3]
        h = heat[M]
        dh = h[2] - heat[M - 3][2]
    except KeyError:
        return None
    ang = 2 * math.pi * (M % 12) / 12
    s, c = math.sin(ang), math.cos(ang)
    return np.array(r + [n34, n34_1, n34_2, n3, n4, n12] + list(h) + [dh, s, c,
                    r[0] * s, r[0] * c, h[2] * s, h[2] * c])


def targets_at(d, M):
    """RONI for leads 1..LEADS after M (NaN where not observed yet)."""
    return np.array([d["roni"].get(M + k, np.nan) for k in range(1, LEADS + 1)])


def latest_issue_month(d):
    """Most recent month with every input available."""
    M = min(max(d["roni"]), max(d["nino"]), max(d["heat"]))
    while M > 0 and features_at(d, M) is None:
        M -= 1
    return M


def build_dataset(d, first=None, last=None):
    """Arrays X (n, features), Y (n, LEADS) and the issue months they belong to."""
    first = first or min(d["heat"]) + 6
    last = last or latest_issue_month(d)
    months, X, Y = [], [], []
    for M in range(first, last + 1):
        f = features_at(d, M)
        if f is None:
            continue
        months.append(M)
        X.append(f)
        Y.append(targets_at(d, M))
    return np.array(months), np.array(X), np.array(Y)
