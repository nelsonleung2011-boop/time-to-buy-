# Time to Buy? — 美股熊市底部监控 / US Bear-Market Bottom Monitor

A **static dashboard + daily cloud data pipeline** that tracks where the US
stock market sits in the panic-and-bottom cycle. GitHub Actions collects public
financial data every day after the US close, recomputes seven observable
dimensions, classifies the market into **P0 / P1 / P2 / P3**, rebuilds
`index.html` and commits the refreshed data back to the repository. GitHub Pages
then serves it — **no server, no API keys, no browser-side data calls**.

> This is a **condition detector**, not a return forecast, not a buy signal and
> not investment advice.

---

## 1. How to check whether it has been updated

This is the first thing the page shows. Four tiles sit at the top of the dashboard:

| Tile | What it tells you |
|---|---|
| **Last updated / 最后更新** | Exact UTC timestamp of the last pipeline build, its age ("3.2 h ago"), local time, and a live badge: `FRESH` (<36 h), `LAGGING` (36–72 h), `STALE` (>72 h). The badge is computed **in your browser from the embedded build time**, so even a browser-cached page cannot pretend to be fresh. |
| **Data as of / 数据截至** | The last US trading close used by the engine, its weekday and its age in calendar days. |
| **Current phase / 当前阶段** | P0–P3 plus the Chinese phase name. |
| **Cloud run / 云端采集** | How many sources were updated vs kept from cache on the last run, and the next scheduled run time. |

Additional checks built into the page:

- **A red notice banner** appears automatically if the snapshot is older than
  72 hours or the market data is more than 5 calendar days old.
- **"Check for newer data"** button compares the embedded snapshot with
  `data/latest.json` on the server. If a newer build exists, it tells you to
  hard-refresh (`Ctrl+F5`). On a local `file://` copy it says so explicitly.
- **Data & Sources tab** lists the **actual last observation date** of every
  cache file, its age and a `STALE` flag (>10 days for daily series, >45 days
  for the monthly CAPE series), plus the per-source result of the last cloud
  run. This is the honest answer to "is the data moving?".
- Outside the page: check the GitHub **Actions** tab and the timestamp of the
  last commit to `data/`. Every successful run creates a commit named
  `chore: daily market data refresh YYYY-MM-DD`.

**If it looks stuck**, work through this list:

1. `.github/workflows/daily.yml` exists in the repo. Hidden folders are easily
   dropped by drag-and-drop upload — verify it in the repo's Code tab.
2. **Settings → Actions → General → Workflow permissions = Read and write**
   (otherwise the job cannot commit refreshed data).
3. **Settings → Pages → Build and deployment → Deploy from a branch → `main` / `/ (root)`**.
4. Actions tab → **Daily market data refresh → Run workflow** to trigger a
   manual run; wait ~1–2 minutes, then hard-refresh the page with `Ctrl+F5`.
5. GitHub **pauses scheduled workflows after ~60 days of repository inactivity**.
   Any push (or a manual run) reactivates them. Scheduled runs can also be
   delayed by queueing on GitHub's side.
6. Weekends and US market holidays legitimately keep `Data as of` unchanged —
   `Last updated` should still move on every scheduled run.

---

## 2. Files to upload to GitHub

Upload **the contents of this folder** (the folder itself becomes the repository
root). Every file below is needed; nothing here is generated at runtime by the
browser.

```
time to buy？/
├── index.html                     <- the website (generated, data embedded)
├── dashboard_template.html        <- editable HTML/CSS/JS shell
├── README.md
├── LICENSE
├── requirements.txt
├── .gitignore
├── .github/
│   └── workflows/
│       └── daily.yml              <- THE daily cloud job (hidden folder!)
├── pipeline/
│   ├── __init__.py
│   ├── config.py                  <- symbols, sources, pre-registered thresholds
│   ├── fetch_data.py              <- Yahoo / FRED / CNN / multpl collectors
│   ├── indicators.py              <- seven-dimension builder
│   ├── phases.py                  <- P0–P3 classifier
│   └── build_dashboard.py         <- one-command orchestrator
├── data/
│   ├── latest.json                <- full snapshot payload (machine readable)
│   ├── history.csv                <- append-only daily phase log
│   ├── sources.json               <- per-source refresh report
│   ├── raw/*.csv                  <- cached daily price series
│   └── macro/observations.json    <- cached FRED / CNN / CAPE observations
└── tests/
    └── test_phases.py
```

