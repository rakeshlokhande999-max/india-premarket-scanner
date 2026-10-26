"""AI Short-Term Momentum & Upper-Circuit Probability Engine
(app-info.md's primary objective).

On "Run Market Research", scans the broader NSE universe -- not just
Nifty-50, most of which has no static price band at all, see
nse_live.fetch_quote() -- for a short-term (1-2 hour) upward-momentum
signal with a distance/probability read toward each stock's real,
exchange-reported upper circuit where one applies.

Two-stage funnel, so an undocumented, unauthenticated, per-symbol NSE
endpoint (nse_live.fetch_quote) never gets hammered for the full
~900-name broad universe:

  Stage 1 (cheap, one batched call): ~1y of daily bars for the *entire*
    broad universe via market_data.fetch_ohlcv_batch() -> the existing
    indicators.compute_indicators() per name, in memory, no extra network
    round-trips.
  Stage 2 (narrow, expensive): only the top `config.MOMENTUM_UNIVERSE_LIMIT`
    names by a coarse day-change x relative-volume pre-filter get a live
    NSE quote (for the real upper-circuit price) and a batched intraday
    5-minute-bar fetch.

This is a user-triggered ("Run Market Research" / "Refresh Data") or
cron-triggered snapshot, not a continuous/streaming monitor -- true live
monitoring (spec section 18) is deferred until a broker feed is configured
(BROKER_API_KEY etc. in config.py), same as order-book/order-flow data.
"""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import indicators
import market_data
import momentum_scoring
import news
import nse_live
import scoring
import storage

log = config.get_logger("momentum")

IST = timezone(timedelta(hours=5, minutes=30))
LATEST_MOMENTUM_PATH = Path("./data/latest_momentum.json")


def _now_ist() -> datetime:
    return datetime.now(IST)


def _reasons_and_invalidation(dind: dict, iind: dict | None, score, news_info: dict | None) -> tuple[list, list]:
    """Deterministic sentence assembly from real fields only -- spec
    section 16/20's "never invent reasons; every reason must be backed by
    actual collected data."
    """
    reasons = []
    if iind and iind.get("opening_range_breakout"):
        reasons.append("Confirmed opening-range breakout")
    elif dind["last_close"] > dind["prev_day_high"]:
        reasons.append("Trading above yesterday's high")
    if score.relative_volume_intraday and score.relative_volume_intraday >= 1.5:
        reasons.append(f"{score.relative_volume_intraday:.1f}x relative volume vs. the session-adjusted 20-day average")
    if news_info and news_info.get("news_score", 0) > 0:
        tags = ", ".join(news_info.get("tags", [])[:3])
        reasons.append(f"Positive news catalyst: {tags}" if tags else "Positive news catalyst")
    if score.sub_scores.get("sector_market_strength") is not None and score.sub_scores["sector_market_strength"] >= 7:
        reasons.append("Sector outperforming the broader market")
    if iind and iind.get("above_vwap"):
        reasons.append("Trading above session VWAP")
    if not reasons:
        reasons.append("Composite technical read only -- no single dominant signal; see the score breakdown")

    invalidation = []
    if iind and iind.get("vwap"):
        invalidation.append(f"Signal weakens if price closes back below VWAP (Rs{iind['vwap']})")
    if iind and iind.get("opening_range_low"):
        invalidation.append(f"Signal invalidated on a break below the opening-range low (Rs{iind['opening_range_low']})")
    if score.relative_volume_intraday:
        invalidation.append("Signal weakens if relative volume drops back toward 1x")
    if score.risk in ("HIGH", "EXTREME"):
        invalidation.append("Elevated risk flags present -- see manipulation_flags")
    return reasons, invalidation


def _candidate_to_dict(c: dict, generated_at: str) -> dict:
    inst, quote, score = c["instrument"], c["quote"], c["score"]
    dind, iind, news_info = c["daily_ind"], c["intraday_ind"], c["news_info"]
    reasons, invalidation = _reasons_and_invalidation(dind, iind, score, news_info)
    return {
        "symbol": inst.symbol,
        "name": inst.name,
        "sector": inst.sector,
        "current_price": round(c["current_price"], 2),
        "has_static_band": bool((quote or {}).get("has_static_band")),
        "upper_circuit": (quote or {}).get("upper_circuit"),
        "lower_circuit": (quote or {}).get("lower_circuit"),
        "uc_distance_pct": score.uc_distance_pct,
        "opportunity_score": score.opportunity_score,
        "momentum_grade": score.momentum_grade,
        "uc_probability_pct": score.uc_probability_pct,
        "uc_confidence": score.uc_confidence,
        "confirming_signals": score.confirming_signals,
        "horizon_probabilities": score.horizon_probabilities,
        "expected_move_pct": score.expected_move_pct,
        "relative_volume_intraday": score.relative_volume_intraday,
        "risk": score.risk,
        "manipulation_flags": score.manipulation_flags,
        "manipulation_checks": score.manipulation_checks,
        "sub_scores": score.sub_scores,
        "unavailable_components": score.unavailable_components,
        **score.targets,
        "news_tags": (news_info or {}).get("tags", []),
        "news_headlines": (news_info or {}).get("headlines", []),
        "reasons": reasons,
        "invalidation_watch": invalidation,
        "data_as_of": generated_at,
        "nse_quote_available": quote is not None,
    }


