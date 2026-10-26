# Master Prompt — AI Short-Term Upper Circuit Prediction Engine

I already have an existing Indian stock-market web application called **Price Band Screener**. The current application displays Indian equities, price bands, symbols, company names, sectors, prices and day changes.

I want to upgrade this application into an **AI-powered Short-Term Stock Movement Research & Prediction Platform**.

## PRIMARY OBJECTIVE

When the application is opened and the user clicks:

**“Run Market Research”**

the system must automatically research the Indian stock market and identify stocks that have a **high probability of making a strong upward move during the next 1–2 hours**, including candidates that may potentially approach their exchange-defined upper circuit.

Do NOT claim that any stock is guaranteed to hit Upper Circuit.

The system must provide:

* Probability score
* Confidence score
* Expected short-term movement
* Current price
* Upper Circuit price
* Distance from Upper Circuit
* Volume confirmation
* Buy-side pressure
* News/sentiment
* Technical signals
* Order-book signals where legally and technically available
* Catalyst/reason
* Risk level
* Data freshness
* Exact timestamp of analysis

The output should be a **ranked research list**, not a guaranteed prediction.

---

# 1. MARKET UNIVERSE

Research as broad an Indian equity universe as the available data sources legally and technically allow.

Prefer:

* NSE listed stocks
* BSE listed stocks
* Nifty Total Market
* Nifty 500
* Nifty Midcap
* Nifty Smallcap
* Nifty Microcap where reliable data is available
* Other actively traded listed equities

Remove duplicates between NSE and BSE where appropriate.

Exclude or separately flag:

* Suspended securities
* Stocks with stale prices
* Stocks with insufficient data
* Stocks with extremely low liquidity
* Stocks with abnormal data quality
* Stocks where reliable real-time data is unavailable

Never fabricate missing market data.

---

# 2. DATA COLLECTION ENGINE

Build a modular data-provider architecture.

Do NOT depend on one website.

Use multiple reliable sources/APIs wherever licensing and terms permit.

Possible data categories:

### Exchange / Market Data

Collect:

* LTP
* Previous close
* Open
* High
* Low
* Volume
* Average volume
* VWAP
* Day change %
* Intraday change %
* Upper circuit limit
* Lower circuit limit
* Market status
* Trading status
* Delivery data where available
* Bid/ask data where available
* Order-book imbalance where available

Primary preference should be official exchange/licensed market-data sources.

### News

Collect recent news from reliable financial sources.

Look for:

* Company announcements
* Earnings
* Order wins
* New contracts
* Government orders
* Regulatory approvals
* Product launches
* Management announcements
* Fundraising
* M&A
* Strategic partnerships
* Capacity expansion
* Promoter activity
* Corporate actions
* Sector news
* Government policy impact

Prioritize recent information.

### Corporate Filings

Research:

* NSE/BSE corporate announcements
* Results
* Investor presentations
* Exchange filings
* Shareholding changes
* Promoter transactions
* Bulk/block deals
* Credit-rating changes
* Important regulatory filings

### Technical Market Data

Calculate:

* RSI
* MACD
* EMA 9
* EMA 20
* EMA 50
* SMA 20
* SMA 50
* VWAP
* ATR
* ADX
* Bollinger Bands
* Relative volume
* Volume acceleration
* Price momentum
* Intraday breakout
* Previous day high breakout
* Opening range breakout
* Support/resistance
* Gap-up strength
* Trend strength

Do not use indicators individually.

Combine multiple signals.

---

# 3. REAL-TIME DATA REQUIREMENT

Every research result must show:

**Data as of: DD MMM YYYY, HH:MM:SS IST**

Also show:

**Data freshness: X seconds/minutes old**

If the data is delayed, clearly display:

> Delayed data — prediction reliability reduced.

Never present delayed data as real-time.

If real-time market data is unavailable, explicitly show:

> Real-time prediction unavailable — using delayed market data.

---

# 4. UPPER CIRCUIT ANALYSIS

For every candidate calculate:

Current Price

Upper Circuit Price

Distance to Upper Circuit

