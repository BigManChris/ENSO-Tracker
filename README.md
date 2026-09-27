# ENSO Tracker

A homemade El Niño forecast that runs itself once a month and keeps an honest public track record.

Every month a GitHub Action downloads NOAA's latest ocean data, forecasts the next 11 seasons of the **Relative Oceanic Niño Index (RONI)**, saves that forecast with its date, and publishes a dashboard on GitHub Pages. Saved forecasts are never edited. As real values come in, each one is scored against what actually happened and against the laziest possible forecast: "nothing changes".

**Dashboard:** https://bigmanchris.github.io/ENSO-Tracker/

## What's being forecast

**RONI** has been NOAA's official El Niño index since February 2026. It's the three-month average of how much warmer the central Pacific (the Niño 3.4 box) is than the tropics as a whole, in °C. Measuring against the rest of the tropics, rather than a fixed 30-year average, stops global warming from slowly pushing the index upward.

| RONI | Label |
|---|---|
| ≥ +0.5 | El Niño (weak < 1.0, moderate < 1.5, strong < 2.0, very strong ≥ 2.0) |
| −0.5 to +0.5 | Neutral |
| ≤ −0.5 | La Niña |

## The data (all free, all from NOAA's Climate Prediction Center)

| File | What it tells the model |
|---|---|
| [`RONI.ascii.txt`](https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt) | The index itself, since 1950 |
| [`ersst5.nino.mth.91-20.ascii`](https://www.cpc.ncep.noaa.gov/data/indices/ersst5.nino.mth.91-20.ascii) | Monthly surface temperature anomalies in the four Niño boxes (east to west) |
| [`heat_content_index.txt`](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ocean/index/heat_content_index.txt) | Temperature of the top 300 m of the equatorial Pacific since 1979. Warm water builds up underground months before El Niño shows at the surface, so this is the main source of skill at long leads. |

## The models

| Model | Idea |
|---|---|
| **Persistence** | "Next season looks like this one." The benchmark to beat, not part of the forecast. |
| **Analog** | Find the 12 past months (same time of year) whose ocean looked most like now and average what happened next. |
| **Ridge** | Regularised linear regression, one per lead, with terms that let the relationships change through the year. |
| **Neural net** | A small scikit-learn MLP (one hidden layer of 16 neurons), 10 copies trained on bootstrap resamples and averaged. With only ~550 training months, anything bigger just memorises history. |

The published forecast is the average of Analog, Ridge and the neural net. The 80% range and the El Niño / La Niña probabilities come from how large the back-tested errors were at each lead.

## Honest back-testing

`enso/hindcast.py` stands at every month since 1998 and forecasts using only what was known then. Models are retrained every two years on data whose outcomes had already been observed, and a test (`test_hindcast_does_not_peek_at_the_future`) checks that changing future data can't change past forecasts. The dashboard shows the resulting skill by lead time, and a heatmap that makes the famous **spring predictability barrier** visible: forecasts that have to cross March–May lose skill fastest.

## Comparing with the professionals

IRI no longer publishes its forecast plume as downloadable data. To put their numbers on your chart, copy the plume average into [`docs/data/official.json`](docs/data/official.json) once a month (it takes about a minute) and push. The dots appear automatically. IRI forecasts the traditional Niño 3.4 index, which runs a little different from RONI, so treat it as a rough comparison.

## Setup (once)

1. Push this repo to GitHub.
2. **Settings → Pages → Source: GitHub Actions**.
3. **Settings → Actions → General → Workflow permissions → Read and write**.
4. **Actions → Monthly ENSO forecast → Run workflow** to make the first forecast now.

After that it checks every morning (06:00 UTC) and only does real work when NOAA has published a new month, usually in the first ten days.

## Running locally

```bash
pip install -r requirements.txt pytest
python -m enso.run --force     # needs internet access to NOAA
pytest                         # uses simulated data, no internet needed
```

## Ideas for version 2

- A CNN on full Pacific temperature maps (Ham et al., *Nature* 2019), pre-trained on climate-model runs to get around the small-data problem.
- Add wind data (westerly wind bursts often trigger El Niño).
- Link to impacts: how RONI forecasts line up with cocoa, coffee or palm-oil prices.

*A student project, not an official forecast.*
