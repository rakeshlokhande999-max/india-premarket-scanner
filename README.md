# India Pre-Market Scanner

A working rule-based scanner for NSE-listed Nifty-50 stocks: real price/volume
history, real NSE pre-open and FII/DII data, real news headlines, scored
against a weighted momentum model, with a backtest store so its own hit rate
is measurable instead of assumed.

It also includes an **AI Short-Term Momentum & Upper-Circuit Scanner**
(app-info.md's spec) that scans a much broader universe for a 1-2 hour
upward-momentum read with a distance/probability estimate toward each
stock's real, exchange-reported upper circuit where a static one exists.
See "AI Momentum & Upper-Circuit Scanner" below.

**Read this before treating any output as advice.** Every number in this
tool is either a genuine calculation on genuine data, or explicitly marked
`null`/"unavailable" when the real input couldn't be fetched -- never a
placeholder standing in for a real number. It is still a probabilistic,
rule-based model that can be wrong, has not been reviewed against SEBI
Research Analyst (2014) / Investment Adviser (2013) regulations, and is
built for personal, single-user use. Do not point other people at its
output without resolving that regulatory question first.

## What it actually uses (no API keys required for any of this)

| Need | Source | Notes |
|---|---|---|
| Nifty-50 constituents + sector | NSE's public archive CSV | Always current, no hardcoded list to go stale |
| OHLCV / index levels | `yfinance` | Free, ~15-minute-delayed NSE quotes -- not tick-real-time |
| Pre-open snapshot | NSE's own `market-data-pre-open` endpoint | Undocumented, can change without notice; only meaningful ~9:00-9:15 IST |
| FII/DII cash flows | NSE's own `fiidiiTradeReact` endpoint | Usually one day behind (T-1) |
| News | Moneycontrol / ET Markets / Business Standard RSS | Keyword-scored, not NLP sentiment |

Upgrade points are wired but unused: `.env` has empty `BROKER_API_KEY` /
`BROKER_API_SECRET` / `BROKER_ACCESS_TOKEN` for swapping in Kite Connect,
Upstox, or Angel One SmartAPI when you want true real-time quotes and
order-book depth instead of delayed data; `NEWS_API_KEY` for a paid
news/sentiment API if keyword scoring proves too coarse.

## Setup

```bash
cd india-premarket-scanner
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # defaults work as-is; edit only if you add real keys later
python -m pytest tests/ -q   # 10 tests, no network required
```

## Usage

```bash
python scanner.py scan               # run any time; best run right after 8:00 IST
python scanner.py preopen            # only meaningful 9:00-9:15 IST -- cross-checks the scan against NSE's real pre-open snapshot
python scanner.py backfill           # run once daily (e.g. next morning) -- fills T+1 actual outcomes, never same-day
python scanner.py stats              # current backtest accuracy: target-1/2 hit rate, stop-loss rate, MFE/MAE
python scanner.py momentum           # AI Momentum / Upper-Circuit research run -- best during 09:15-15:30 IST
python scanner.py momentum-backfill  # fills due 15/30/60/120-min horizon outcomes; run every ~15 min in market hours
python scanner.py momentum-stats     # current momentum-model calibration: predicted vs. realized per horizon
streamlit run app.py                 # dashboard -- reads what the CLI wrote (except the momentum tab's own buttons)
```

`scan` writes `data/latest_scan.json` (read by the dashboard) and inserts
every surfaced candidate into `data/scanner.db` (SQLite) for backtesting.

## Scheduling it for real

Cron runs in the machine's local timezone -- confirm with `timedatectl` (Linux) or
set `TZ=Asia/Kolkata` explicitly in the crontab if the host isn't IST. See
`crontab.example`.

## How the score is built

Ten weighted components (`config.SCORE_WEIGHTS`, sums to 1.0): market trend,
sector momentum, news catalyst, technical trend, price action, volume,
pre-open strength, institutional (FII/DII) flow, momentum indicators,
risk/reward. Each is 0-10, computed from real fetched data. If a component's
real input isn't available (most commonly `pre_open_strength` outside the
9:00-9:15 IST window), it's dropped and the remaining weights are
renormalized -- the composite score never silently treats "no data" as
"neutral," and `unavailable_components` on every candidate shows exactly
what was missing.

Targets/stop-loss are ATR multiples off the last close (0.8x / 1.5x / 2.5x
ATR for targets 1/2/3, 1x ATR for the stop) -- a standard technical
heuristic computed from real historical volatility, not an invented number,
and not a promise those levels get hit.

Regime and risk filters from the original spec are enforced in code, not
just described: `HIGH RISK`/`BEARISH` regimes cap candidates at 3 instead of
10; `EXTREME` risk (very negative news, illiquid turnover) is auto-rejected;
below a 60 composite score, nothing is shown and the scan reports
`no_trade_reason` instead of forcing a list.

## AI Momentum & Upper-Circuit Scanner

`momentum.py` implements app-info.md's primary objective: on "Run Market
Research" (a button in the dashboard's first tab, or `scanner.py momentum`
from cron), it looks for stocks showing a short-term (1-2 hour)
upward-momentum signal, with a distance/probability read toward each
stock's real, exchange-reported upper circuit where one applies.

**Two-stage funnel**, so NSE's undocumented, unauthenticated, per-symbol
`quote-equity` endpoint never gets hammered for the whole universe:

1. **Stage 1 (cheap, one batched call)** -- ~1 year of daily bars for the
   *entire* broad universe (Nifty Total Market + Nifty Microcap 250, ~900
   names) via one `yfinance` batch download, feeding the same
   `indicators.compute_indicators()` the daily scanner uses. No
   network round-trip per name.
2. **Stage 2 (narrow, expensive)** -- only the top `SCANNER_MOMENTUM_UNIVERSE_LIMIT`
   names (default 60) by a coarse day-change x relative-volume pre-filter
   get a live NSE quote (real upper-circuit price) and a batched intraday
   5-minute-bar fetch (VWAP, opening-range breakout, EMA9/20, Bollinger %B).

**What it deliberately does not do**, per your own scope decision to hold
off on anything that needs a broker feed:

- No order-book depth / bid-ask spread / buy-side pressure -- reported as
  `unavailable_no_data_source` in `manipulation_checks`, never guessed.
- No continuous/live/websocket monitoring -- "Run Market Research" /
  "Refresh Data" are explicit, on-demand actions (or cron, see
  `crontab.example`), not a streaming feed. Wire up `BROKER_API_KEY` etc.
  first if you want true live monitoring later.
- No social-sentiment / search-trend data -- no source is configured, so
  it's marked unavailable rather than fabricated.
- Horizon probabilities (15/30/60/120 min) are a transparent, documented
  heuristic (`momentum_scoring.horizon_probabilities`), **not yet
  calibrated** against historical outcomes -- there's no backfilled
  intraday history on a fresh install. `scanner.py momentum-stats` /
  the dashboard's Backtest tab report the real predicted-vs-realized
  comparison once enough signals have been backfilled.

**A real-world reliability note**: NSE's `quote-equity` endpoint (the
source of the actual upper-circuit price) sits behind a stricter WAF than
`fiidiiTradeReact`/`market-data-pre-open` and can return 403 even with a
warmed session and browser-shaped headers -- observed in testing, not
hypothetical. When it fails for a name, that candidate simply shows
`upper_circuit: N/A` / `uc_probability_pct: N/A` for that run (surfaced in
`nse_quote_failures`) rather than a stale or invented circuit price; its
opportunity score, technical/volume/catalyst read, and targets are
unaffected since those don't depend on this endpoint. Also note that most
large/F&O-eligible names (most of Nifty-50) genuinely have **no static
circuit at all** (NSE reports `pPriceBand: "No Band"`) -- that's not a
failure, it's the exchange's own answer, and the app shows it as such.

## Known limitations (real ones, not disclaimers)

- **yfinance is delayed**, not tick-real-time. Fine for an 8 AM directional
  read; not for order execution.
- **News-to-stock matching is a coarse substring heuristic** on company-name
  tokens. It over-matches sometimes (RSS article summaries often carry
  "related stocks" boilerplate that pulls in unrelated names) and under-matches
  when a headline doesn't use the exact company name. Treat `news_tags` as
  "worth a manual check," not a verified catalyst.
- **FII/DII is a single day's snapshot**, not a multi-day trend -- the spec's
  institutional sub-score is only as good as one day's read.
- **No options/OI data.** Left out entirely rather than approximated, per the
  spec's own instruction not to use derivatives data you can't trust.
- **No ML.** The spec calls for XGBoost/LightGBM; there's no labeled
  history yet to train on. `backfill` is what builds that history --
  revisit ML only after months of real backtest rows exist.
- **The Nifty-50 sector-momentum score is a same-universe proxy** (average
  daily change of scanned constituents in a sector), not an official NSE
  sector index.
- **The intraday relative-volume read is an approximation**: today's
  session volume-so-far vs. the 20-day average, scaled to the elapsed
  fraction of the session -- not a true same-time-yesterday comparison
  (that needs stored intraday history across many days, not collected
  yet).
- **No order-book/order-flow, no live/websocket monitoring, no
  social-sentiment data** in the AI Momentum Scanner -- deferred until a
  broker feed is configured; see that section above.
- **Horizon probabilities (15/30/60/120 min) are uncalibrated** on a fresh
  install -- see the AI Momentum Scanner section above.

## Project layout

```
config.py            env-var config, weights, endpoints
market_data.py        Nifty-50 + broad universe, OHLCV (single + batched), index snapshot (yfinance)
nse_live.py           NSE pre-open + FII/DII + per-symbol live quote/circuit limits (direct NSE JSON endpoints)
news.py                RSS fetch + keyword catalyst scoring
indicators.py          daily EMA/RSI/MACD/ADX/ATR/rel.volume + intraday VWAP/ORB/EMA9-20/Bollinger (real `ta` calcs)
scoring.py             pre-market daily model: weighted composite, regime, targets, risk classification
momentum_scoring.py    AI Momentum Scanner model: UC distance/probability, Final Opportunity Score, horizon estimates
storage.py             SQLite store: daily predictions/backtest + momentum signals/backtest
momentum.py            AI Momentum Scanner orchestration: two-stage funnel, "Run Market Research", horizon backfill
scanner.py             CLI: scan / preopen / backfill / stats / momentum / momentum-backfill / momentum-stats
app.py                 Streamlit dashboard (AI Momentum Scanner tab is interactive; the rest is read-only)
tests/                  no-network unit tests for the math/logic layer
app-info.md            the original feature spec, with an implementation-status tracker at the bottom
```