Percentage required to reach Upper Circuit

Formula:

Distance % =
((Upper Circuit Price - Current Price) / Current Price) × 100

Example:

Current Price = ₹42.50
Upper Circuit = ₹44.60

Distance = 4.94%

Display:

**UC Distance: 4.94%**

Prioritize stocks where:

* Momentum is strong
* Volume is increasing
* Price is moving toward the circuit
* Buy-side pressure is strong
* There is a credible catalyst
* Liquidity is sufficient
* Technical breakout is confirmed

Do NOT assume that a low-priced stock is more likely to hit Upper Circuit.

---

# 5. SHORT-TERM MOMENTUM ENGINE

The prediction engine should focus specifically on the next:

**15 minutes**
**30 minutes**
**60 minutes**
**120 minutes**

Generate separate probabilities.

Example:

| Time Horizon | Probability |
| ------------ | ----------: |
| 15 min       |         82% |
| 30 min       |         78% |
| 60 min       |         71% |
| 120 min      |         64% |

These are model probabilities, NOT guarantees.

---

# 6. AI SCORING MODEL

Create a transparent scoring system from 0–100.

Suggested scoring:

### Momentum — 20 points

Consider:

* Intraday price acceleration
* Short-term trend
* Breakout strength
* EMA alignment
* VWAP position

### Volume — 20 points

Consider:

* Relative volume
* Volume spike
* Volume acceleration
* Volume compared with historical average

### Order Flow — 15 points

Where reliable order-book data exists:

* Bid/ask imbalance
* Buy quantity
* Sell quantity
* Bid absorption
* Ask absorption
* Market depth

### Catalyst / News — 15 points

Consider:

* Positive company announcement
* Order win
* Results
* Corporate action
* Government announcement
* Sector catalyst
* Institutional activity

### Technical Breakout — 10 points

Consider:

* Resistance breakout
* Previous high breakout
* VWAP breakout
* Opening-range breakout
* Consolidation breakout

### Market/Sector Strength — 10 points

Compare:

* Nifty
* Bank Nifty
* Relevant sector index
* Peer stocks
* Sector momentum

### Liquidity / Risk — 10 points

Consider:

* Average traded volume
* Bid/ask spread
* Market depth
* Price volatility
* Circuit restrictions

Total:

**100 points**

---

# 7. PREDICTION CLASSIFICATION

Classify candidates:

### 90–100

EXTREME MOMENTUM

### 80–89

VERY HIGH MOMENTUM

### 70–79

HIGH MOMENTUM

### 60–69

MODERATE MOMENTUM

### Below 60

DO NOT PRIORITIZE

Do not show low-confidence stocks in the primary prediction list.

---

# 8. UPPER CIRCUIT PROBABILITY

Create a separate model:

**Upper Circuit Probability Score**

Example:

> UC Probability: 84%

Also display:

> Confidence: High

But only assign High confidence when multiple independent signals agree.

For example:

Strong volume + positive catalyst + breakout + sector strength + buy pressure

should produce higher confidence than:

Price increase alone.

---

# 9. IMPORTANT: AVOID FALSE SIGNALS

The AI must actively detect and penalize:

* Pump-and-dump patterns
* Sudden unexplained spikes
* Extremely low liquidity
* Wide bid/ask spread
* Abnormal price manipulation patterns
* Social-media-only hype
* Unverified news
* Fake news
* Old news being circulated again
* One-minute abnormal candles
* Stocks already extremely extended
* Circuit-to-circuit illiquid stocks
* Data anomalies

If manipulation risk is detected:

**Prediction Status: HIGH RISK**

and reduce the score.

---

# 10. SOCIAL SENTIMENT

Where legally available, analyze public sentiment from:

* Financial news
* Public market discussions
* Public social platforms
* Search trends
* Investor discussions

But NEVER use social sentiment as the only reason to recommend a stock.

Separate:

**Verified News**

from

**Market Sentiment**

and

**Unverified Discussion**

Clearly label each.

---

# 11. MARKET REGIME ANALYSIS

Before ranking stocks, analyze the overall market.

Check:

