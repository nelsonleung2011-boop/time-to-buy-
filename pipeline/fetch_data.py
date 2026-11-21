#!/usr/bin/env python3
"""Cloud-side daily data collection.

Runs inside GitHub Actions (or locally) with **no credentials**: every source
is a public endpoint. The three rules that matter:

1. A failing source NEVER overwrites good cached data. Each series is validated
   before its cache file is replaced; on failure the committed cache is kept and
   the reason is recorded in ``data/sources.json``.
2. Dated macro observations are MERGED by date, never replaced wholesale, so a
   provider glitch cannot erase 25 years of history.
3. Yahoo ``adj_close`` is retroactively dividend-adjusted, so price CSVs are
   replaced wholesale (only when valid) to keep each series internally
   consistent.

Sources: Yahoo Finance chart API, FRED fredgraph.csv, CNN Fear & Greed,
multpl.com Shiller CAPE. No browser-side network calls are ever made.
"""
from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import config as C

UA_BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "*/*",
}
UA_FRED = {"User-Agent": "curl/8.4.0", "Accept": "text/csv,*/*"}


def http_get(url: str, timeout: int = 30, attempts: int = 3,
             headers: dict | None = None) -> bytes:
    """GET with retry/backoff. Raises after the last attempt."""
    h = dict(UA_BROWSER)
    if headers:
        h.update(headers)
    last: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(0.9 * (i + 1))
    raise RuntimeError(f"{type(last).__name__}: {last}" if last else "HTTP failed")