> **Folder / repository name.** Windows and GitHub both forbid the ASCII `?`
> character in folder and repository names. The local folder therefore uses the
> visually identical full-width character (`time to buy？`) and the project is
> titled **Time to Buy?** everywhere. Use **`time-to-buy`** as the GitHub
> repository name (letters, digits, `-`, `_`, `.` only). The folder name itself
> is never uploaded — only its contents.

**Quick path (no git CLI):** create an empty public repo named `time-to-buy` →
"uploading an existing file" → select **all** files above, including the hidden
`.github` folder → commit. Then follow steps 2–4 in section 1.

**With git:**

```bash
cd "time to buy？"
git init
git add .
git commit -m "init: Time to Buy? bear-market bottom monitor"
git branch -M main
git remote add origin https://github.com/<you>/time-to-buy.git
git push -u origin main
```

The site will be at `https://<you>.github.io/time-to-buy/`.

---

## 3. The seven dimensions / 七个维度

All thresholds are fixed constants in `pipeline/config.py` and are published in
`data/latest.json` and on the dashboard. Nothing is fitted to today's reading.

| # | 维度 | Dimension | Measure | Source | Key thresholds |
|---|---|---|---|---|---|
| 1 | 信用利差 | Credit spreads | ICE BofA US High Yield OAS | FRED `BAMLH0A0HYM2` (fallback: HYG/LQD ratio proxy) | easing ≤ −0.15pp/20d; widening ≥ +0.15pp; elevated ≥ 3.5% |
| 2 | 国债收益率 | Treasury yields | 10Y nominal + 10Y TIPS real yield | Yahoo `^TNX` / FRED `DGS10`, `DFII10` | easing = either yield falls ≥ 0.15pp in 20 observations |
| 3 | VIX 期限结构 | VIX term structure | VIX9D / VIX30D − 1 (backwardation) | Yahoo `^VIX`, `^VIX9D` | panic: VIX ≥ 30 or 9D/30D > 1.05 |
| 4 | 投资者情绪 | Investor sentiment | CNN Fear & Greed 0–100 | CNN dataviz graphdata | extreme fear < 25; fear < 45; complacent > 55 |
| 5 | 市场宽度 | Market breadth | % of 11 SPDR sector ETFs above their 50DMA | Yahoo (XLC…XLY) | panic < 30%; weak < 40%; confirmation ≥ 50% |
| 6 | 趋势反转 | Trend reversal | SPY vs 50DMA / 200DMA, 20d momentum, 50DMA slope | Yahoo `SPY` | confirmed: above both MAs; recovering: above 50DMA only |
| 7 | 长期估值 | Long-term valuation | Shiller CAPE (monthly) | multpl.com | cheap ≤ 15x; fair 15–30x; expensive ≥ 30x |

**Point-in-time rule:** at any date D, only observations on or before D are
used. A series that did not exist at D reports `NO DATA` — it is never
back-filled, and a `NO DATA` check can never count as satisfied.

---

## 4. The four phases / 四个阶段

