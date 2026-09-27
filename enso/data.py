"""Download and parse NOAA's ENSO text files.

Months are stored as plain integers: m = year * 12 + (month - 1). That makes
"three months later" just m + 3 and avoids date arithmetic everywhere.

Sources (all public, all plain text, all updated monthly by NOAA CPC):
  RONI      https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt
            The Relative Oceanic Niño Index. NOAA's official El Niño index
            since February 2026: Niño 3.4 temperature anomaly relative to the
            whole tropics, as 3-month running means (DJF, JFM, ...).
  Niño SSTs https://www.cpc.ncep.noaa.gov/data/indices/ersst5.nino.mth.91-20.ascii
            Monthly sea-surface temperature anomalies in the four Niño boxes.
  Heat      https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ocean/index/heat_content_index.txt
            Average temperature anomaly of the top 300 m of the equatorial
            Pacific. Warm water piles up underground months before El Niño
            reaches the surface, so this is the best early-warning signal.
"""

import urllib.request

RONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt"
NINO_URL = "https://www.cpc.ncep.noaa.gov/data/indices/ersst5.nino.mth.91-20.ascii"
# Same columns, updated on a different schedule; used to fill any months the
# first file hasn't caught up with yet.
NINO_URL_2 = "https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices"
HEAT_URL = ("https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/"
            "ocean/index/heat_content_index.txt")

USER_AGENT = "enso-tracker (student forecasting project; GitHub Actions)"

# Season code -> its middle month (1-12). DJF 1950 is centred on Jan 1950.
SEASONS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ",
           "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
SEASON_CENTRE = {s: i + 1 for i, s in enumerate(SEASONS)}
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def month_index(year, month):
    return year * 12 + (month - 1)


def year_month(m):
    return m // 12, m % 12 + 1


def month_label(m):
    y, mo = year_month(m)
    return f"{y}-{mo:02d}"


def season_ending(m):
    """Name of the 3-month season that ends in month m, e.g. JJA 2026 for Aug 2026.

    The year is the year of the middle month, matching NOAA's convention.
    """
    centre = m - 1
    y, mo = year_month(centre)
    return f"{SEASONS[mo - 1]} {y}"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def _num(s):
    v = float(s)
    return None if abs(v) >= 90 else v  # NOAA uses -99.9 / -999 for missing


def parse_roni(text):
    """{end_month: RONI} from lines like 'JJA  2026  1.36'."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0] not in SEASON_CENTRE:
            continue
        try:
            year, val = int(parts[1]), _num(parts[2])
        except ValueError:
            continue
        if val is None:
            continue
        centre = month_index(year, SEASON_CENTRE[parts[0]])
        out[centre + 1] = val
    return out


def parse_nino(text):
    """{month: (nino12, nino3, nino4, nino34)} anomalies."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 10:
            continue
        try:
            m = month_index(int(parts[0]), int(parts[1]))
            vals = tuple(_num(parts[i]) for i in (3, 5, 7, 9))
        except ValueError:
            continue  # header line
        if None not in vals:
            out[m] = vals
    return out


def parse_heat(text):
    """{month: (130E-80W, 160E-80W, 180W-100W)} upper-300 m temperature anomalies."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            m = month_index(int(parts[0]), int(parts[1]))
            vals = tuple(_num(p) for p in parts[2:5])
        except ValueError:
            continue
        if None not in vals:
            out[m] = vals
    return out


def load_all(fetcher=fetch, log=print):
    nino = parse_nino(fetcher(NINO_URL))
    try:
        extra = parse_nino(fetcher(NINO_URL_2))
    except Exception as e:  # the backup file is optional
        log(f"backup Niño file unavailable: {e}")
        extra = {}
    filled = sorted(m for m in extra if m not in nino and m > max(nino, default=0))
    for m in filled:
        nino[m] = extra[m]
    d = {"roni": parse_roni(fetcher(RONI_URL)), "nino": nino, "heat": parse_heat(fetcher(HEAT_URL))}
    for name, series in d.items():
        log(f"  {name:5s} data runs to {month_label(max(series))}"
            + (f" ({len(filled)} month(s) from sstoi.indices)" if name == "nino" and filled else ""))
    return d
