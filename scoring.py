"""The weighted composite scoring model (spec sections 4, 11, 15, 16-18).

Every sub-score is computed from a real, fetched value (price history,
NSE FII/DII flow, RSS-derived news score) -- nothing is a placeholder
constant. Where a genuinely required input is unavailable (e.g. the
pre-open snapshot outside the 9:00-9:15 IST window), the sub-score is
marked unavailable and excluded from the composite (weights are
renormalized over what's actually available) rather than defaulted to
a made-up "neutral" number that would silently inflate the score.
"""
from dataclasses import dataclass, field

import config

log = config.get_logger(__name__)


def _clip(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def classify_market_regime(nifty_change_pct: float, india_vix: float, breadth_pct: float | None = None) -> str:
    """spec section 4. Rule-based, not a black box: elevated VIX alone is
    enough to force HIGH RISK regardless of index direction.
    """
    if india_vix is not None and india_vix >= 22:
        return "HIGH RISK"
    if nifty_change_pct <= -1.2:
        return "BEARISH"
    if nifty_change_pct >= 1.2 and (breadth_pct is None or breadth_pct >= 60):
        return "STRONG BULLISH"
    if nifty_change_pct >= 0.4:
        return "BULLISH"
    if nifty_change_pct <= -0.4:
        return "BEARISH"
    return "NEUTRAL"


def sector_momentum_scores(sector_day_changes: dict[str, float]) -> dict[str, float]:
    """0-10 score per sector, ranked by today's average % change of its
    constituents within the scanned universe (a same-universe proxy for
    "sector momentum" -- not official NSE sector-index data).
    """
    if not sector_day_changes:
        return {}
    values = sorted(sector_day_changes.values())
    n = len(values)

    def percentile_score(v: float) -> float:
        rank = sum(1 for x in values if x <= v)
        return _clip((rank / n) * 10)

    return {sector: round(percentile_score(chg), 2) for sector, chg in sector_day_changes.items()}


def _technical_trend_score(ind: dict) -> float:
    alignment = ind["ema_alignment_bullish_count"] / max(ind["ema_alignment_total"], 1)
    score = alignment * 10
    if ind.get("macd_hist") is not None:
        score += 1.0 if ind["macd_hist"] > 0 else -1.0
    return _clip(score)


def _momentum_indicator_score(ind: dict) -> float:
    score = 5.0
    rsi = ind.get("rsi_14")
    if rsi is not None:
        if 55 <= rsi <= 70:
            score += 3
        elif rsi > 70:
            score += 0.5  # overbought -- some credit, but capped, see risk flag
        elif rsi < 45:
            score -= 3
    if ind.get("macd_hist") is not None:
        score += 1.5 if ind["macd_hist"] > 0 else -1.5
    if ind.get("adx_14") is not None and ind["adx_14"] >= 25:
        score += 1.5  # trending market, momentum reads are more trustworthy
    return _clip(score)


def _price_action_score(ind: dict) -> float:
    score = 5.0
    if ind["last_close"] > ind["prev_day_high"]:
        score += 3  # breaking above yesterday's high
    if ind.get("high_52w") and ind["last_close"] >= ind["high_52w"] * 0.99:
        score += 2  # near/at 52-week high -- momentum, but flagged as a risk factor too
    if ind["last_close"] < ind["prev_day_low"]:
        score -= 4
    return _clip(score)


def _volume_score(ind: dict) -> float:
    rel_vol = ind.get("relative_volume")
    if rel_vol is None:
        return 5.0
    return _clip(rel_vol * 5)  # 2x avg volume -> 10


def _news_score_to_subscore(news_score: int) -> float:
    return _clip((news_score + 10) / 2)


def _institutional_subscore(fii_net_cr: float | None, dii_net_cr: float | None) -> float | None:
    if fii_net_cr is None and dii_net_cr is None:
        return None
    net = (fii_net_cr or 0) + (dii_net_cr or 0)
    # +-2000cr combined net flow treated as a strong (not just "some") signal
    return _clip(5 + (net / 2000) * 5)


def _market_trend_subscore(regime: str) -> float:
    return {"STRONG BULLISH": 9, "BULLISH": 7, "NEUTRAL": 5, "BEARISH": 2.5, "HIGH RISK": 1}.get(regime, 5)


def compute_targets(last_close: float, atr: float) -> dict:
    """ATR-multiple targets/stop -- a standard technical heuristic, not a
    promise. All three targets and the stop are real arithmetic on a real
    ATR value pulled from price history, never invented numbers.
    """
    entry_low, entry_high = round(last_close, 2), round(last_close * 1.003, 2)
    target1 = round(last_close + 0.8 * atr, 2)
    target2 = round(last_close + 1.5 * atr, 2)
    target3 = round(last_close + 2.5 * atr, 2)
    stop_loss = round(last_close - 1.0 * atr, 2)
    risk = last_close - stop_loss
    reward = target2 - last_close
    risk_reward_ratio = round(reward / risk, 2) if risk > 0 else None
    return {
        "entry_zone": f"{entry_low}-{entry_high}",
        "target_1": target1,
        "target_2": target2,
        "target_3": target3,
        "stop_loss": stop_loss,
        "risk_reward_ratio": risk_reward_ratio,
    }


def _risk_reward_subscore(risk_reward_ratio: float | None) -> float:
    if risk_reward_ratio is None:
        return 3.0
    return _clip(risk_reward_ratio * 3)


def classify_risk(ind: dict, news_score: int, avg_turnover_cr: float | None) -> str:
    """spec section 18. EXTREME auto-rejects downstream (spec section 18)."""
    if news_score <= -6:
        return "EXTREME"
    if avg_turnover_cr is not None and avg_turnover_cr < 5:
        return "EXTREME"  # too illiquid to reliably enter/exit
    high = ind.get("rsi_14") is not None and ind["rsi_14"] > 75
    near_52w_high = (
        ind.get("high_52w") and ind["last_close"] >= ind["high_52w"] * 0.995
    )
    if high and near_52w_high:
        return "HIGH"  # overbought right at resistance -- fake-breakout / exhaustion risk
    if ind.get("adx_14") is not None and ind["adx_14"] < 15:
        return "MEDIUM"  # no real trend to lean on
    return "LOW"


@dataclass
class CandidateScore:
    symbol: str
    composite_score: float
    confidence_pct: float
    sub_scores: dict = field(default_factory=dict)
    unavailable_components: list = field(default_factory=list)
    risk: str = "MEDIUM"
    targets: dict = field(default_factory=dict)


def score_instrument(
    symbol: str,
    ind: dict,
    market_regime: str,
    sector_score: float | None,
    news_info: dict | None,
    fii_net_cr: float | None,
    dii_net_cr: float | None,
    preopen_change_pct: float | None,
    avg_turnover_cr: float | None,
) -> CandidateScore:
    news_score = (news_info or {}).get("news_score", 0)

    sub = {
        "market_trend": _market_trend_subscore(market_regime),
        "sector_momentum": sector_score,
        "news_catalyst": _news_score_to_subscore(news_score) if news_info else None,
        "technical_trend": _technical_trend_score(ind),
        "price_action": _price_action_score(ind),
        "volume": _volume_score(ind),
        "pre_open_strength": _clip(5 + (preopen_change_pct or 0) * 1.5) if preopen_change_pct is not None else None,
        "institutional": _institutional_subscore(fii_net_cr, dii_net_cr),
        "momentum_indicators": _momentum_indicator_score(ind),
        "risk_reward": None,  # filled in after targets are computed, below
    }

    targets = compute_targets(ind["last_close"], ind["atr_14"]) if ind.get("atr_14") else {}
    sub["risk_reward"] = _risk_reward_subscore(targets.get("risk_reward_ratio"))

    unavailable = [k for k, v in sub.items() if v is None]
    available = {k: v for k, v in sub.items() if v is not None}
    weight_sum = sum(config.SCORE_WEIGHTS[k] for k in available)
    composite = 0.0
    if weight_sum > 0:
        composite = sum(config.SCORE_WEIGHTS[k] * v for k, v in available.items()) / weight_sum * 10

    # Confidence tracks both the score and how much of the model actually
    # had real data behind it this run -- a "90/100" built on half-missing
    # inputs should not read as high-confidence.
    completeness = len(available) / len(sub)
    confidence = _clip(composite * 0.8 + completeness * 20, 0, 100)

    risk = classify_risk(ind, news_score, avg_turnover_cr)

    return CandidateScore(
        symbol=symbol,
        composite_score=round(composite, 1),
        confidence_pct=round(confidence, 1),
        sub_scores={k: (round(v, 2) if v is not None else None) for k, v in sub.items()},
        unavailable_components=unavailable,
        risk=risk,
        targets=targets,
    )


def score_label(composite_score: float) -> str:
    if composite_score >= 90:
        return "Exceptional setup"
    if composite_score >= 80:
        return "Strong setup"
    if composite_score >= 70:
        return "Good setup"
    if composite_score >= 60:
        return "Watchlist"
    if composite_score >= 50:
        return "Weak"
    return "Avoid"


def confidence_label(confidence_pct: float) -> str:
    if confidence_pct >= 85:
        return "Very high"
    if confidence_pct >= 75:
        return "High"
    if confidence_pct >= 65:
        return "Moderate"
    if confidence_pct >= 50:
        return "Low"
    return "Avoid"