* NIFTY trend
* BANK NIFTY trend
* India VIX
* Advance/decline ratio
* Sector performance
* Market breadth
* FII/DII activity where available
* Index futures sentiment where legally available
* Global market direction
* Major overnight market movements

Determine:

**MARKET REGIME**

Possible values:

* Strong Bullish
* Bullish
* Neutral
* Weak
* Bearish
* High Volatility

If the overall market is weak, increase the required confidence threshold.

---

# 12. SECTOR ROTATION

Identify sectors showing strongest momentum.

Example:

1. Defence
2. PSU Banks
3. Railways
4. Renewable Energy
5. Infrastructure

Then identify the strongest stocks within those sectors.

Calculate:

**Stock Relative Strength vs Sector**

and

**Stock Relative Strength vs NIFTY**

Prioritize stocks outperforming both their sector and NIFTY.

---

# 13. MULTI-SOURCE VALIDATION

Do not trust a single source.

For important information:

Cross-check where possible.

Example:

News detected:

Source A → Positive
Exchange filing → Confirmed
Source B → Positive

Then:

**Catalyst Confidence: High**

If sources disagree:

**Data Conflict Detected**

Do not hide the conflict.

---

# 14. RANKING ALGORITHM

Create a final score:

**Final Opportunity Score =**

35% Short-Term Momentum
20% Volume Confirmation
15% Catalyst Strength
10% Technical Breakout
10% Sector/Market Strength
5% Liquidity Quality
5% Risk Adjustment

Then apply penalties for:

* Manipulation risk
* Low liquidity
* Wide spread
* Data staleness
* Conflicting information
* Extreme volatility

Sort highest score first.

---

# 15. PRIMARY RESULTS TABLE

Create a new page:

## AI Short-Term Momentum Scanner

Show:

| Rank | Symbol | Company | Price | UC Price | UC Distance | Momentum | Volume | UC Probability | Confidence | Risk |
| ---- | ------ | ------- | ----: | -------: | ----------: | -------: | -----: | -------------: | ---------- | ---- |

Example:

1. ABC — XYZ Ltd — ₹42.50 — ₹44.60 — 4.94% — 91/100 — 3.8x — 84% — High — Medium

Do NOT use fake example data in the live application.

---

# 16. STOCK DETAIL VIEW

When the user clicks a stock, open a detailed research page.

Show:

### Price

Current Price
Previous Close
Day Change
Day Change %
VWAP
Upper Circuit
Lower Circuit

### Prediction

15-Min Probability
30-Min Probability
60-Min Probability
120-Min Probability

### AI Score

Overall Score
Momentum Score
Volume Score
Catalyst Score
Technical Score
Market Score
Liquidity Score
Risk Score

### Why This Stock?

Generate a concise AI explanation.

Example structure:

> Strong intraday momentum supported by 3.8x relative volume, a confirmed resistance breakout and positive sector strength. Recent exchange filing provides an additional catalyst. Current price is 4.9% below the upper circuit.

Never invent reasons.

Every reason must be backed by actual collected data.

---

# 17. SIGNAL TIMELINE

Show an event timeline.

Example:

09:21 — Volume increased 2.1x
09:24 — VWAP breakout
09:28 — Resistance breakout
09:31 — Sector strength increased
09:34 — Positive filing detected
09:36 — Momentum score increased to 87

This allows the user to understand WHY the model changed.

---

# 18. LIVE MONITORING

After generating the list, continuously monitor the shortlisted stocks.

Refresh available data periodically.

If the stock becomes stronger:

> SIGNAL STRENGTHENING

If momentum weakens:

> SIGNAL WEAKENING

If the thesis becomes invalid:

> SIGNAL INVALIDATED

If price approaches Upper Circuit:

> APPROACHING UPPER CIRCUIT

If Upper Circuit is reached:

> UPPER CIRCUIT REACHED

Never continue displaying an old bullish signal after the underlying conditions have changed.

---

# 19. ALERT SYSTEM

Create alerts for:

