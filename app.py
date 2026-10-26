"""Real Exchange Rate Explorer — Streamlit app using IMF SDMX 3.0 data.

Definitions
-----------
S(t)   = units of Country 2 currency per 1 unit of Country 1 currency
P1, P2 = monthly CPI of Country 1 and Country 2
RER(t) = S(t) * P1(t) / P2(t)
RER*   = average of RER(t) over valid months in the selected sample
Real Index(t) = 100 * RER(t) / RER*

IMF exchange rates (XDC_USD) are local-currency units per USD, so
S(t) = (LCU2 per USD) / (LCU1 per USD).
"""

from __future__ import annotations

import io

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "https://api.imf.org/external/sdmx/3.0"
CSV_HEADERS = {"Accept": "application/vnd.sdmx.data+csv;version=2.0.0"}
JSON_HEADERS = {"Accept": "application/json"}
START_MONTH = pd.Timestamp("1976-01-01")
EURO_AREA = "G163"
TIMEOUT = 60

# Euro-area members whose IMF national exchange-rate series stop when they
# adopted the euro (legacy currency per USD).
EURO_MEMBERS = {
    "AUT", "BEL", "CYP", "DEU", "ESP", "EST", "FIN", "FRA", "GRC", "HRV",
    "IRL", "ITA", "LTU", "LUX", "LVA", "MLT", "NLD", "PRT", "SVK", "SVN",
}