def run_market_research() -> dict:
    generated_at_dt = _now_ist()
    generated_at = generated_at_dt.isoformat()
    log.info("Starting AI Momentum Scanner research run at %s", generated_at)

    universe = market_data.fetch_broad_universe()
    if not universe:
        log.error("Broad universe fetch failed -- aborting rather than scoring stale/wrong data")
        return {"error": "universe_unavailable", "generated_at": generated_at}

    index_snapshot = market_data.fetch_index_snapshot()
    nifty = index_snapshot.get("NIFTY 50", {})
    vix = index_snapshot.get("INDIA VIX", {}).get("price")

    # Stage 1: one cheap batched daily read across the whole broad universe.
    daily_by_ticker = market_data.fetch_ohlcv_batch(
        [inst.yf_ticker for inst in universe], period="1y", interval="1d"
    )
    daily_ind: dict[str, dict] = {}
    sector_day_changes: dict[str, list[float]] = {}
    for inst in universe:
        df = daily_by_ticker.get(inst.yf_ticker)
        ind = indicators.compute_indicators(df) if df is not None else None
        if ind is None:
            continue
        daily_ind[inst.symbol] = ind
        sector_day_changes.setdefault(inst.sector, []).append(ind["day_change_pct"])

    sector_avg = {s: sum(v) / len(v) for s, v in sector_day_changes.items()}
    sector_scores = scoring.sector_momentum_scores(sector_avg)

    # spec section 11: market breadth from the scanned universe itself --
    # real, already-available data, no new external source needed.
    breadth_pct = (
        round(sum(1 for v in daily_ind.values() if v["day_change_pct"] > 0) / len(daily_ind) * 100, 1)
        if daily_ind else None
    )
    regime = scoring.classify_market_regime(nifty.get("change_pct", 0.0), vix, breadth_pct)
    log.info("Market regime: %s (Nifty %.2f%%, VIX %s, breadth %s%%)",
              regime, nifty.get("change_pct", 0.0), vix, breadth_pct)

    # Coarse pre-filter for Stage 2: real signal already visible in daily
    # bars (positive move + volume backing it), ranked, capped -- never a
    # silent truncation, the drop count is logged and surfaced in the output.
    prefiltered = [
        (inst, daily_ind[inst.symbol]) for inst in universe
        if inst.symbol in daily_ind
        and daily_ind[inst.symbol]["day_change_pct"] > 0
        and (daily_ind[inst.symbol].get("relative_volume") or 0) >= 1.0
    ]
    prefiltered.sort(key=lambda t: t[1]["day_change_pct"] * (t[1].get("relative_volume") or 1), reverse=True)
    shortlist = prefiltered[: config.MOMENTUM_UNIVERSE_LIMIT]
    dropped = max(len(prefiltered) - len(shortlist), 0)
    if dropped:
        log.info(
            "Stage 2 shortlist capped at %d of %d names that cleared the pre-filter (%d dropped -- "
            "raise SCANNER_MOMENTUM_UNIVERSE_LIMIT to widen)", len(shortlist), len(prefiltered), dropped,
        )

    headlines = news.fetch_headlines()
    news_map = news.map_news_to_universe(headlines, [inst for inst, _ in shortlist])

    # Stage 2: expensive per-name reads, only for the shortlist.
    intraday_by_ticker = market_data.fetch_ohlcv_batch(
        [inst.yf_ticker for inst, _ in shortlist], period="5d", interval="5m"
    )

    # One warmed session reused across the whole shortlist loop instead of
    # re-hitting NSE's homepage per symbol.
    quote_session = nse_live.warmed_session()
    candidates = []
    quote_failures = []
    for inst, dind in shortlist:
        quote = nse_live.fetch_quote(inst.symbol, session=quote_session)
        time.sleep(config.NSE_QUOTE_DELAY_SEC)
        if quote is None:
            quote_failures.append(inst.symbol)

        idf = intraday_by_ticker.get(inst.yf_ticker)
        iind = indicators.compute_intraday_indicators(idf, dind["prev_close"]) if idf is not None else None

        current_price = (quote or {}).get("last_price") or dind["last_close"]
        avg_turnover_cr = (dind["avg_volume_20"] * current_price) / 1e7 if dind.get("avg_volume_20") else None

        result = momentum_scoring.score_candidate(
            symbol=inst.symbol,
            current_price=current_price,
            upper_circuit=(quote or {}).get("upper_circuit"),
            has_static_band=(quote or {}).get("has_static_band"),
            daily_ind=dind,
            intraday_ind=iind,
            sector_score=sector_scores.get(inst.sector),
            news_info=news_map.get(inst.symbol),
            market_regime=regime,
            avg_turnover_cr=avg_turnover_cr,
            now_ist=generated_at_dt,
        )
        candidates.append({
            "instrument": inst, "quote": quote, "score": result,
            "daily_ind": dind, "intraday_ind": iind, "news_info": news_map.get(inst.symbol),
            "current_price": current_price,
        })

    # spec section 7: below-threshold names never reach the primary list.
    # spec section 18: EXTREME risk auto-rejected.
    eligible = [
        c for c in candidates
        if c["score"].opportunity_score >= config.MOMENTUM_MIN_SCORE and c["score"].risk != "EXTREME"
    ]
    eligible.sort(key=lambda c: c["score"].opportunity_score, reverse=True)

    market_summary = {
        "market_regime": regime,
        "nifty_change_pct": nifty.get("change_pct"),
        "india_vix": vix,
        "market_breadth_pct": breadth_pct,
        "strongest_sector": max(sector_scores, key=sector_scores.get) if sector_scores else None,
        "high_momentum_found": len(eligible),
        "high_confidence_candidates": sum(1 for c in eligible if c["score"].uc_confidence == "High"),
    }

    output = {
        "generated_at": generated_at,
        "data_as_of": generated_at,
        **market_summary,
        "index_snapshot": index_snapshot,
        "sector_scores": sector_scores,
        "universe_size": len(universe),
        "stage1_scored": len(daily_ind),
        "stage2_shortlist_size": len(shortlist),
        "stage2_dropped_by_cap": dropped,
        "nse_quote_failures": quote_failures,
        "headline_count": len(headlines),
        "candidates": [_candidate_to_dict(c, generated_at) for c in eligible],
        "disclaimer": (
            "This is an AI-generated market research signal, not a guarantee of future price "
            "movement or investment advice. Horizon probabilities are a transparent heuristic, "
            "not yet calibrated against historical outcomes -- see the Backtest/Accuracy tab."
        ),
    }

    LATEST_MOMENTUM_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_MOMENTUM_PATH.write_text(json.dumps(output, indent=2, default=str))

    for cand in output["candidates"]:
        storage.insert_momentum_signal({**cand, "run_at": generated_at})

    log.info(
        "Momentum research complete: regime=%s, %d/%d stage1 scored, %d stage2 shortlisted, %d candidates cleared threshold",
        regime, len(daily_ind), len(universe), len(shortlist), len(eligible),
    )
    return output


