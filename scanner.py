#!/usr/bin/env python3
"""Main orchestration CLI.

    python scanner.py scan               # full daily scan (run at/after 8:00 IST)
    python scanner.py preopen            # 9:00-9:15 IST pre-open validation pass
    python scanner.py backfill           # T+1 job: fill in actual outcomes for backtesting
    python scanner.py stats              # print current backtest accuracy stats
    python scanner.py momentum           # AI Momentum / Upper-Circuit research run (market hours)
    python scanner.py momentum-backfill  # fill due 15/30/60/120-min horizon outcomes
    python scanner.py momentum-stats     # print current momentum-model calibration stats

Every run is a plain function call, not an LLM call -- this is meant to
run unattended off cron/systemd timers (see README + crontab.example),
not to have an agent in the loop at 9:15 AM.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import indicators
import market_data
import momentum
import news
import nse_live
import scoring
import storage

log = config.get_logger("scanner")

IST = timezone(timedelta(hours=5, minutes=30))
LATEST_SCAN_PATH = Path("./data/latest_scan.json")


def _now_ist_str() -> str:
    return datetime.now(IST).isoformat()


def _today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _latest_fii_dii_net(rows: list[dict]) -> dict:
    if not rows:
        return {"fii_net_cr": None, "dii_net_cr": None, "as_of": None}
    dates = sorted({r["date"] for r in rows}, key=lambda d: datetime.strptime(d, "%d-%b-%Y"))
    latest_date = dates[-1]
    latest_rows = [r for r in rows if r["date"] == latest_date]
    fii = next((float(r["netValue"]) for r in latest_rows if "FII" in r["category"] or "FPI" in r["category"]), None)
    dii = next((float(r["netValue"]) for r in latest_rows if r["category"] == "DII"), None)
    return {"fii_net_cr": fii, "dii_net_cr": dii, "as_of": latest_date}


def run_scan() -> dict:
    generated_at = _now_ist_str()
    log.info("Starting scan at %s", generated_at)

    universe = market_data.fetch_universe()
    if not universe:
        log.error("Universe fetch failed -- aborting scan rather than scoring stale/wrong data")
        return {"error": "universe_unavailable", "generated_at": generated_at}

    index_snapshot = market_data.fetch_index_snapshot()
    nifty = index_snapshot.get("NIFTY 50", {})
    vix = index_snapshot.get("INDIA VIX", {}).get("price")
    regime = scoring.classify_market_regime(nifty.get("change_pct", 0.0), vix)
    log.info("Market regime: %s (Nifty %.2f%%, VIX %.2f)", regime, nifty.get("change_pct", 0.0), vix or -1)

    fii_dii_raw = nse_live.fetch_fii_dii()
    fii_dii = _latest_fii_dii_net(fii_dii_raw)

    headlines = news.fetch_headlines()
    news_map = news.map_news_to_universe(headlines, universe)

    scored = []
    sector_day_changes: dict[str, list[float]] = {}
    skipped = []

    for inst in universe:
        df = market_data.fetch_ohlcv(inst.yf_ticker)
        ind = indicators.compute_indicators(df)
        if ind is None:
            skipped.append(inst.symbol)
            continue
        sector_day_changes.setdefault(inst.sector, []).append(ind["day_change_pct"])
        scored.append((inst, ind))

    sector_avg = {s: sum(v) / len(v) for s, v in sector_day_changes.items()}
    sector_scores = scoring.sector_momentum_scores(sector_avg)

    candidates = []
    for inst, ind in scored:
        avg_turnover_cr = (
            (ind["avg_volume_20"] * ind["last_close"]) / 1e7
            if ind.get("avg_volume_20")
            else None
        )
        result = scoring.score_instrument(
            symbol=inst.symbol,
            ind=ind,
            market_regime=regime,
            sector_score=sector_scores.get(inst.sector),
            news_info=news_map.get(inst.symbol),
            fii_net_cr=fii_dii["fii_net_cr"],
            dii_net_cr=fii_dii["dii_net_cr"],
            preopen_change_pct=None,  # not available outside the 9:00-9:15 IST window
            avg_turnover_cr=avg_turnover_cr,
        )
        candidates.append({"instrument": inst, "indicators": ind, "score": result})

    # Spec section 18: EXTREME risk auto-rejected.
    eligible = [c for c in candidates if c["score"].risk != "EXTREME"]
    eligible.sort(key=lambda c: (c["score"].composite_score, c["score"].confidence_pct), reverse=True)

    # Spec section 4: fewer candidates when the regime itself is weak.
    max_candidates = 3 if regime in ("BEARISH", "HIGH RISK") else config.TOP_N_CANDIDATES
    top = [c for c in eligible if c["score"].composite_score >= 60][:max_candidates]

    no_trade_reason = None
    if not top:
        no_trade_reason = (
            f"No candidate cleared the Watchlist threshold (score >= 60) under a {regime} regime."
        )

    output = {
        "generated_at": generated_at,
        "market_regime": regime,
        "index_snapshot": index_snapshot,
        "fii_dii": fii_dii,
        "sector_scores": sector_scores,
        "universe_size": len(universe),
        "skipped_symbols": skipped,
        "headline_count": len(headlines),
        "no_trade_reason": no_trade_reason,
        "candidates": [
            {
                "symbol": c["instrument"].symbol,
                "name": c["instrument"].name,
                "sector": c["instrument"].sector,
                "last_close": c["indicators"]["last_close"],
                "composite_score": c["score"].composite_score,
                "score_label": scoring.score_label(c["score"].composite_score),
                "confidence_pct": c["score"].confidence_pct,
                "confidence_label": scoring.confidence_label(c["score"].confidence_pct),
                "risk": c["score"].risk,
                "sub_scores": c["score"].sub_scores,
                "unavailable_components": c["score"].unavailable_components,
                "news_tags": (news_map.get(c["instrument"].symbol) or {}).get("tags", []),
                "news_headlines": (news_map.get(c["instrument"].symbol) or {}).get("headlines", []),
                **c["score"].targets,
            }
            for c in top
        ],
        "all_scored": [
            {
                "symbol": c["instrument"].symbol,
                "sector": c["instrument"].sector,
                "last_close": c["indicators"]["last_close"],
                "day_change_pct": c["indicators"]["day_change_pct"],
                "composite_score": c["score"].composite_score,
                "risk": c["score"].risk,
                "relative_volume": c["indicators"].get("relative_volume"),
            }
            for c in candidates
        ],
    }

    LATEST_SCAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_SCAN_PATH.write_text(json.dumps(output, indent=2, default=str))

    run_date = _today_ist()
    for cand in output["candidates"]:
        storage.insert_prediction(
            {
                "run_date": run_date,
                "run_time": generated_at,
                "symbol": cand["symbol"],
                "sector": cand["sector"],
                "entry_zone": cand.get("entry_zone"),
                "target_1": cand.get("target_1"),
                "target_2": cand.get("target_2"),
                "target_3": cand.get("target_3"),
                "stop_loss": cand.get("stop_loss"),
                "composite_score": cand["composite_score"],
                "confidence_pct": cand["confidence_pct"],
                "risk": cand["risk"],
                "market_regime": regime,
                "reasoning": {
                    "sub_scores": cand["sub_scores"],
                    "unavailable_components": cand["unavailable_components"],
                    "news_tags": cand["news_tags"],
                },
            }
        )

    log.info(
        "Scan complete: regime=%s, %d/%d scored, %d candidates, %d skipped",
        regime, len(candidates), len(universe), len(top), len(skipped),
    )
    return output


def run_preopen_validation() -> dict:
    """spec sections 9, 22-24. Cross-checks stored candidates for today
    against NSE's real pre-open snapshot; only meaningful 9:00-9:15 IST.
    """
    if not LATEST_SCAN_PATH.exists():
        return {"error": "no_scan_found", "message": "Run `scanner.py scan` first."}
    latest = json.loads(LATEST_SCAN_PATH.read_text())
    preopen = nse_live.fetch_preopen("NIFTY")
    preopen_by_symbol = {row["metadata"]["symbol"]: row["metadata"] for row in preopen.get("data", [])}

    validated = []
    for cand in latest.get("candidates", []):
        p = preopen_by_symbol.get(cand["symbol"])
        if p is None:
            validated.append({**cand, "preopen_status": "WAIT", "preopen_reason": "not found in pre-open snapshot"})
            continue
        pchange = p.get("pChange", 0)
        if pchange <= -1.0:
            status = "AVOID"
            reason = f"Gapping down {pchange:.2f}% pre-open, contradicts the long setup"
        elif pchange >= 4.0:
            status = "WAIT"
            reason = f"Gap-up {pchange:.2f}% is large enough to check for exhaustion before chasing"
        else:
            status = "BUY SETUP"
            reason = f"Pre-open {pchange:+.2f}%, consistent with the scan"
        validated.append({**cand, "preopen_status": status, "preopen_reason": reason, "preopen_change_pct": pchange})

    result = {"generated_at": _now_ist_str(), "validated_candidates": validated}
    Path("./data/latest_preopen.json").write_text(json.dumps(result, indent=2, default=str))
    return result


def run_backfill() -> dict:
    """T+1 outcome backfill -- never touches same-day data (spec section 28)."""
    cutoff = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
    pending = storage.get_predictions_needing_outcome(cutoff)
    filled = 0
    for row in pending:
        yf_ticker = f"{row['symbol']}.NS"
        df = market_data.fetch_ohlcv(yf_ticker, period="10d")
        if df.empty:
            continue
        day_rows = df[df.index.strftime("%Y-%m-%d") > row["run_date"]]
        if day_rows.empty:
            continue
        next_day = day_rows.iloc[0]
        entry_ref = float(row["entry_zone"].split("-")[0]) if row["entry_zone"] else None
        storage.backfill_outcome(
            row["id"], float(next_day["High"]), float(next_day["Low"]), float(next_day["Close"]), entry_ref,
        )
        filled += 1
    log.info("Backfilled outcomes for %d/%d pending predictions", filled, len(pending))
    return {"pending": len(pending), "filled": filled}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=["scan", "preopen", "backfill", "stats", "momentum", "momentum-backfill", "momentum-stats"],
    )
    args = parser.parse_args()

    storage.init_db()

    if args.mode == "scan":
        result = run_scan()
    elif args.mode == "preopen":
        result = run_preopen_validation()
    elif args.mode == "backfill":
        result = run_backfill()
    elif args.mode == "stats":
        result = storage.compute_accuracy_stats()
    elif args.mode == "momentum":
        result = momentum.run_market_research()
    elif args.mode == "momentum-backfill":
        result = momentum.run_momentum_backfill()
    else:
        result = storage.compute_momentum_accuracy_stats()

    print(json.dumps(result, indent=2, default=str))
    return 1 if isinstance(result, dict) and result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
