#!/usr/bin/env python3
"""One-command daily build: collect data -> score seven dimensions -> classify
P0-P3 -> publish a self-contained static dashboard.

    python pipeline/build_dashboard.py                  # live refresh + publish
    python pipeline/build_dashboard.py --offline        # cached data only
    python pipeline/build_dashboard.py --as-of 2026-11-20

Outputs (all committed by GitHub Actions so the site is fully static):
    data/latest.json    full snapshot payload   <- machine readable
    data/history.csv    daily phase log         <- upserted, never truncated
    data/sources.json   per-source refresh report
    index.html          standalone dashboard    <- data embedded, works offline

The browser NEVER calls a financial data provider. GitHub Actions does.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import deque
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import config as C          # noqa: E402
from pipeline import fetch_data as F      # noqa: E402
from pipeline import indicators as I      # noqa: E402
from pipeline import phases as P          # noqa: E402

UTC = dt.timezone.utc


def _json_safe(obj):
    """Replace NaN/Inf and numpy scalars with plain JSON values."""
    import math
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, (str, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    try:
        import numpy as np
        if isinstance(obj, (np.floating, np.integer, np.bool_)):
            return _json_safe(obj.item())
    except ImportError:
        pass
    return obj


def _clean_dumps(obj) -> str:
    """JSON for a <script> tag: escape any '</' so it cannot close the tag."""
    return json.dumps(_json_safe(obj), ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).replace("</", "<\\/")


def _source_rows(S: dict, report: dict) -> list[dict]:
    groups = {
        "SPY": ["SPY"], "VIX": ["VIX"], "VIX9D": ["VIX9D"], "TNX": ["TNX"],
        "BAMLH0A0HYM2": ["BAMLH0A0HYM2"], "DFII10": ["DFII10"],
        "FNG": ["FNG"], "SECTORS": list(C.SECTORS), "CAPE": ["CAPE"],
        "HYG_LQD": ["HYG", "LQD"],
    }
    cov = I.coverage_last(S)
    out = []
    for cat in C.SOURCE_CATALOG:
        keys = groups.get(cat["key"], [cat["key"]])
        dates = [cov.get(k) for k in keys if cov.get(k)]
        last = min(dates) if dates else None
        statuses = [report.get("sources", {}).get(k, {}).get("status", "CACHED") for k in keys]
        status = "UPDATED" if all(s == "UPDATED" for s in statuses) else (
            "PARTIAL" if any(s == "UPDATED" for s in statuses) else
            ("CACHED" if report["mode"].startswith("OFFLINE") else "KEPT CACHE"))
        out.append({**cat, "last": last,
                    "n_series": len(keys), "status": status,
                    "series": ", ".join(keys[:4]) + (" …" if len(keys) > 4 else "")})
    return out


def _history_row(date: pd.Timestamp, dims: dict, phase: dict) -> dict:
    return {
        "date": str(pd.Timestamp(date).date()),
        "phase": phase["phase"],
        "p1": phase["P1"]["count"], "p2": phase["P2"]["count"], "p3": phase["P3"]["count"],
        "vix": dims["vix_term"]["value"],
        "inversion_pct": dims["vix_term"].get("inversion_pct"),
        "breadth": dims["breadth"]["value"],
        "hy_oas": dims["credit"]["value"] if not dims["credit"].get("proxy") else None,
        "fng": dims["sentiment"]["value"],
        "tnx": dims["rates"]["value"],
        "cape": dims["valuation"]["value"],
        "spy": dims["trend"]["value"],
        "trend": dims["trend"]["state"],
        "credit": dims["credit"]["state"],
        "sentiment": dims["sentiment"]["state"],
    }


def _write_history(rows: list[dict]) -> None:
    """Upsert by date; a re-run never duplicates or truncates the log."""
    existing: dict[str, dict] = {}
    if C.HISTORY.exists():
        with C.HISTORY.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing[r["date"]] = r
    for r in rows:
        existing[r["date"]] = {k: ("" if v is None else v) for k, v in r.items()}
    fields = ["date", "phase", "p1", "p2", "p3", "vix", "inversion_pct", "breadth",
              "hy_oas", "fng", "tnx", "cape", "spy", "trend", "credit", "sentiment"]
    with C.HISTORY.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for d in sorted(existing):
            w.writerow({k: existing[d].get(k, "") for k in fields})


def build(offline: bool = False, as_of: str | None = None) -> dict:
    now = dt.datetime.now(UTC)
    print("[build] 1/5 refreshing market data ...", flush=True)
    report = F.refresh(offline=offline)

    print("[build] 2/5 building seven dimensions ...", flush=True)
    S = I.build_series()
    dates = I.trading_dates(S, lookback=260)
    if not dates:
        raise RuntimeError("no SPY price history found — run the fetch step first")
    last_market = pd.Timestamp(dates[-1])
    scoring_date = pd.Timestamp(as_of) if as_of else last_market

    print(f"[build] 3/5 classifying {len(dates)} sessions ...", flush=True)
    memory = deque(maxlen=C.THRESHOLDS["panic_memory_sessions"])
    timeline: list[dict] = []
    current_dims = current_phase = None
    for d in dates:
        dims = I.snapshot(S, d)
        ph = P.classify(dims, panic_seen=any(memory))
        memory.append(ph["panic_now"])
        timeline.append(_history_row(d, dims, ph))
        if d == scoring_date:
            current_dims, current_phase = dims, ph
    if current_dims is None:  # --as-of outside the cached window
        current_dims = I.snapshot(S, scoring_date)
        current_phase = P.classify(current_dims, panic_seen=any(memory))

    print("[build] 4/5 writing data files ...", flush=True)
    as_of_date = str(pd.Timestamp(scoring_date).date())
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    data_age = (now.date() - pd.Timestamp(scoring_date).date()).days
    payload = {
        "meta": {
            "project": C.PROJECT, "subtitle": C.SUBTITLE, "version": C.VERSION,
            "generated_at": generated_at,
            "as_of": as_of_date,
            "as_of_weekday": pd.Timestamp(scoring_date).day_name(),
            "run_mode": report["mode"],
            "refresh_status": report.get("status", "OFFLINE"),
            "sources_updated": report["updated"], "sources_failed": report["failed"],
            "data_age_days": data_age,
            "schedule": C.SCHEDULE_TEXT, "schedule_cron": C.SCHEDULE_CRON,
            "schedule_days_utc": C.SCHEDULE_DAYS_UTC,
            "schedule_hour_utc": C.SCHEDULE_HOUR_UTC,
            "schedule_minute_utc": C.SCHEDULE_MINUTE_UTC,
            "thresholds": C.THRESHOLDS, "phase_meta": C.PHASE_META,
            "phase_rules": C.PHASE_RULES, "dimension_order": C.DIMENSION_ORDER,
            "disclaimer": C.DISCLAIMER,
            "history_sessions": len(timeline),
            "data_notes": [
                "FRED and multpl serve latest-revised vintages, not real-time vintages.",
                "CNN Fear & Greed has only about one year of public history; before that the sentiment check is NO DATA.",
                "A failing source keeps its committed cache and is labelled KEPT CACHE, never silently filled.",
            ],
        },
        "current": {
            "date": as_of_date,
            "dimensions": current_dims,
            "phases": current_phase,
            "coverage": I.coverage_last(S),
        },
        "history": timeline,
        "sources": _source_rows(S, report),
        "refresh": {"checked_at": report["checked_at"], "mode": report["mode"],
                    "updated": report["updated"], "failed": report["failed"],
                    "sources": report.get("sources", {})},
    }
    payload = _json_safe(payload)
    C.LATEST.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    _write_history(timeline)

    print("[build] 5/5 publishing index.html ...", flush=True)
    tpl = C.TEMPLATE.read_text(encoding="utf-8")
    if "__PAYLOAD__" not in tpl:
        raise RuntimeError("template is missing the __PAYLOAD__ placeholder")
    html = tpl.replace("__PAYLOAD__", _clean_dumps(payload), 1)
    C.INDEX.write_text(html, encoding="utf-8")

    ph = current_phase["phase"]
    print(f"[build] DONE | data as of {as_of_date} | phase {ph} "
          f"({current_phase['cn']}) | updated {report['updated']} sources, "
          f"kept cache {report['failed']} | index.html {C.INDEX.stat().st_size:,} bytes",
          flush=True)
    return payload


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Build the Time to Buy? dashboard")
    ap.add_argument("--offline", action="store_true", help="use committed cache, no network")
    ap.add_argument("--as-of", default=None, help="score a specific date (YYYY-MM-DD)")
    args = ap.parse_args(argv)
    build(offline=args.offline, as_of=args.as_of)


if __name__ == "__main__":
    main()
