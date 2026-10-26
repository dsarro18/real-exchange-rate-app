# Real Exchange Rate App

A Streamlit app that computes and plots the bilateral real exchange rate between any two IMF countries (or the Euro Area) using monthly IMF CPI and exchange-rate data from January 1976 where available.

**Live app:** https://dsarro18-real-exchange-rate-app-app-qbnaei.streamlit.app/

## Economics

| Symbol | Definition |
|---|---|
| S(t) | Units of Country 2 currency per 1 unit of Country 1 currency |
| P1(t), P2(t) | Monthly CPI of Country 1 and Country 2 |
| RER(t) | S(t) × P1(t) / P2(t) |
| RER* | Average of RER(t) over valid months in the selected sample |
| Real Index(t) | 100 × RER(t) / RER* |

IMF exchange rates are local-currency units per USD, so the app converts them:
S(t) = (Country 2 currency per USD) / (Country 1 currency per USD).

A rising Real Index means Country 1's currency has appreciated in real terms against Country 2's. RER* is recalculated whenever the sample period changes. Nominal S(t) is plotted in actual currency units, not normalized.

## Features

- Choose Country 1 and Country 2 from all IMF countries with monthly CPI and exchange-rate data, plus the Euro Area (G163)
- Choose the start and end months of the sample
- Chart Real, Nominal, or Both (Both uses separate y-axes)
- Download a CSV of all observations and calculations in the selected sample

## Data

IMF SDMX 3.0 API: `https://api.imf.org/external/sdmx/3.0`

- CPI: dataflow `IMF.STA/CPI`, key `{ISO3}.CPI._T.IX.M`
- Exchange rate: dataflow `IMF.STA/ER`, key `{ISO3}.XDC_USD.PA_RT.M` (period average)
- Euro Area code: `G163`. The IMF publishes Euro Area prices as the HICP, so the app falls back to `G163.HICP._T.IX.M`; this series begins in December 1999.

Data limitations:
- Coverage differs by country; only months where both CPIs and both exchange rates exist are used for RER*.
- National exchange rates for euro-area members (e.g. ITA, DEU, FRA) are in the legacy currency and stop when the country joined the euro. Use Euro Area (G163) for later periods.

## Files

- `app.py` — the Streamlit app
- `requirements.txt` — Python dependencies (Python 3.12)
- `README.md` — this file

## Run locally (optional)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

On share.streamlit.io: Create app → select this repository, branch `main`, file `app.py`; under Advanced settings choose Python 3.12.

## LLM disclosure

Code written by Claude (Anthropic), model Claude Opus 5.5, on October 25, 2026. Prompt: _paste your prompt here_.
