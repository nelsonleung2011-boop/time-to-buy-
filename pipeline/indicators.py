#!/usr/bin/env python3
"""Build the seven observable dimensions from cached market data.

Point-in-time rule: every value used at date D is the latest observation ON OR
BEFORE D. A series that did not exist at D reports NO DATA — it is never
back-filled with an invented number. Thresholds live in ``config.py`` and are
published with the payload.

Limitation (disclosed in the dashboard): FRED and multpl serve LATEST REVISED
vintages rather than real-time vintages, and macro observations are aligned to
their nominal observation date. This is a current-state condition detector, not
a backtested return-forecast model, so no predictive claim rests on the history.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from pipeline import config as C

T = C.THRESHOLDS

STATE_CN = {
    "EASING": "缓和", "WIDENING": "走阔", "ELEVATED": "偏高", "STABLE": "平稳",
    "PRESSURE": "压力", "PANIC": "恐慌", "STRESS": "承压", "CALM": "平静",
    "FEAR": "恐惧", "NEUTRAL": "中性", "COMPLACENT": "乐观", "WEAK": "偏弱",
    "HEALTHY": "健康", "CONFIRMED": "确认", "RECOVERING": "修复", "BEAR": "熊市",
    "CHEAP": "便宜", "FAIR": "合理", "EXPENSIVE": "昂贵", "NO DATA": "无数据",
}

TONE = {
    "EASING": "good", "CALM": "good", "HEALTHY": "good", "CONFIRMED": "good",
    "CHEAP": "good", "RECOVERING": "good",
    "WIDENING": "bad", "PANIC": "bad", "BEAR": "bad", "EXPENSIVE": "warn",
    "PRESSURE": "warn", "ELEVATED": "warn", "FEAR": "warn", "WEAK": "warn",
    "STRESS": "warn", "COMPLACENT": "warn",
    "STABLE": "neutral", "NEUTRAL": "neutral", "FAIR": "neutral",
    "NO DATA": "nodata",
}


def read_price(key: str) -> pd.Series:
    p = C.RAW / f"{key}.csv"
    if not p.exists():
        return pd.Series(dtype=float)
    d = pd.read_csv(p)
    if "date" not in d or "close" not in d:
        return pd.Series(dtype=float)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).set_index("date").sort_index()
    s = pd.to_numeric(d["close"], errors="coerce").dropna()
    return s[~s.index.duplicated(keep="last")]


def read_observations(key: str) -> pd.Series:
    if not C.OBSERVATIONS.exists():
        return pd.Series(dtype=float)
    obj = json.loads(C.OBSERVATIONS.read_text(encoding="utf-8"))
    rows = obj.get(key, [])
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([r["date"] for r in rows], errors="coerce")
    val = pd.to_numeric([r.get("value") for r in rows], errors="coerce")
    s = pd.Series(val, index=idx).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def build_series() -> dict[str, pd.Series]:
    S: dict[str, pd.Series] = {}
    for key in C.PRICE_SYMBOLS:
        S[key] = read_price(key)

    # --- derived price series ---------------------------------------------
    vix, vix9d = S["VIX"], S["VIX9D"]
    S["vix_term"] = ((vix9d / vix - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
                     if len(vix) and len(vix9d) else pd.Series(dtype=float))

    sector_frames = {}
    for sec in C.SECTORS:
        px = S.get(sec, pd.Series(dtype=float))
        if len(px) < 60:
            continue
        ma50 = px.rolling(50, min_periods=50).mean()
        sector_frames[sec] = (px > ma50).astype(float).where(ma50.notna())
    if sector_frames:
        S["breadth"] = (pd.DataFrame(sector_frames).mean(axis=1) * 100.0).dropna()
        S["n_sectors_used"] = len(sector_frames)
    else:
        S["n_sectors_used"] = 0
        S["breadth"] = pd.Series(dtype=float)

    spy = S["SPY"]
    if len(spy):
        S["spy_ma50"] = spy.rolling(50, min_periods=50).mean()
        S["spy_ma200"] = spy.rolling(200, min_periods=200).mean()
        S["spy_r20"] = (spy / spy.shift(20) - 1.0) * 100.0
        S["ma50_slope20"] = (S["spy_ma50"] / S["spy_ma50"].shift(20) - 1.0) * 100.0
    else:
        for k in ("spy_ma50", "spy_ma200", "spy_r20", "ma50_slope20"):
            S[k] = pd.Series(dtype=float)

    hyg, lqd = S["HYG"], S["LQD"]
    S["credit_proxy"] = ((hyg / lqd).replace([np.inf, -np.inf], np.nan).dropna()
                         if len(hyg) and len(lqd) else pd.Series(dtype=float))

    # --- macro observations ------------------------------------------------
    for key in list(C.FRED_SERIES) + ["FNG", "CAPE"]:
        S[key] = read_observations(key)
    return S


def at(s: pd.Series | None, date: pd.Timestamp, window: int = 0) -> tuple[float | None, float | None]:
    """Latest value at/before `date`, plus its change over `window` rows."""
    if s is None or len(s) == 0:
        return None, None
    sub = s.loc[s.index <= date]
    if len(sub) == 0:
        return None, None
    val = float(sub.iloc[-1])
    if not np.isfinite(val):
        return None, None
    chg = None
    if window and len(sub) > window:
        prev = float(sub.iloc[-1 - window])
        if np.isfinite(prev):
            chg = val - prev
    return val, chg


def last_date(s: pd.Series | None) -> str | None:
    if s is None or len(s) == 0:
        return None
    return str(pd.Timestamp(s.index.max()).date())


def _dim(key: str, value, unit: str, display: str, state: str, note: str,
         threshold: str, source: str, source_last, change_20d=None,
         change_display="", extra=None) -> dict:
    d = {
        "key": key, "name": C.DIMENSION_META[key]["name"], "name_cn": C.DIMENSION_META[key]["cn"],
        "icon": C.DIMENSION_META[key]["icon"],
        "value": None if value is None else round(float(value), 3),
        "unit": unit, "display": display,
        "change_20d": None if change_20d is None else round(float(change_20d), 3),
        "change_display": change_display,
        "state": state, "state_cn": STATE_CN.get(state, state), "tone": TONE.get(state, "neutral"),
        "note": note, "threshold": threshold, "source": source,
        "source_last": source_last, "has_data": value is not None,
    }
    if extra:
        d.update(extra)
    return d


def snapshot(S: dict[str, pd.Series], date: pd.Timestamp) -> dict:
    """Seven dimension readings as of `date` (no future information)."""
    dims: dict[str, dict] = {}

    # 1. Credit spreads -----------------------------------------------------
    hy, hy20 = at(S["BAMLH0A0HYM2"], date, 20)
    proxy_used = False
    proxy_value = None
    if hy is None:
        ratio, _ = at(S["credit_proxy"], date)
        _, ratio20 = at(S["credit_proxy"], date, 20)
        if ratio is not None and ratio20 is not None:
            pct = ratio20 / (ratio - ratio20) * 100.0 if (ratio - ratio20) != 0 else 0.0
            proxy_used = True
            proxy_value, hy20 = pct, pct
            if pct >= 0.5:
                state = "EASING"
            elif pct <= -0.5:
                state = "WIDENING"
            else:
                state = "STABLE"
        else:
            state = "NO DATA"
    elif hy20 is not None and hy20 <= T["hy_narrow_20d"]:
        state = "EASING"
    elif hy20 is not None and hy20 >= T["hy_widen_20d"]:
        state = "WIDENING"
    else:
        state = "ELEVATED" if hy >= T["hy_elevated"] else "STABLE"
    if proxy_used:
        note = f"HYG/LQD ratio 20d {hy20:+.2f}% (documented fallback proxy — FRED OAS unavailable)"
        disp = f"{hy20:+.2f}% / 20d"
        src, slast = "HYG / LQD (proxy)", last_date(S["credit_proxy"])
    else:
        note = (f"HY OAS {hy:.2f}%" if hy is not None else "HY OAS unavailable") + (
            f"; 20d change {hy20:+.2f}pp" if hy20 is not None else "")
        disp = f"{hy:.2f}%" if hy is not None else "—"
        src, slast = "FRED BAMLH0A0HYM2", last_date(S["BAMLH0A0HYM2"])
    dims["credit"] = _dim(
        "credit", proxy_value if proxy_used else hy, "%", disp, state, note,
        "Easing ≤ −0.15pp/20d · widening ≥ +0.15pp · elevated ≥ 3.5%",
        src, slast, hy20,
        f"{hy20:+.2f}pp / 20d" if hy20 is not None else "",
        {"proxy": proxy_used})

    # 2. Treasury yields ----------------------------------------------------
    tnx, tnx20 = at(S["TNX"], date, 20)
    if tnx is None:
        tnx, tnx20 = at(S["DGS10"], date, 20)
    real, real20 = at(S["DFII10"], date, 20)
    if tnx is None and real is None:
        state = "NO DATA"
    else:
        easing = ((tnx20 is not None and tnx20 <= T["rate_ease_20d"]) or
                  (real20 is not None and real20 <= T["rate_ease_20d"]))
        state = "EASING" if easing else "PRESSURE"
    dims["rates"] = _dim(
        "rates", tnx, "%", f"{tnx:.2f}%" if tnx is not None else "—", state,
        f"10Y nominal {tnx:.2f}%" if tnx is not None else "10Y nominal —",
        "Easing: 10Y nominal or 10Y real yield falls ≥ 0.15pp in 20 observations",
        "Yahoo ^TNX + FRED DFII10", last_date(S["TNX"]) or last_date(S["DGS10"]),
        tnx20, f"{tnx20:+.2f}pp / 20d" if tnx20 is not None else "",
        {"real10y": None if real is None else round(real, 2),
         "real10y_chg20": None if real20 is None else round(real20, 2),
         "curve_10y2y": (lambda v: None if v is None else round(v, 2))(at(S["T10Y2Y"], date)[0]),
         "display_secondary": (f"10Y real {real:.2f}%" if real is not None else "10Y real —")})

    # 3. VIX term structure -------------------------------------------------
    vix, _ = at(S["VIX"], date)
    term, _ = at(S["vix_term"], date)
    vix9d, _ = at(S["VIX9D"], date)
    if vix is None and term is None:
        state = "NO DATA"
    elif (vix is not None and vix >= T["vix_panic"]) or \
         (term is not None and term > T["vix_term_inversion"]):
        state = "PANIC"
    elif term is not None and term > T["vix_term_stress"]:
        state = "STRESS"
    else:
        state = "CALM"
    dims["vix_term"] = _dim(
        "vix_term", vix, "idx", f"{vix:.2f}" if vix is not None else "—", state,
        f"VIX 30D {vix:.2f}" if vix is not None else "VIX 30D —",
        "Panic: VIX ≥ 30 or VIX9D/VIX > 1.05 (>5% backwardation)",
        "Yahoo ^VIX + ^VIX9D", last_date(S["vix_term"]) or last_date(S["VIX"]),
        None, "",
        {"vix9d": None if vix9d is None else round(vix9d, 2),
         "inversion_pct": None if term is None else round(term * 100, 2),
         "display_secondary": (f"9D/30D {term * 100:+.1f}%" if term is not None else "9D/30D —")})

    # 4. Investor sentiment -------------------------------------------------
    fng, _ = at(S["FNG"], date)
    if fng is None:
        state = "NO DATA"
    elif fng < T["fng_extreme_fear"]:
        state = "PANIC"
    elif fng < T["fng_fear"]:
        state = "FEAR"
    elif fng < T["fng_complacent"]:
        state = "NEUTRAL"
    else:
        state = "COMPLACENT"
    dims["sentiment"] = _dim(
        "sentiment", fng, "idx", f"{fng:.1f}" if fng is not None else "—", state,
        "CNN Fear & Greed 0–100 (extreme fear < 25)",
        "Extreme fear < 25 · fear < 45 · neutral 45–55 · complacent > 55",
        "CNN Fear & Greed", last_date(S["FNG"]), None, "",
        {"display_secondary": "≈1 year of public history"})

    # 5. Market breadth -----------------------------------------------------
    br, br20 = at(S["breadth"], date, 20)
    if br is None:
        state = "NO DATA"
    elif br < T["breadth_panic"]:
        state = "PANIC"
    elif br < T["breadth_weak"]:
        state = "WEAK"
    elif br < T["breadth_confirm"]:
        state = "NEUTRAL"
    else:
        state = "HEALTHY"
    dims["breadth"] = _dim(
        "breadth", br, "%", f"{br:.0f}%" if br is not None else "—", state,
        f"{br:.0f}% of 11 sector ETFs above their 50DMA" if br is not None else "Unavailable",
        "Panic < 30% · weak < 40% · confirmation ≥ 50%",
        "11 SPDR sector ETFs (Yahoo)", last_date(S["breadth"]),
        br20, f"{br20:+.1f}pp / 20d" if br20 is not None else "",
        {"display_secondary": (f"20d {br20:+.1f}pp" if br20 is not None else "20d —")})

    # 6. Trend reversal -----------------------------------------------------
    spy, _ = at(S["SPY"], date)
    ma50, _ = at(S["spy_ma50"], date)
    ma200, _ = at(S["spy_ma200"], date)
    r20, _ = at(S["spy_r20"], date)
    slope, _ = at(S["ma50_slope20"], date)
    if spy is None or ma50 is None:
        state = "NO DATA"
    elif spy > ma50 and ma200 is not None and spy > ma200:
        state = "CONFIRMED"
    elif spy > ma50:
        state = "RECOVERING"
    else:
        state = "BEAR"
    dist50 = (spy / ma50 - 1) * 100 if (spy is not None and ma50) else None
    dist200 = (spy / ma200 - 1) * 100 if (spy is not None and ma200) else None
    dims["trend"] = _dim(
        "trend", spy, "USD", f"${spy:,.2f}" if spy is not None else "—", state,
        (f"vs 50DMA {dist50:+.1f}%, vs 200DMA {dist200:+.1f}%" if dist50 is not None and dist200 is not None
         else "Moving averages not yet available"),
        "Confirmed: SPY > 50DMA and > 200DMA · recovering: above 50DMA only",
        "Yahoo SPY", last_date(S["SPY"]),
        r20, f"{r20:+.1f}% / 20d" if r20 is not None else "",
        {"ma50": None if ma50 is None else round(ma50, 2),
         "ma200": None if ma200 is None else round(ma200, 2),
         "ma50_slope20": None if slope is None else round(slope, 2),
         "display_secondary": (f"50DMA slope {slope:+.1f}% / 20d" if slope is not None else "50DMA slope —")})

    # 7. Long-term valuation ------------------------------------------------
    cape, _ = at(S["CAPE"], date)
    if cape is None:
        state = "NO DATA"
    elif cape <= T["cape_cheap"]:
        state = "CHEAP"
    elif cape >= T["cape_expensive"]:
        state = "EXPENSIVE"
    else:
        state = "FAIR"
    dims["valuation"] = _dim(
        "valuation", cape, "x", f"{cape:.1f}x" if cape is not None else "—", state,
        "Shiller cyclically adjusted P/E, monthly",
        "Cheap ≤ 15x · fair 15–30x · expensive ≥ 30x",
        "multpl.com / Shiller CAPE", last_date(S["CAPE"]), None, "",
        {"display_secondary": "Monthly · latest revised vintage"})
    return dims


def coverage_last(S: dict[str, pd.Series]) -> dict[str, str | None]:
    """Actual last observation date of every cache file — the honest freshness view."""
    keys = list(C.PRICE_SYMBOLS) + list(C.FRED_SERIES) + ["FNG", "CAPE"]
    return {k: last_date(S.get(k)) for k in keys}


def trading_dates(S: dict[str, pd.Series], lookback: int = 260) -> list[pd.Timestamp]:
    """Recent SPY sessions, the calendar used by the phase timeline."""
    spy = S.get("SPY", pd.Series(dtype=float))
    if len(spy) == 0:
        return []
    return [pd.Timestamp(d) for d in spy.index[-lookback:]]