| Phase | 名称 | Rule |
|---|---|---|
| **P0** | 观察 · Observation | Default: fewer than two fear conditions, or insufficient data. |
| **P1** | 恐慌出清 · Panic clearing | ≥ 2 of 3 fear conditions: VIX term structure, sentiment, breadth. |
| **P2** | 底部酝酿 · Bottom brewing | ≥ 2 of 4 improvements (credit easing, rates easing, breadth improving ≥ 5pp/20d, price structure stabilising) **and** a P1 episode within the last 120 sessions. |
| **P3** | 趋势确认 · Trend confirmed | ≥ 1 of 2 confirmations (breadth ≥ 50%, SPY above both 50/200DMA), price above its 50DMA, **and** a P1 episode within the last 120 sessions. |

The 120-session "panic memory" is deliberate: requiring fear and trend
confirmation on the same day would make P3 unreachable in a real recovery. A
confirmed cycle therefore stays in P3 until that memory expires (then it falls
back to P0), and a fresh P1 restarts the cycle. The highest satisfied phase
wins. The dashboard shows every check with its status, its raw detail and its
source date.

---

## 5. Daily cloud collection

`.github/workflows/daily.yml` runs at **06:30 UTC, Tuesday–Saturday**
(≈ 01:30 EST / 02:30 EDT after the Mon–Fri US close):

1. Checkout → Python 3.11 → `pip install -r requirements.txt`.
2. `python -m unittest discover -s tests -v` (offline unit tests).
3. `python pipeline/build_dashboard.py` → fetch → validate+merge → compute →
   write `data/latest.json`, `data/history.csv`, `data/sources.json`, `index.html`.
4. Health check (payload injected, build timestamp recent, source counts).
5. Commit `data/` and `index.html` back to `main`.

All endpoints are public and **no GitHub secrets are needed**:
Yahoo Finance chart API, FRED `fredgraph.csv`, CNN Fear & Greed graphdata,
multpl.com monthly Shiller CAPE.

**Cache-safety:** a failing or truncated source never overwrites good cached
data. Price histories are validated before replacement (length, last date,
positive closes); macro observations are merged by date. Failures are recorded
as `KEPT CACHE` with a reason in `data/sources.json` and shown on the dashboard.

---

## 6. Run locally

Python 3.11+ with `pandas` and `numpy`:

```bash
pip install -r requirements.txt
python pipeline/build_dashboard.py                     # live refresh + publish
python pipeline/build_dashboard.py --offline           # cached data, no network
python pipeline/build_dashboard.py --as-of 2026-03-31  # score a past session
python -m unittest discover -s tests -v               # offline unit tests
python pipeline/fetch_data.py                         # refresh caches only
```

Open `index.html` directly — the data is embedded, so it works offline and on
GitHub Pages. Edit the layout/CSS/renderer in `dashboard_template.html`, then
rebuild; never hand-edit `index.html` because the next build overwrites it.

---

## 7. Method, limitations, honesty

- **No prediction.** The engine reports observable states and pre-registered
  rules. There is no trained model, no target variable, no backtested return
  claim and no position sizing.
- **Revision risk.** FRED and multpl serve *latest-revised* vintages rather than
  real-time vintages, and macro observations are aligned to their nominal
  observation date. Historical phase rows therefore carry revision risk; they
  are context, not evidence of a trading edge.
- **Short sentiment history.** CNN Fear & Greed publishes roughly one year of
  history. Older dates show `NO DATA` for sentiment instead of a fabricated
  value.
- **CAPE is monthly** and slow-moving; it is context for the long-term valuation
  dimension, not a timing trigger.
- **Staleness is visible on purpose.** The build timestamp, the data as-of date,
  per-source last observations and the last-run status are all published rather
  than hidden.
- **Not investment advice.** Educational research tool only. Market data can be
  wrong, delayed or revised; always verify against primary sources.

---

## 8. Credits

Architecture follows the reference project `ETF_Timing_Dashboard`: static
self-contained HTML with an embedded JSON payload, a cache-safe Python fetch
layer, point-in-time series alignment, pre-registered thresholds, and a
scheduled GitHub Actions job that commits refreshed data back to the repo.
This repository is a clean standalone rebuild focused on one question only:
**where are we in the bear-market bottom sequence?**