def run_momentum_backfill() -> dict:
    """Horizon outcome backfill -- checks which open signals have at least
    one due (15/30/60/120-minute) horizon and fills it with a fresh NSE
    quote. Never fills a horizon early, never fabricates a price. Meant to
    be run periodically (cron, or the dashboard's "Refresh Data"/backfill
    button) -- not a continuous monitor.
    """
    now = _now_ist()
    open_rows = storage.get_open_momentum_signals()
    due = []
    for row in open_rows:
        run_at = datetime.fromisoformat(row["run_at"])
        elapsed_min = (now - run_at).total_seconds() / 60
        for h in config.HORIZON_MINUTES:
            if elapsed_min >= h and row[f"price_after_{h}m"] is None:
                due.append((row, h))

    if not due:
        return {"checked": len(open_rows), "due": 0, "filled": 0}

    symbols_needed = sorted({row["symbol"] for row, _ in due})
    quote_session = nse_live.warmed_session()
    quotes: dict[str, dict | None] = {}
    for sym in symbols_needed:
        quotes[sym] = nse_live.fetch_quote(sym, session=quote_session)
        time.sleep(config.NSE_QUOTE_DELAY_SEC)

    filled = 0
    for row, h in due:
        q = quotes.get(row["symbol"])
        if not q or q.get("last_price") is None:
            continue
        price = float(q["last_price"])
        uc_reached = bool(row["upper_circuit"] and price >= row["upper_circuit"])
        storage.backfill_momentum_horizon(row["id"], h, price, uc_reached)
        filled += 1

    log.info("Momentum backfill: %d open signals, %d horizons due, %d filled", len(open_rows), len(due), filled)
    return {"checked": len(open_rows), "due": len(due), "filled": filled}