* Strong breakout
* Volume spike
* Momentum acceleration
* Positive verified news
* UC distance < 2%
* UC distance < 1%
* Signal strengthening
* Signal weakening
* Prediction invalidated

Allow user-configurable thresholds.

---

# 20. RESEARCH OUTPUT

At the end of every scan show:

### Market Summary

Market Regime: Bullish
Strongest Sector: XXXXX
Market Breadth: XXXXX
High Momentum Stocks Found: XX
High Confidence Candidates: XX

Then:

### Top Short-Term Candidates

Show only the highest-quality candidates.

For each candidate show:

**WHY IT IS HERE**

**WHAT CONFIRMS THE SIGNAL**

**WHAT CAN INVALIDATE THE SIGNAL**

**RISK LEVEL**

**DATA FRESHNESS**

---

# 21. DO NOT MAKE GUARANTEES

Never use wording such as:

❌ Guaranteed Upper Circuit
❌ 100% Sure
❌ Guaranteed Profit
❌ निश्चित फायदा
❌ निश्चित Upper Circuit
❌ Buy this stock

Instead use:

✅ High Probability Candidate
✅ Strong Momentum Setup
✅ Potential Upper Circuit Candidate
✅ AI Research Signal
✅ Short-Term Momentum Score
✅ Probability Estimate

The application must clearly state:

> This is an AI-generated market research signal, not a guarantee of future price movement or investment advice.

---

# 22. BACKTESTING ENGINE

This is extremely important.

Do not simply create a prediction score.

Build a historical backtesting system.

For every signal generated historically, record:

* Signal timestamp
* Entry price
* Upper Circuit price
* Volume
* Technical indicators
* Catalyst
* Prediction score
* Predicted probability
* Actual price after 15 min
* Actual price after 30 min
* Actual price after 60 min
* Actual price after 120 min
* Whether Upper Circuit was reached

Calculate:

* Prediction accuracy
* Precision
* Recall
* False-positive rate
* UC prediction accuracy
* Average return
* Maximum adverse movement
* Win rate

Continuously improve the scoring model based on historical performance.

---

# 23. CONFIDENCE CALIBRATION

If the model says:

**80% probability**

historical backtesting should verify whether approximately 80% of similar signals actually achieved the defined outcome.

Do not display arbitrary probability numbers.

Probabilities must be calibrated using historical results.

---

# 24. DATA FAILURE HANDLING

If a data provider fails:

Do not crash the application.

Show:

> Market data provider unavailable.

Use another configured provider where permitted.

If insufficient data exists:

> Insufficient data for reliable prediction.

Do not generate a fake score.

---

# 25. API ARCHITECTURE

Build the system using modular services:

```text
Market Data Service
        ↓
News Service
        ↓
Corporate Filings Service
        ↓
Technical Analysis Engine
        ↓
Volume Analysis Engine
        ↓
Order Flow Engine
        ↓
Sentiment Engine
        ↓
Market Regime Engine
        ↓
Stock Scoring Engine
        ↓
Prediction Engine
        ↓
Risk Engine
        ↓
Ranking Engine
        ↓
AI Research Explanation
        ↓
Dashboard
```

Every data provider must be replaceable.

Do not hard-code the entire application around one API.

---

# 26. DATABASE

Store historical snapshots.

Suggested tables:

```text
stocks
market_snapshots
intraday_prices
volume_snapshots
technical_indicators
corporate_events
news_events
market_regime
sector_strength
prediction_signals
prediction_results
signal_events
backtest_results
data_provider_status
```

Store timestamps in UTC internally and display in:

**Asia/Kolkata / IST**

---

# 27. UI REQUIREMENTS

Use the existing application's design language.

Keep the current:

* Price Band Screener
* Price category tabs
* Search
* Stock table
* Clean financial dashboard

Add:

**AI Momentum Scanner**

and

**Run Market Research**

button.

Use a clean professional financial-terminal style.

Add filters:

* Minimum Score
* Minimum Probability
* Sector
* Market Cap
* Price
* Volume
* UC Distance
* Risk
* Confidence
* Liquidity

---

# 28. TOP-5 PRIORITY VIEW

At the top of the dashboard show:

