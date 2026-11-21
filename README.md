# Time to Buy? — 美股熊市底部监控 / US Bear-Market Bottom Monitor

**Time to Buy?** is a dashboard that answers one question: *where are we in the
US bear-market bottom sequence?* It tracks seven observable dimensions of
market stress and recovery, and classifies each trading day into one of four
bottom-formation stages — **P0 / P1 / P2 / P3**.

Public financial data is collected in the cloud once a day after the US market
close, so the page always reflects the most recent completed session.

> This is a **condition detector**, not a return forecast, not a buy signal and
> not investment advice.

---

## 1. Checking whether it has been updated

Freshness is the first thing the dashboard shows. Four tiles sit at the top:

| Tile | What it tells you |
|---|---|
| **Last updated / 最后更新** | Exact UTC timestamp of the last data build, its age ("3.2 h ago"), your local time, and a live badge: `FRESH` (<36 h), `LAGGING` (36–72 h), `STALE` (>72 h). The badge is calculated in your browser from the build time, so a cached page cannot pretend to be fresh. |
| **Data as of / 数据截至** | The last US trading close used by the engine, its weekday, and its age in calendar days. |
| **Current phase / 当前阶段** | The active P0–P3 stage and its Chinese name. |
| **Cloud run / 云端采集** | Result of the latest daily collection and when the next one is due. |

The page also self-checks:

- A **red notice banner** appears automatically if the snapshot is older than
  72 hours or the market data is more than 5 calendar days old.
- **"Check for newer data"** compares the page against the published snapshot
  and tells you to hard-refresh (`Ctrl+F5`) if a newer one exists.
- The **Data & Sources** tab lists the real last observation date and age of
  every input, with a `STALE` flag, so you can confirm the numbers are actually
  moving.

> Weekends and US market holidays legitimately keep *Data as of* unchanged;
> *Last updated* should still move on every scheduled run.

---

## 2. The seven dimensions / 七个维度

The system reads seven dimensions, each scored against fixed, pre-registered
thresholds that are published on the dashboard. Nothing is tuned to the current
reading.

| # | 维度 | Dimension | What it measures | Trigger levels |
|---|---|---|---|---|
| 1 | 信用利差 | Credit spreads | US high-yield option-adjusted spread | widening ≥ +0.15pp / 20d; elevated ≥ 3.5%; easing ≤ −0.15pp |
| 2 | 国债收益率 | Treasury yields | 10Y nominal and 10Y real (TIPS) yields | easing when either falls ≥ 0.15pp over 20 observations |
| 3 | VIX 期限结构 | VIX term structure | 9-day vs 30-day VIX (backwardation) | panic at VIX ≥ 30 or 9D/30D > 1.05 |
| 4 | 投资者情绪 | Investor sentiment | CNN Fear & Greed index (0–100) | extreme fear < 25; fear < 45; complacent > 55 |
| 5 | 市场宽度 | Market breadth | Share of 11 sector ETFs above their 50-day average | panic < 30%; weak < 40%; confirmation ≥ 50% |
| 6 | 趋势反转 | Trend reversal | S&P 500 vs 50/200-day averages, momentum, slope | confirmed above both averages; recovering above the 50-day |
| 7 | 长期估值 | Long-term valuation | Shiller CAPE (monthly) | cheap ≤ 15x; fair 15–30x; expensive ≥ 30x |

**Point-in-time rule:** for any given day, only data available on or before
that day is used. A missing series reports `NO DATA` — it is never back-filled,
and a `NO DATA` check can never count as satisfied.

---

## 3. The four phases / 四个阶段

| Phase | 名称 | Rule |
|---|---|---|
| **P0** | 观察 · Observation | Default — fewer than two fear conditions, or insufficient data. |
| **P1** | 恐慌出清 · Panic clearing | ≥ 2 of 3 fear conditions: VIX term structure, sentiment, breadth. |
| **P2** | 底部酝酿 · Bottom brewing | ≥ 2 of 4 improvements (credit easing, rates easing, breadth improving ≥ 5pp / 20d, price stabilising) **and** a P1 episode within the last 120 sessions. |
| **P3** | 趋势确认 · Trend confirmed | ≥ 1 of 2 confirmations (breadth ≥ 50%, price above both 50/200-day averages), price above its 50-day average, **and** a P1 episode within the last 120 sessions. |

The 120-session "panic memory" is deliberate: demanding fear and trend
confirmation on the same day would make P3 unreachable in a real recovery. A
confirmed cycle stays in P3 until that memory expires (then it falls back to
P0), and a fresh P1 restarts the cycle. The highest satisfied phase wins.

The dashboard shows every check with its status, its raw reading and the date
of the underlying data, so any classification can be audited.

---

## 4. How to read it

- **P0–P1** describe stress, not opportunity. Panic clearing is a necessary
  precondition, not a buy signal.
- **P2** means the panic is easing and market internals are starting to repair.
- **P3** means a trend has been confirmed after a panic episode.
- The seven dimension cards and the phase checklists explain *why* the current
  phase was assigned; the History tab shows how the classification evolved.

---

## 5. Limitations / 免责声明

- **No prediction.** The system reports observable states against fixed rules.
  There is no trained model, no return forecast, no backtested edge and no
  position sizing.
- **Context, not a signal.** Long-term valuation (CAPE) is monthly and
  slow-moving; it provides context, not a timing trigger. Historical phase rows
  carry data-revision risk and should be read as context, not evidence of a
  trading edge.
- **Gaps are shown honestly.** Some sentiment series publish only about one
  year of history; older dates show `NO DATA` instead of a fabricated value.
  Staleness is never hidden — build time, data date and per-source last
  observations are all published.
- **Not investment advice.** Educational research tool only. Market data can be
  wrong, delayed or revised; always verify against primary sources.
