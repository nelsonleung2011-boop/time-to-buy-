#!/usr/bin/env python3
"""Single source of truth for paths, data sources and pre-registered rules.

Every threshold used by the phase engine is declared here and echoed into the
published payload, so the dashboard and the README can never drift away from
the code that actually classifies the market.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
MACRO = DATA / "macro"
OBSERVATIONS = MACRO / "observations.json"
LATEST = DATA / "latest.json"
HISTORY = DATA / "history.csv"
SOURCES = DATA / "sources.json"
TEMPLATE = ROOT / "dashboard_template.html"
INDEX = ROOT / "index.html"

PROJECT = "Time to Buy?"
SUBTITLE = "美股熊市底部监控 / US Bear-Market Bottom Monitor"
VERSION = "1.0"

# GitHub Actions runs after the US close. 06:30 UTC = 01:30 EST / 02:30 EDT.
# Tue-Sat UTC covers Mon-Fri US sessions.
SCHEDULE_CRON = "30 6 * * 2-6"
SCHEDULE_TEXT = "06:30 UTC, Tue–Sat (after the US close)"
SCHEDULE_DAYS_UTC = [2, 3, 4, 5, 6]  # JS day-of-week: 0=Sun
SCHEDULE_HOUR_UTC = 6
SCHEDULE_MINUTE_UTC = 30

# ---------------------------------------------------------------------------
# Market data sources — all public, no API key, no GitHub secret required.
# ---------------------------------------------------------------------------
SECTORS = ["XLC", "XLRE", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]

PRICE_SYMBOLS = {
    "SPY": "SPY",           # S&P 500 ETF — trend anchor and trading calendar
    "VIX": "%5EVIX",        # CBOE VIX (30-day)
    "VIX9D": "%5EVIX9D",    # CBOE 9-day VIX — term structure
    "TNX": "%5ETNX",        # 10Y Treasury yield, %
    "FVX": "%5EFVX",        # 5Y Treasury yield, % (context)
    "HYG": "HYG",           # High-yield credit ETF (fallback proxy)
    "LQD": "LQD",           # Investment-grade credit ETF (fallback proxy)
    "RSP": "RSP",           # Equal-weight S&P 500 (breadth context)
    **{s: s for s in SECTORS},
}

FRED_SERIES = {
    "BAMLH0A0HYM2": "ICE BofA US High Yield OAS (percent)",
    "DFII10": "10-Year TIPS real yield (percent)",
    "T10Y2Y": "10Y minus 2Y Treasury curve (percentage points)",
    "DGS10": "10-Year Treasury constant maturity (percent, TNX fallback)",
}

CNN_FNG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
MULTPL_CAPE_URL = "https://www.multpl.com/shiller-pe/table/by-month"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"

# Catalog shown in the Data & Freshness tab. `used_for` is a dimension key.
SOURCE_CATALOG = [
    {"key": "SPY", "name": "S&P 500 ETF (SPY)", "url": "https://finance.yahoo.com/quote/SPY/",
     "provider": "Yahoo Finance chart API", "used_for": "trend", "frequency": "daily close"},
    {"key": "VIX", "name": "CBOE VIX 30-day", "url": "https://finance.yahoo.com/quote/%5EVIX/",
     "provider": "Yahoo Finance chart API", "used_for": "vix_term", "frequency": "daily close"},
    {"key": "VIX9D", "name": "CBOE VIX 9-day", "url": "https://finance.yahoo.com/quote/%5EVIX9D/",
     "provider": "Yahoo Finance chart API", "used_for": "vix_term", "frequency": "daily close"},
    {"key": "TNX", "name": "10Y Treasury yield", "url": "https://finance.yahoo.com/quote/%5ETNX/",
     "provider": "Yahoo Finance chart API", "used_for": "rates", "frequency": "daily close"},
    {"key": "BAMLH0A0HYM2", "name": "ICE BofA US High Yield OAS",
     "url": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
     "provider": "FRED fredgraph.csv", "used_for": "credit", "frequency": "business daily"},
    {"key": "DFII10", "name": "10Y TIPS real yield",
     "url": "https://fred.stlouisfed.org/series/DFII10",
     "provider": "FRED fredgraph.csv", "used_for": "rates", "frequency": "business daily"},
    {"key": "FNG", "name": "CNN Fear & Greed Index",
     "url": "https://www.cnn.com/markets/fear-and-greed",
     "provider": "CNN dataviz graphdata", "used_for": "sentiment", "frequency": "daily (≈1y history)"},
    {"key": "SECTORS", "name": "11 US sector ETFs", "url": "https://www.sectorspdrs.com/",
     "provider": "Yahoo Finance chart API", "used_for": "breadth", "frequency": "daily close"},
    {"key": "CAPE", "name": "Shiller CAPE (cyclically adjusted P/E)",
     "url": "https://www.multpl.com/shiller-pe",
     "provider": "multpl.com monthly table", "used_for": "valuation", "frequency": "monthly"},
    {"key": "HYG_LQD", "name": "HYG / LQD credit ETF pair",
     "url": "https://finance.yahoo.com/quote/HYG/",
     "provider": "Yahoo Finance chart API", "used_for": "credit (fallback proxy)", "frequency": "daily close"},
]

# ---------------------------------------------------------------------------
# Pre-registered thresholds (never tuned on the live reading).
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "vix_panic": 30.0,           # VIX level
    "vix_term_inversion": 0.05,  # VIX9D/VIX - 1 (5% = backwardation)
    "vix_term_stress": 0.0,      # any inversion at all
    "fng_extreme_fear": 25.0,
    "fng_fear": 45.0,
    "fng_complacent": 55.0,
    "breadth_panic": 30.0,       # % of 11 sectors above 50DMA
    "breadth_weak": 40.0,
    "breadth_confirm": 50.0,
    "hy_elevated": 3.5,          # HY OAS, %
    "hy_narrow_20d": -0.15,      # pp change over 20 observations
    "hy_widen_20d": 0.15,
    "rate_ease_20d": -0.15,      # pp change over 20 observations
    "breadth_improve_20d": 5.0,  # pp change over 20 sessions
    "cape_cheap": 15.0,
    "cape_expensive": 30.0,
    "panic_memory_sessions": 120,  # how long a P1 episode stays "in play"
}

PHASE_META = {
    "P0": {"label": "Observation", "cn": "观察",
           "text": "No stress cluster. Keep watching the seven dimensions.",
           "text_cn": "尚未出现压力聚集，继续观察七个维度。"},
    "P1": {"label": "Panic clearing", "cn": "恐慌出清",
           "text": "Fear is present across volatility, sentiment and breadth; risk has not cleared.",
           "text_cn": "波动率、情绪与市场宽度同时出现恐慌，风险尚未出清。"},
    "P2": {"label": "Bottom brewing", "cn": "底部酝酿",
           "text": "Credit, rates, breadth or price structure are starting to stabilise after panic.",
           "text_cn": "恐慌之后，信用、利率、宽度或价格结构开始企稳。"},
    "P3": {"label": "Trend confirmed", "cn": "趋势确认",
           "text": "At least one confirmation path is established; the panic low is likely behind us.",
           "text_cn": "至少一条确认路径成立，恐慌低点大概率已过去。"},
}

PHASE_RULES = {
    "P0": "Default state: fewer than two fear conditions, or insufficient data.",
    "P1": "≥ 2 of 3 fear conditions: VIX term structure, sentiment, breadth.",
    "P2": "≥ 2 of 4 improvements (credit, rates, breadth, trend) AND a P1 episode in the last 120 sessions.",
    "P3": "≥ 1 of 2 confirmations (breadth ≥ 50%, SPY above both 50/200DMA), price above its 50DMA, AND a P1 episode in the last 120 sessions.",
}

DIMENSION_ORDER = ["credit", "rates", "vix_term", "sentiment", "breadth", "trend", "valuation"]

DIMENSION_META = {
    "credit": {"name": "Credit spreads", "cn": "信用利差", "icon": "CR"},
    "rates": {"name": "Treasury yields", "cn": "国债收益率", "icon": "RT"},
    "vix_term": {"name": "VIX term structure", "cn": "VIX 期限结构", "icon": "VX"},
    "sentiment": {"name": "Investor sentiment", "cn": "投资者情绪", "icon": "ST"},
    "breadth": {"name": "Market breadth", "cn": "市场宽度", "icon": "BR"},
    "trend": {"name": "Trend reversal", "cn": "趋势反转", "icon": "TR"},
    "valuation": {"name": "Long-term valuation", "cn": "长期估值", "icon": "VL"},
}

DISCLAIMER = (
    "This is a condition detector, not a return forecast or a trading signal. "
    "It reports observable market states and their pre-registered rules. "
    "Educational research only — not investment advice."
)