## Top 5 Short-Term Momentum Candidates

For each:

**Rank #1**

Company
Current Price
Upper Circuit
UC Distance
15m Probability
30m Probability
60m Probability
120m Probability
AI Score
Confidence
Risk
Main Catalyst
Volume Multiple

This should be the first thing the user sees after running research.

---

# 29. RESEARCH REFRESH

Provide:

**Run Research**

**Refresh Data**

**Auto Monitor**

buttons.

Show:

> Last research: 24 Aug 2026, 04:17 PM IST

> Next refresh: XX seconds

Never silently use old data.

---

# 30. FINAL AI RESPONSE FORMAT

After completing the market scan, the AI should return:

## Market Status

Market Regime:
NIFTY Trend:
Market Breadth:
Strongest Sector:

## Top Short-Term Candidates

1. Stock

   * Current Price:
   * Upper Circuit:
   * UC Distance:
   * 15m Probability:
   * 30m Probability:
   * 60m Probability:
   * 120m Probability:
   * AI Score:
   * Confidence:
   * Risk:
   * Volume:
   * Catalyst:
   * Technical Confirmation:
   * Why selected:
   * What could invalidate the signal:

Repeat for the top candidates.

## Important

Do not simply return stocks because they have increased in price.

The objective is to identify stocks where **multiple independent signals are simultaneously aligned toward strong short-term upward momentum**.

The system should prioritize:

**Verified catalyst + strong volume + price momentum + technical breakout + sector strength + market strength + sufficient liquidity + proximity to Upper Circuit**

rather than simply:

**Low price + high percentage change.**

---

# 31. MOST IMPORTANT IMPLEMENTATION RULE

The system must behave like a **real-time quantitative research engine**, not a simple stock screener.

Before producing a candidate, ask internally:

1. Is the market data fresh?
2. Is the stock liquid enough?
3. Is volume confirming the move?
4. Is price momentum accelerating?
5. Is there a technical breakout?
6. Is the sector strong?
7. Is the overall market supportive?
8. Is there a verified catalyst?
9. Is the stock already overextended?
10. Is there evidence of abnormal/manipulative activity?
11. How far is it from Upper Circuit?
12. What happened to similar signals historically?
13. Does the historical backtest support this probability?
14. What could invalidate the prediction?

Only after these checks should the stock receive a high score.

---

# 32. DELIVERABLE

Modify my existing application rather than creating an unrelated application.

First inspect the existing codebase and understand:

* Existing architecture
* Frontend
* Backend
* APIs
* Database
* Current Price Band Screener
* Existing components
* Existing styling
* Existing data flow

Then implement the new:

**AI Short-Term Momentum & Upper Circuit Probability Engine**

without unnecessarily breaking existing functionality.

Reuse existing components wherever possible.

Keep the UI responsive for desktop, tablet and mobile.

Most importantly:

**Do not fabricate market data, news, prices, volume, Upper Circuit values, probabilities or research evidence.**

Every prediction must be traceable to actual collected data and timestamped.

---

# IMPLEMENTATION STATUS (updated 24 Aug 2026)

Scoped deliberately, not attempted section-by-section in one pass: order-book/
order-flow and continuous live monitoring are held pending a broker feed
(`BROKER_API_KEY` etc. in `config.py`, currently unset); everything else
buildable on free/delayed data was implemented this pass. Code: `momentum.py`
(orchestration), `momentum_scoring.py` (pure scoring model), `nse_live.fetch_quote`
(live quote + circuit limits), `storage.py` momentum tables. See README's
"AI Momentum & Upper-Circuit Scanner" section for the real-world caveats.