# ---------------------------------------------------------------------------
# Source adapters -> list of {"date": "YYYY-MM-DD", "value"/"close": float}
# ---------------------------------------------------------------------------
def fetch_yahoo(symbol: str) -> list[dict]:
    """Full daily history with a DYNAMIC end date (never a hard-coded cutoff)."""
    end = int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).timestamp())
    url = (C.YAHOO_URL + symbol
           + f"?period1=946684800&period2={end}&interval=1d&events=div%2Csplit")
    j = json.loads(http_get(url, headers={"Referer": "https://finance.yahoo.com/"})
                   .decode("utf-8", "ignore"))
    r0 = (j.get("chart", {}).get("result") or [None])[0]
    if not r0 or not r0.get("timestamp"):
        raise RuntimeError("empty chart result")
    ts = r0["timestamp"]
    quote = ((r0.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
    adj = ((r0.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or [])
    rows = []
    for i, t in enumerate(ts):
        close = quote[i] if i < len(quote) else None
        a = adj[i] if i < len(adj) else None
        if close is None or not np.isfinite(close):
            continue
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat()
        rows.append({"date": d, "close": float(close),
                     "adj_close": float(a) if a is not None and np.isfinite(a) else float(close)})
    if not rows:
        raise RuntimeError("no valid closes")
    return rows


def fetch_fred(series_id: str) -> list[dict]:
    txt = http_get(C.FRED_URL + series_id, headers=UA_FRED).decode("utf-8", "ignore")
    out = []
    for line in txt.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[-1].strip()
        if not d or v in (".", "", "NA"):
            continue
        try:
            out.append({"date": d, "value": float(v)})
        except ValueError:
            continue
    if not out:
        raise RuntimeError("empty FRED series")
    return out


def fetch_fng() -> list[dict]:
    raw = http_get(
        C.CNN_FNG_URL,
        headers={"Referer": "https://www.cnn.com/",
                 "Accept": "application/json,text/plain,*/*"},
    ).decode("utf-8", "ignore")
    j = json.loads(raw)
    rows = []
    for p in j.get("fear_and_greed_historical", {}).get("data", []):
        x, y = p.get("x"), p.get("y")
        if x is None or y is None:
            continue
        try:
            v = float(y)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(v):
            continue
        d = dt.datetime.fromtimestamp(float(x) / 1000.0, dt.timezone.utc).date().isoformat()
        rows.append({"date": d, "value": v})
    if not rows:
        raise RuntimeError("empty CNN Fear & Greed history")
    return rows


def fetch_cape() -> list[dict]:
    """multpl monthly Shiller CAPE table; keep canonical month-start rows only."""
    s = http_get(C.MULTPL_CAPE_URL, timeout=45).decode("utf-8", "ignore")
    pairs = re.findall(r"<tr[^>]*>\s*<td[^>]*>\s*([^<]+?)\s*</td>\s*"
                       r"<td[^>]*>\s*([^<]+?)\s*</td>", s)
    out: dict[str, float] = {}
    for a, b in pairs:
        ds = html_lib.unescape(a).strip()
        vs = re.sub(r"[^\d.\-]", "", html_lib.unescape(b))
        try:
            d = dt.datetime.strptime(ds, "%b %d, %Y").date()
            v = float(vs)
        except (ValueError, TypeError):
            continue
        # Skip multpl's partial current-month row (e.g. "Nov 18, 2026").
        if d.day > 7:
            continue
        out[d.isoformat()] = v
    if not out:
        raise RuntimeError("no CAPE rows parsed")
    return [{"date": d, "value": out[d]} for d in sorted(out)]


# ---------------------------------------------------------------------------
# Cache-safe writes
# ---------------------------------------------------------------------------
def _valid_replacement(rows: list[dict], old_len: int, old_last: str | None) -> tuple[bool, str]:
    if len(rows) < 100:
        return False, f"only {len(rows)} rows returned"
    if old_len and len(rows) < int(old_len * 0.95):
        return False, f"history shrank {old_len} -> {len(rows)}"
    new_last = rows[-1]["date"]
    if old_last and new_last < old_last:
        return False, f"last date went backwards {old_last} -> {new_last}"
    for r in rows[:3] + rows[-3:]:
        if not np.isfinite(r["close"]) or r["close"] <= 0:
            return False, "non-positive close in head/tail"
    return True, ""


def merge_csv(path: Path, rows: list[dict]) -> dict:
    """Validate then replace one price CSV. Returns a per-symbol status record."""
    if path.exists():
        old = pd.read_csv(path)
        old_len = len(old)
        old_last = str(old["date"].iloc[-1])[:10] if old_len else None
    else:
        old_len, old_last = 0, None
    ok, why = _valid_replacement(rows, old_len, old_last)
    if not ok:
        return {"status": "KEPT CACHE", "reason": why, "last": old_last, "n": old_len}
    new = pd.DataFrame(rows)[["date", "close", "adj_close"]]
    new = new.drop_duplicates("date", keep="last").sort_values("date")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new.to_csv(index=False), encoding="utf-8")
    return {"status": "UPDATED", "added": max(0, len(new) - old_len),
            "from": old_last, "last": str(new["date"].iloc[-1]), "n": len(new)}


def merge_observations(old: list[dict], new: list[dict]) -> list[dict]:
    """Union by date; refreshed values win (they include vendor revisions)."""
    by_date = {str(r["date"])[:10]: dict(r) for r in old}
    for r in new:
        d = str(r["date"])[:10]
        merged = dict(by_date.get(d, {}))
        merged.update(r)
        by_date[d] = merged
    return [by_date[k] for k in sorted(by_date)]


def _cached_last_price(path: Path) -> str | None:
    try:
        return str(pd.read_csv(path)["date"].iloc[-1])[:10]
    except Exception:
        return None


def refresh(offline: bool = False) -> dict:
    """Refresh every source. Returns the report also written to sources.json."""
    C.RAW.mkdir(parents=True, exist_ok=True)
    C.MACRO.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report: dict = {"checked_at": now, "mode": "OFFLINE (cached data used)" if offline else "LIVE",
                    "sources": {}, "updated": 0, "failed": 0}

    if offline:
        C.SOURCES.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    # --- price CSVs -------------------------------------------------------
    for key, sym in C.PRICE_SYMBOLS.items():
        path = C.RAW / f"{key}.csv"
        try:
            rec = merge_csv(path, fetch_yahoo(sym))
        except Exception as exc:
            rec = {"status": "KEPT CACHE", "reason": type(exc).__name__ + ": " + str(exc)[:110],
                   "last": _cached_last_price(path)}
        report["sources"][key] = rec
        time.sleep(0.12)

    # --- dated macro observations ----------------------------------------
    obs: dict[str, list[dict]] = {}
    if C.OBSERVATIONS.exists():
        obs = json.loads(C.OBSERVATIONS.read_text(encoding="utf-8"))
    adapters: list[tuple[str, callable]] = [
        (sid, lambda sid=sid: fetch_fred(sid)) for sid in C.FRED_SERIES
    ] + [("FNG", fetch_fng), ("CAPE", fetch_cape)]
    for key, fn in adapters:
        before = obs.get(key, [])
        before_last = before[-1]["date"] if before else None
        try:
            rows = fn()
            if len(rows) < 20 and before_last:
                raise RuntimeError(f"only {len(rows)} rows; refusing to shrink history")
            obs[key] = merge_observations(before, rows)
            report["sources"][key] = {
                "status": "UPDATED", "added": len(obs[key]) - len(before),
                "last": obs[key][-1]["date"], "n": len(obs[key]),
            }
        except Exception as exc:
            report["sources"][key] = {
                "status": "KEPT CACHE", "last": before_last, "n": len(before),
                "reason": type(exc).__name__ + ": " + str(exc)[:110],
            }
        time.sleep(0.15)

    C.OBSERVATIONS.write_text(json.dumps(obs, separators=(",", ":")), encoding="utf-8")

    report["updated"] = sum(1 for v in report["sources"].values() if v.get("status") == "UPDATED")
    report["failed"] = len(report["sources"]) - report["updated"]
    report["status"] = "OK" if report["updated"] else "ALL SOURCES KEPT CACHE"
    C.SOURCES.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    import sys
    r = refresh(offline="--offline" in sys.argv)
    print(f"[fetch] {r['status'] if not r['mode'].startswith('OFFLINE') else r['mode']} "
          f"| updated {r['updated']} | kept cache {r['failed']}")