st.set_page_config(page_title="Real Exchange Rate Explorer", layout="wide")


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------
def _get_csv(url: str, params: dict | None = None) -> pd.DataFrame:
    """GET an SDMX-CSV response and return it as a DataFrame (empty if none)."""
    resp = requests.get(url, headers=CSV_HEADERS, params=params, timeout=TIMEOUT)
    if resp.status_code == 404:
        return pd.DataFrame()
    resp.raise_for_status()
    text = resp.text.strip()
    if not text:
        return pd.DataFrame()
    return pd.read_csv(io.StringIO(text))


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def country_names() -> dict[str, str]:
    """ISO3 / IMF code -> country name, from the IMF CL_COUNTRY codelist."""
    url = f"{BASE_URL}/structure/codelist/IMF/CL_COUNTRY/+"
    resp = requests.get(url, headers=JSON_HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    codes = resp.json()["data"]["codelists"][0]["codes"]
    return {c["id"]: c.get("name", c["id"]) for c in codes}


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def countries_with_series(dataflow: str, key_suffix: str) -> set[str]:
    """Country codes that have a given series (series keys only, no data)."""
    url = f"{BASE_URL}/data/dataflow/IMF.STA/{dataflow}/+/*.{key_suffix}"
    df = _get_csv(url, params={"attributes": "none", "measures": "none"})
    if df.empty or "COUNTRY" not in df.columns:
        return set()
    return set(df["COUNTRY"].dropna().astype(str))


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def available_countries() -> list[tuple[str, str]]:
    """Countries with both a monthly CPI and a monthly USD exchange rate."""
    er = countries_with_series("ER", "XDC_USD.PA_RT.M")
    cpi = countries_with_series("CPI", "CPI._T.IX.M")
    cpi |= {EURO_AREA}  # Euro area CPI is published as HICP
    names = country_names()
    codes = sorted(er & cpi)
    out = [(c, names.get(c, c)) for c in codes]
    return sorted(out, key=lambda x: (x[0] != EURO_AREA, x[1]))


def _parse_period(p: pd.Series) -> pd.Series:
    """'1976-M01' -> Timestamp('1976-01-01')."""
    return pd.to_datetime(p.astype(str).str.replace("-M", "-", regex=False), format="%Y-%m")


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def fetch_series(dataflow: str, key: str) -> pd.Series:
    """Fetch one monthly IMF series as a float Series indexed by month start."""
    url = f"{BASE_URL}/data/dataflow/IMF.STA/{dataflow}/+/{key}"
    df = _get_csv(url)
    if df.empty or "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
        return pd.Series(dtype=float)
    df = df.dropna(subset=["TIME_PERIOD"])
    s = pd.Series(
        pd.to_numeric(df["OBS_VALUE"], errors="coerce").values,
        index=_parse_period(df["TIME_PERIOD"]),
    )
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s[s.index >= START_MONTH].dropna()


def fetch_cpi(code: str) -> tuple[pd.Series, str]:
    """CPI for a country; falls back to HICP (needed for the Euro area)."""
    for index_type in ("CPI", "HICP"):
        s = fetch_series("CPI", f"{code}.{index_type}._T.IX.M")
        if not s.empty:
            return s, index_type
    return pd.Series(dtype=float), "none"


def fetch_fx(code: str) -> pd.Series:
    """Local-currency units per USD, monthly period average."""
    return fetch_series("ER", f"{code}.XDC_USD.PA_RT.M")


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------
def build_frame(c1: str, c2: str) -> tuple[pd.DataFrame, dict]:
    p1, t1 = fetch_cpi(c1)
    p2, t2 = fetch_cpi(c2)
    e1 = fetch_fx(c1)
    e2 = fetch_fx(c2)
    df = pd.concat(
        {"P1": p1, "P2": p2, "LCU1_per_USD": e1, "LCU2_per_USD": e2}, axis=1
    ).sort_index()
    # S(t): units of Country 2 currency per 1 unit of Country 1 currency
    df["S"] = df["LCU2_per_USD"] / df["LCU1_per_USD"]
    df["RER"] = df["S"] * df["P1"] / df["P2"]
    meta = {"cpi_type_1": t1, "cpi_type_2": t2,
            "n_p1": len(p1), "n_p2": len(p2), "n_e1": len(e1), "n_e2": len(e2)}
    return df, meta


def month_label(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("Real Exchange Rate Explorer")
st.caption(
    "Source: IMF SDMX 3.0 API — monthly CPI (IMF.STA/CPI) and exchange rates "
    "(IMF.STA/ER, period average, local currency per USD)."
)

try:
    with st.spinner("Loading IMF country list…"):
        countries = available_countries()
except Exception as exc:  # network / API errors
    st.error(f"Could not load the IMF country list: {exc}")
    st.stop()

if not countries:
    st.error("The IMF API returned no countries. Try again later.")
    st.stop()

labels = {code: f"{name} ({code})" for code, name in countries}
codes = [c for c, _ in countries]

with st.sidebar:
    st.header("Settings")
    default1 = codes.index("USA") if "USA" in codes else 0
    default2 = codes.index(EURO_AREA) if EURO_AREA in codes else min(1, len(codes) - 1)
    c1 = st.selectbox("Country 1", codes, index=default1, format_func=labels.get)
    c2 = st.selectbox("Country 2", codes, index=default2, format_func=labels.get)
    view = st.radio("Chart", ["Real", "Nominal", "Both"], index=2, horizontal=True)

if c1 == c2:
    st.warning("Choose two different countries.")
    st.stop()

try:
    with st.spinner("Fetching IMF data…"):
        df, meta = build_frame(c1, c2)
except Exception as exc:
    st.error(f"Could not fetch IMF data: {exc}")
    st.stop()

n1, n2 = labels[c1], labels[c2]

# Data-coverage diagnostics
missing = []
if meta["n_p1"] == 0:
    missing.append(f"CPI for {n1}")
if meta["n_p2"] == 0:
    missing.append(f"CPI for {n2}")
if meta["n_e1"] == 0:
    missing.append(f"exchange rate for {n1}")
if meta["n_e2"] == 0:
    missing.append(f"exchange rate for {n2}")
if missing:
    st.error("The IMF has no monthly data for: " + "; ".join(missing) + ".")
    st.stop()

valid = df.dropna(subset=["RER"])
if valid.empty:
    st.error("No months where both CPIs and both exchange rates are available.")
    st.stop()

euro_legacy = [labels[c] for c in (c1, c2) if c in EURO_MEMBERS]
if euro_legacy:
    st.info(
        "Note: IMF national exchange rates for euro-area members are in the "
        "legacy currency and end when the country adopted the euro. For later "
        f"periods, use Euro Area (G163). Affected: {', '.join(euro_legacy)}."
    )
for code, t in ((c1, meta["cpi_type_1"]), (c2, meta["cpi_type_2"])):
    if t == "HICP":
        st.caption(f"{labels[code]}: price index is the HICP (harmonised CPI).")

# Sample period selector over months with complete data
months = list(valid.index)
with st.sidebar:
    start, end = st.select_slider(
        "Sample period",
        options=months,
        value=(months[0], months[-1]),
        format_func=month_label,
    )
    st.caption(
        f"Data with all four series available: {month_label(months[0])} to "
        f"{month_label(months[-1])} ({len(months)} months)."
    )

sample = df.loc[start:end].copy()
sample_valid = sample.dropna(subset=["RER"])
rer_star = sample_valid["RER"].mean()
sample["RER_star"] = rer_star
sample["Real_Index"] = 100 * sample["RER"] / rer_star

gaps = len(sample) - len(sample_valid)

# Headline metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Valid months in sample", f"{len(sample_valid)}")
m2.metric("RER* (sample mean)", f"{rer_star:,.6g}")
latest = sample_valid.iloc[-1]
m3.metric(f"Real Index ({month_label(sample_valid.index[-1])})",
          f"{100 * latest['RER'] / rer_star:,.1f}")
m4.metric(f"S ({month_label(sample_valid.index[-1])})", f"{latest['S']:,.6g}")
if gaps:
    st.caption(f"{gaps} month(s) in the range have missing data and are excluded from RER*.")

st.markdown(
    f"**S(t)** = {n2} currency per 1 unit of {n1} currency.  "
    f"**RER(t)** = S(t) × P1(t) / P2(t).  "
    f"**Real Index** = 100 × RER(t) / RER*.  "
    "A rise in the Real Index is a real appreciation of Country 1's currency."
)

# Chart
real_trace = go.Scatter(x=sample.index, y=sample["Real_Index"], name="Real Index (RER*=100)",
                        mode="lines", connectgaps=False, line=dict(color="#1f77b4"))
nom_trace = go.Scatter(x=sample.index, y=sample["S"], name=f"Nominal S ({c2} per {c1})",
                       mode="lines", connectgaps=False, line=dict(color="#d62728"))

if view == "Both":
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(real_trace, secondary_y=False)
    fig.add_trace(nom_trace, secondary_y=True)
    fig.update_yaxes(title_text="Real Index (RER* = 100)", secondary_y=False)
    fig.update_yaxes(title_text=f"S: {c2} currency per {c1} currency", secondary_y=True)
    fig.add_hline(y=100, line_dash="dot", line_color="gray")
elif view == "Real":
    fig = go.Figure(real_trace)
    fig.update_yaxes(title_text="Real Index (RER* = 100)")
    fig.add_hline(y=100, line_dash="dot", line_color="gray")
else:
    fig = go.Figure(nom_trace)
    fig.update_yaxes(title_text=f"S: {c2} currency per {c1} currency")

fig.update_layout(
    title=f"{n1} vs {n2}: {month_label(start)} to {month_label(end)}",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    height=520,
    margin=dict(t=80),
)
fig.update_xaxes(title_text="Month")
st.plotly_chart(fig, width="stretch")

# Table + CSV download
out = sample.rename_axis("month").reset_index()
out["month"] = out["month"].dt.strftime("%Y-%m")
out = out[["month", "LCU1_per_USD", "LCU2_per_USD", "S", "P1", "P2", "RER", "RER_star", "Real_Index"]]
out.columns = [
    "month",
    f"{c1}_currency_per_USD",
    f"{c2}_currency_per_USD",
    f"S_{c2}_per_{c1}",
    f"P1_CPI_{c1}",
    f"P2_CPI_{c2}",
    "RER",
    "RER_star",
    "Real_Index",
]

st.download_button(
    "Download CSV (selected sample)",
    data=out.to_csv(index=False).encode("utf-8"),
    file_name=f"rer_{c1}_{c2}_{month_label(start)}_{month_label(end)}.csv",
    mime="text/csv",
)

with st.expander("Show data table"):
    st.dataframe(out, width="stretch", hide_index=True)
