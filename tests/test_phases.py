#!/usr/bin/env python3
"""Offline unit tests: python -m unittest discover -s tests -v

No network access and no live data are needed.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import config as C          # noqa: E402
from pipeline import indicators as I      # noqa: E402
from pipeline import phases as P          # noqa: E402
from pipeline.build_dashboard import _clean_dumps  # noqa: E402


def dim(state="CALM", value=10.0, change=None, display="10", note="test"):
    return {"key": "x", "name": "X", "name_cn": "X", "state": state,
            "state_cn": state, "tone": "neutral", "value": value,
            "change_20d": change, "display": display, "display_secondary": "",
            "note": note, "threshold": "", "source": "test", "source_last": None,
            "has_data": value is not None}


def dims(**overrides):
    base = {
        "credit": dim("STABLE"),
        "rates": dim("PRESSURE"),
        "vix_term": dim("CALM"),
        "sentiment": dim("NEUTRAL"),
        "breadth": dim("HEALTHY", 60.0, change=0.0),
        "trend": dim("BEAR"),
        "valuation": dim("FAIR"),
    }
    base.update(overrides)
    return base


class PhaseTests(unittest.TestCase):
    def test_p0_on_calm_market(self):
        self.assertEqual(P.classify(dims())["phase"], "P0")

    def test_p1_needs_two_fear_conditions(self):
        self.assertEqual(P.classify(dims(vix_term=dim("PANIC")))["phase"], "P0")
        r = P.classify(dims(vix_term=dim("PANIC"), sentiment=dim("PANIC")))
        self.assertEqual(r["phase"], "P1")
        self.assertTrue(r["panic_now"])
        self.assertEqual(r["P1"]["count"], 2)

    def test_no_data_never_satisfies_a_check(self):
        nod = dim("NO DATA", None, None, "—")
        r = P.classify(dims(**{k: nod for k in C.DIMENSION_ORDER}))
        self.assertEqual(r["phase"], "P0")
        for p in ("P1", "P2", "P3"):
            self.assertTrue(all(c["status"] == "no data" for c in r[p]["checks"]))
            self.assertEqual(r[p]["tally"]["satisfied"], 0)

    def test_near_is_not_satisfied(self):
        r = P.classify(dims(breadth=dim("WEAK", 35.0, change=0.0)))
        self.assertEqual(r["P1"]["checks"][2]["status"], "near")
        self.assertEqual(r["P1"]["count"], 0)

    def test_p2_requires_panic_memory(self):
        improved = dims(
            credit=dim("EASING"), rates=dim("EASING"),
            breadth=dim("NEUTRAL", 45.0, change=6.0), trend=dim("RECOVERING"),
        )
        self.assertEqual(P.classify(improved, panic_seen=False)["phase"], "P0")
        r = P.classify(improved, panic_seen=True)
        self.assertEqual(r["phase"], "P2")
        self.assertEqual(r["P2"]["count"], 4)

    def test_p3_confirmation_outranks_p2(self):
        confirmed = dims(
            credit=dim("EASING"), rates=dim("EASING"),
            breadth=dim("HEALTHY", 60.0, change=6.0), trend=dim("CONFIRMED"),
        )
        self.assertEqual(P.classify(confirmed, panic_seen=True)["phase"], "P3")
        self.assertEqual(P.classify(confirmed, panic_seen=True)["P3"]["count"], 2)

    def test_p3_blocked_when_trend_is_bear(self):
        mixed = dims(breadth=dim("HEALTHY", 60.0, change=0.0), trend=dim("BEAR"))
        self.assertNotEqual(P.classify(mixed, panic_seen=True)["phase"], "P3")

    def test_phase_meta_is_complete(self):
        for p in ("P0", "P1", "P2", "P3"):
            self.assertIn("cn", C.PHASE_META[p])
            self.assertIn(p, C.PHASE_RULES)
        self.assertEqual(set(C.DIMENSION_ORDER), set(C.DIMENSION_META))


class IndicatorTests(unittest.TestCase):
    def test_at_is_point_in_time(self):
        import pandas as pd
        s = pd.Series([1.0, 2.0, 3.0, 9.0],
                      index=pd.to_datetime(["2026-01-01", "2026-01-02",
                                           "2026-01-03", "2026-01-31"]))
        val, chg = I.at(s, pd.Timestamp("2026-01-30"), window=1)
        self.assertEqual(val, 3.0)       # 9.0 on Jan 31 must NOT leak in
        self.assertEqual(chg, 1.0)
        self.assertEqual(I.at(s, pd.Timestamp("2025-01-01"))[0], None)


class PayloadTests(unittest.TestCase):
    def test_script_tag_is_escaped(self):
        out = _clean_dumps({"x": "</script><b>ok</b>", "nan": float("nan")})
        self.assertNotIn("</script>", out)
        self.assertIn("<\\/script>", out)
        self.assertIn("null", out)


if __name__ == "__main__":
    unittest.main()