| # | Section | Status | Notes |
|---|---|---|---|
| 1 | Market universe | Done | Broad universe (Nifty Total Market + Microcap 250, ~900 names); Stage-2 live/intraday pass capped to top `SCANNER_MOMENTUM_UNIVERSE_LIMIT` (60) by design -- see README |
| 2 | Data collection: exchange/market data | Partial | LTP, prev close, VWAP, UC/LC, day change, avg volume via yfinance+NSE. No bid/ask, no order-book imbalance, no delivery data -- deferred |
| 2 | Data collection: news | Done | Existing RSS + keyword scorer, reused as-is |
| 2 | Data collection: corporate filings | Not done | No source wired up (results/investor presentations/bulk deals) |
| 2 | Data collection: technical | Done | Daily (existing) + new intraday (VWAP, ORB, EMA9/20, Bollinger %B) |
| 3 | Real-time data requirement | Done | `data_as_of` / `generated_at` on every run; NSE quote failures surfaced, never silently stale |
| 4 | Upper Circuit analysis | Done | Real circuit limits from NSE where a static band exists; `has_static_band=False` shown honestly, never fabricated |
| 5 | Short-term momentum engine (15/30/60/120m) | Partial | Computed and shown; explicitly labeled uncalibrated (see 22-23) |
| 6 | AI scoring model | Adapted | `momentum_scoring.py`'s Final Opportunity Score (spec section 14 weights) rather than section 6's own point scheme -- avoids two overlapping 0-100 models |
| 7 | Prediction classification | Done | `classify_momentum_grade()`; <60 excluded from the primary list |
| 8 | Upper Circuit probability | Done | Separate model, requires multiple confirming signals for "High" confidence |
| 9 | False-signal avoidance | Partial | Liquidity/adverse-news/extended/spike checks implemented; bid-ask spread, social-hype, old-news-reuse marked `unavailable_no_data_source` |
| 10 | Social sentiment | Not done | No data source configured -- not fabricated |
| 11 | Market regime analysis | Partial | Nifty trend, VIX, breadth (from scanned universe) implemented; FII/DII/global markets not wired into the momentum engine (still used by the daily scanner) |
| 12 | Sector rotation | Partial | Sector momentum score exists; relative-strength-vs-sector/vs-NIFTY per stock not computed |
| 13 | Multi-source validation | Not done | Single-source per data type; no cross-check/conflict detection |
| 14 | Ranking algorithm | Done | Implemented as specified (35/20/15/10/10/5/5) |
| 15 | Primary results table | Done | Dashboard, AI Momentum Scanner tab |
| 16 | Stock detail view | Done | Expander per candidate: price, prediction, score breakdown, why/invalidation |
| 17 | Signal timeline | Partial | "Why this stock" + "what invalidates it" generated from scan-time data; no evolving intraday event log (needs continuous monitoring) |
| 18 | Live monitoring | Deferred | Needs a broker feed; current version is on-demand/cron snapshots, not streaming |
| 19 | Alert system | Partial | Inline "approaching upper circuit" badge; no configurable thresholds/notifications |
| 20 | Research output | Done | Market summary + top candidates with why/confirms/invalidates/risk/freshness |
| 21 | No guarantees wording | Done | Checked against the banned/preferred phrase lists |
| 22-23 | Backtesting + calibration | Partial | `momentum_signals` table + `momentum-backfill` + `momentum-stats` give real predicted-vs-realized numbers per horizon; not a full reliability-curve UI yet |
| 24 | Data failure handling | Done | Every provider degrades to `None`/`unavailable`, never a crash or a fake score |
| 25 | API architecture | Done | Modular: market_data / nse_live / news / indicators / momentum_scoring / momentum / storage |
| 26 | Database | Partial | `momentum_signals` added; separate tables for filings/order-flow/sentiment not created (no data to store yet) |
| 27 | UI requirements | Done | Existing screener kept; new tab added; filters implemented |
| 28 | Top-5 priority view | Done | First thing shown after a research run |
| 29 | Research refresh | Partial | "Run Market Research"/"Refresh Data" buttons + timestamp; no auto-refresh countdown (would be fake without a live feed) |
| 30 | Final AI response format | Done | Reflected in the JSON output (`data/latest_momentum.json`) and the dashboard |
| 31 | Pre-score checklist | Done | Encoded directly in `momentum_scoring.score_candidate()` / `detect_manipulation()` |
| 32 | Deliverable constraints | Done | Existing architecture extended, not replaced; no fabricated data anywhere in the new code path |
