#!/usr/bin/env python3
"""P0–P3 bear-market bottom classification — pure, testable, no I/O.

The engine answers one question: *where are we in the panic-and-bottom
sequence?* It never forecasts a return and never emits a buy/sell order.

P0 Observation      fewer than two fear conditions, or insufficient data
P1 Panic clearing   >= 2 of 3 fear conditions (VIX term structure, sentiment, breadth)
P2 Bottom brewing   >= 2 of 4 improvements AND a P1 episode in the last 120 sessions
P3 Trend confirmed  >= 1 of 2 confirmations AND a P1 episode in the last 120 sessions

The 120-session "panic memory" is deliberate: requiring panic and trend
confirmation on the *same* day would make P3 unreachable in a real recovery.
A NO DATA check can never count as satisfied.
"""
from __future__ import annotations

from pipeline import config as C

T = C.THRESHOLDS


def _cond(state: str, ok_states: set[str], near_states: set[str] = frozenset()) -> str:
    if state == "NO DATA":
        return "no data"
    if state in ok_states:
        return "satisfied"
    if state in near_states:
        return "near"
    return "not satisfied"


def _check(name: str, cn: str, status: str, detail: str) -> dict:
    return {"name": name, "cn": cn, "status": status, "detail": detail}


def _tally(items: list[dict]) -> dict:
    return {
        "satisfied": sum(1 for x in items if x["status"] == "satisfied"),
        "near": sum(1 for x in items if x["status"] == "near"),
        "no_data": sum(1 for x in items if x["status"] == "no data"),
        "total": len(items),
    }


def classify(dims: dict, panic_seen: bool = False) -> dict:
    """Classify one date from its seven dimension readings."""
    d = dims
    change = d["breadth"]["change_20d"]

    p1 = [
        _check("VIX term structure panic", "VIX 期限结构恐慌",
               _cond(d["vix_term"]["state"], {"PANIC"}, {"STRESS"}),
               d["vix_term"]["note"] + " · " + d["vix_term"].get("display_secondary", "")),
        _check("Extreme fear in sentiment", "投资者极度恐慌",
               _cond(d["sentiment"]["state"], {"PANIC"}, {"FEAR"}),
               d["sentiment"]["display"] + " — " + d["sentiment"]["state_cn"]),
        _check("Breadth collapse", "市场宽度崩塌",
               _cond(d["breadth"]["state"], {"PANIC"}, {"WEAK"}),
               d["breadth"]["display"] + " of sectors above 50DMA"),
    ]
    p2 = [
        _check("Credit risk stabilising", "信用风险企稳",
               _cond(d["credit"]["state"], {"EASING"}),
               d["credit"]["note"]),
        _check("Rate pressure easing", "利率压力缓和",
               _cond(d["rates"]["state"], {"EASING"}),
               d["rates"]["display"] + " · " + d["rates"].get("display_secondary", "")),
        _check("Breadth improving", "市场宽度改善",
               ("no data" if change is None else
                "satisfied" if change >= T["breadth_improve_20d"] else
                "near" if change > 0 else "not satisfied"),
               "20d change " + (f"{change:+.1f}pp" if change is not None else "—")),
        _check("Price structure stabilising", "价格结构企稳",
               _cond(d["trend"]["state"], {"RECOVERING", "CONFIRMED"}),
               d["trend"]["display"] + " · " + d["trend"]["note"]),
    ]
    p3 = [
        _check("Breadth reversal path", "宽度反转路径",
               ("no data" if d["breadth"]["value"] is None else
                "satisfied" if d["breadth"]["value"] >= T["breadth_confirm"] else "not satisfied"),
               f"Breadth back above {T['breadth_confirm']:.0f}% of sectors"),
        _check("50/200DMA trend confirmation", "均线趋势确认",
               _cond(d["trend"]["state"], {"CONFIRMED"}),
               "SPY above both its 50-day and 200-day moving averages"),
    ]

    t1, t2, t3 = _tally(p1), _tally(p2), _tally(p3)
    panic_now = t1["satisfied"] >= 2
    in_play = bool(panic_seen or panic_now)
    trend_ok = d["trend"]["state"] in ("RECOVERING", "CONFIRMED")

    if in_play and t3["satisfied"] >= 1 and trend_ok:
        phase = "P3"
    elif in_play and t2["satisfied"] >= 2:
        phase = "P2"
    elif panic_now:
        phase = "P1"
    else:
        phase = "P0"

    meta = C.PHASE_META[phase]
    return {
        "phase": phase, "label": meta["label"], "cn": meta["cn"],
        "text": meta["text"], "text_cn": meta["text_cn"],
        "panic_now": panic_now, "panic_seen": in_play,
        "P1": {"count": t1["satisfied"], "need": 2, "checks": p1, "tally": t1},
        "P2": {"count": t2["satisfied"], "need": 2, "checks": p2, "tally": t2},
        "P3": {"count": t3["satisfied"], "need": 1, "checks": p3, "tally": t3},
        "rules": C.PHASE_RULES,
    }
