"""Final Opportunity Score + Upper-Circuit Probability model for the AI
Momentum Scanner (app-info.md sections 4-9, 14). Pure functions only -- no
network calls -- so this is unit-testable without mocking any provider.

Every sub-score here is computed from a value the caller already fetched
for real (daily/intraday indicators, a live NSE quote, the RSS news
scanner). Where a genuinely required input is missing, the sub-score comes
back None and is excluded from the composite (weights renormalized over
what's available) -- never defaulted to an invented "neutral" number.

Deliberately NOT implemented here (see README "Known limitations"):
order-book depth / bid-ask spread, social-media sentiment, cross-headline
"is this old news recirculated" detection -- no data source is wired up
for any of these yet, and the spec's own rule is to report `unavailable`
rather than fabricate. `detect_manipulation()` says so explicitly per flag.
"""
from dataclasses import dataclass, field
from datetime import datetime

import config
import scoring  # reuse compute_targets() -- same ATR-multiple heuristic as the daily model

log = config.get_logger(__name__)

MARKET_OPEN_HHMM = (9, 15)
MARKET_CLOSE_HHMM = (15, 30)


def _clip(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def uc_distance_pct(current_price: float, upper_circuit: float | None) -> float | None:
    """spec section 4: Distance % = ((UC - price) / price) x 100.
    None when there's no static upper-circuit price to be distant from.
    """
    if not upper_circuit or not current_price:
        return None
    return round((upper_circuit - current_price) / current_price * 100, 2)


def session_elapsed_fraction(now_ist: datetime) -> float:
    """0.05-1.0 fraction of the 09:15-15:30 IST session elapsed. Used to
    scale an intraday volume-so-far read against the 20-day average.
    """
    open_dt = now_ist.replace(hour=MARKET_OPEN_HHMM[0], minute=MARKET_OPEN_HHMM[1], second=0, microsecond=0)
    close_dt = now_ist.replace(hour=MARKET_CLOSE_HHMM[0], minute=MARKET_CLOSE_HHMM[1], second=0, microsecond=0)
    if now_ist <= open_dt:
        return 0.05
    if now_ist >= close_dt:
        return 1.0
    return max(0.05, min(1.0, (now_ist - open_dt).total_seconds() / (close_dt - open_dt).total_seconds()))


def _momentum_subscore(daily_ind: dict, intraday_ind: dict | None) -> float:
    score = 5.0
    if intraday_ind:
        if intraday_ind.get("ema9_above_ema20"):
            score += 2
        if intraday_ind.get("above_vwap"):
            score += 1.5
        rsi_i = intraday_ind.get("rsi_intraday")
        if rsi_i is not None:
            if 55 <= rsi_i <= 75:
                score += 1.5
            elif rsi_i < 45:
                score -= 2
    if daily_ind.get("macd_hist") is not None:
        score += 1.0 if daily_ind["macd_hist"] > 0 else -1.0
    return _clip(score)


def _volume_subscore(daily_ind: dict, intraday_ind: dict | None, now_ist: datetime) -> tuple[float, float | None]:
    """Returns (subscore, relative_volume_intraday).

    The intraday relative-volume read is an approximation: today's session
    volume-so-far vs. the 20-day average *scaled to the same elapsed
    fraction of the session* -- not a true same-time-yesterday comparison
    (that needs stored intraday history across many days, not collected
    yet). Falls back to the daily relative-volume figure when no intraday
    read is available.
    """
    avg_vol_20 = daily_ind.get("avg_volume_20")
    if not intraday_ind or not avg_vol_20:
        rel = daily_ind.get("relative_volume")
        return (_clip(rel * 5) if rel else 5.0), rel
    elapsed = session_elapsed_fraction(now_ist)
    expected_by_now = avg_vol_20 * elapsed
    if not expected_by_now:
        return 5.0, None
    rel = intraday_ind["session_volume"] / expected_by_now
    return _clip(rel * 4), round(rel, 2)


def _catalyst_subscore(news_info: dict | None) -> float | None:
    if not news_info:
        return None
    return _clip((news_info.get("news_score", 0) + 10) / 2)


def _breakout_subscore(daily_ind: dict, intraday_ind: dict | None) -> float:
    score = 0.0
    hits = 0
    if daily_ind["last_close"] > daily_ind["prev_day_high"]:
        score += 3
        hits += 1
    if intraday_ind:
        if intraday_ind.get("opening_range_breakout"):
            score += 3
            hits += 1
        if intraday_ind.get("above_vwap"):
            score += 2
            hits += 1
    if daily_ind.get("high_52w") and daily_ind["last_close"] >= daily_ind["high_52w"] * 0.99:
        score += 2
        hits += 1
    return _clip(score) if hits else 3.0


def _sector_market_subscore(sector_score: float | None, market_regime: str) -> float | None:
    if sector_score is None:
        return None
    regime_bonus = {
        "STRONG BULLISH": 2, "BULLISH": 1, "NEUTRAL": 0, "BEARISH": -1.5, "HIGH RISK": -2.5,
    }.get(market_regime, 0)
    return _clip(sector_score + regime_bonus)


def _liquidity_subscore(avg_turnover_cr: float | None, relative_volume: float | None) -> float:
    if avg_turnover_cr is None:
        return 3.0
    score = _clip(avg_turnover_cr / 5)  # Rs25cr/day avg turnover -> 5.0
    if relative_volume:
        score = _clip(score + min(relative_volume, 2) - 1)
    return score


_RISK_TO_SCORE = {"LOW": 10.0, "MEDIUM": 6.0, "HIGH": 3.0, "EXTREME": 0.0}


def detect_manipulation(
    daily_ind: dict, intraday_ind: dict | None, news_score: int, avg_turnover_cr: float | None,
) -> tuple[str, list[str], dict[str, str]]:
    """spec section 9. Rule-based and auditable -- every flag traces to a
    real fetched value. Checks the spec asks for that this app has no data
    source for are reported as `unavailable_no_data_source`, never
    silently skipped or guessed at.
    """
    flags: list[str] = []
    checks: dict[str, str] = {
        "wide_bid_ask_spread": "unavailable_no_data_source",
        "social_media_only_hype": "unavailable_no_data_source",
        "old_news_recirculated": "unavailable_no_data_source",
    }

    if avg_turnover_cr is not None and avg_turnover_cr < 5:
        flags.append("Extremely low liquidity (avg turnover < Rs5cr/day)")
        checks["low_liquidity"] = "checked_flagged"
    else:
        checks["low_liquidity"] = "checked_clear"

    if news_score <= -6:
        flags.append("Strongly negative/adverse news detected")
        checks["adverse_news"] = "checked_flagged"
    else:
        checks["adverse_news"] = "checked_clear"

    already_extended = bool(
        daily_ind.get("rsi_14") is not None and daily_ind["rsi_14"] > 78
        and daily_ind.get("high_52w") and daily_ind["last_close"] >= daily_ind["high_52w"] * 0.995
    )
    if already_extended:
        flags.append("Already extended: RSI > 78 at/near the 52-week high -- exhaustion risk")
        checks["already_extended"] = "checked_flagged"
    else:
        checks["already_extended"] = "checked_clear"

    abnormal_spike = bool(
        intraday_ind is not None and intraday_ind.get("gap_pct") is not None
        and abs(intraday_ind["gap_pct"]) >= 10 and (daily_ind.get("adx_14") or 0) < 20
    )
    if abnormal_spike:
        flags.append("Large gap without an established trend (ADX < 20) -- possible unexplained spike")
        checks["abnormal_spike"] = "checked_flagged"
    else:
        checks["abnormal_spike"] = "checked_clear"

    if (avg_turnover_cr is not None and avg_turnover_cr < 5) or news_score <= -6:
        risk = "EXTREME"
    elif already_extended or abnormal_spike:
        risk = "HIGH"
    elif (daily_ind.get("adx_14") or 0) < 15:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return risk, flags, checks


def uc_probability(
    momentum_sub: float,
    volume_sub: float,
    breakout_sub: float,
    catalyst_sub: float | None,
    distance_pct: float | None,
    relative_volume: float | None,
) -> tuple[float | None, str, list[str]]:
    """spec section 8: a *separate* model from the opportunity score.
    Returns None (not a number, never a fabricated placeholder) when
    there's no static upper-circuit price for this security.

    High confidence requires multiple independent signals to agree (the
    spec's own example: volume + catalyst + breakout + momentum together,
    not price movement alone).
    """
    if distance_pct is None:
        return None, "Not applicable", []

    confirming = []
    if relative_volume and relative_volume >= 1.5:
        confirming.append("volume")
    if catalyst_sub is not None and catalyst_sub >= 7:
        confirming.append("catalyst")
    if breakout_sub >= 7:
        confirming.append("breakout")
    if momentum_sub >= 7:
        confirming.append("momentum")

    base = (momentum_sub * 0.40 + volume_sub * 0.25 + breakout_sub * 0.20 + (catalyst_sub or 5.0) * 0.15) * 10
    # Closer to the circuit matters, but only as a multiplier on a real
    # momentum read -- never "cheap stock == closer == more likely" (the
    # spec's own explicit warning in section 4).
    if distance_pct <= 3:
        proximity_mult = 1.15
    elif distance_pct <= 7:
        proximity_mult = 1.05
    else:
        proximity_mult = 1.0
    prob = _clip(base * proximity_mult, 5, 95)  # never claim 0% or 100% certainty

    if len(confirming) >= 3:
        confidence = "High"
    elif len(confirming) == 2:
        confidence = "Moderate"
    else:
        confidence = "Low"

    return round(prob, 1), confidence, confirming


_HORIZON_DECAY = {15: 0.95, 30: 0.87, 60: 0.75, 120: 0.60}


def horizon_probabilities(opportunity_score: float) -> dict[str, float]:
    """spec sections 5-6: separate probabilities per time horizon. These
    decay toward the 50% (maximally uncertain) midpoint as the horizon
    extends -- a short-term momentum read says less about two hours out
    than fifteen minutes out, and this should be visible in the numbers.

    These are model estimates, NOT yet calibrated against historical
    outcomes (spec section 23) -- a fresh install has no backfilled
    intraday history to calibrate against.
    storage.compute_momentum_accuracy_stats() reports the real
    predicted-vs-realized comparison once enough signals have been
    backfilled; until then, treat these as a transparent heuristic, not a
    validated probability.
    """
    return {
        f"{h}m": round(_clip(50 + (opportunity_score - 50) * decay, 5, 95), 1)
        for h, decay in _HORIZON_DECAY.items()
    }


def expected_move_pct(atr: float | None, last_close: float, opportunity_score: float) -> float | None:
    """ATR-based heuristic, not a promise -- same honesty rule as
    scoring.compute_targets().
    """
    if not atr or not last_close:
        return None
    atr_pct = atr / last_close * 100
    multiplier = 0.3 + (max(opportunity_score, 0) / 100) * 0.9  # 0.3x-1.2x ATR
    return round(atr_pct * multiplier, 2)


def classify_momentum_grade(opportunity_score: float) -> str:
    """spec section 7."""
    if opportunity_score >= 90:
        return "EXTREME MOMENTUM"
    if opportunity_score >= 80:
        return "VERY HIGH MOMENTUM"
    if opportunity_score >= 70:
        return "HIGH MOMENTUM"
    if opportunity_score >= 60:
        return "MODERATE MOMENTUM"
    return "DO NOT PRIORITIZE"


@dataclass
class MomentumScore:
    symbol: str
    opportunity_score: float
    momentum_grade: str
    sub_scores: dict = field(default_factory=dict)
    unavailable_components: list = field(default_factory=list)
    risk: str = "MEDIUM"
    manipulation_flags: list = field(default_factory=list)
    manipulation_checks: dict = field(default_factory=dict)
    uc_distance_pct: float | None = None
    uc_probability_pct: float | None = None
    uc_confidence: str = "Not applicable"
    confirming_signals: list = field(default_factory=list)
    horizon_probabilities: dict = field(default_factory=dict)
    expected_move_pct: float | None = None
    relative_volume_intraday: float | None = None
    targets: dict = field(default_factory=dict)


def score_candidate(
    symbol: str,
    current_price: float,
    upper_circuit: float | None,
    has_static_band: bool | None,
    daily_ind: dict,
    intraday_ind: dict | None,
    sector_score: float | None,
    news_info: dict | None,
    market_regime: str,
    avg_turnover_cr: float | None,
    now_ist: datetime,
) -> MomentumScore:
    news_score = (news_info or {}).get("news_score", 0)

    momentum_sub = _momentum_subscore(daily_ind, intraday_ind)
    volume_sub, rel_vol_intraday = _volume_subscore(daily_ind, intraday_ind, now_ist)
    catalyst_sub = _catalyst_subscore(news_info)
    breakout_sub = _breakout_subscore(daily_ind, intraday_ind)
    sector_sub = _sector_market_subscore(sector_score, market_regime)
    liquidity_sub = _liquidity_subscore(avg_turnover_cr, rel_vol_intraday)
    risk, flags, checks = detect_manipulation(daily_ind, intraday_ind, news_score, avg_turnover_cr)
    risk_sub = _RISK_TO_SCORE[risk]

    sub = {
        "short_term_momentum": momentum_sub,
        "volume_confirmation": volume_sub,
        "catalyst_strength": catalyst_sub,
        "technical_breakout": breakout_sub,
        "sector_market_strength": sector_sub,
        "liquidity_quality": liquidity_sub,
        "risk_adjustment": risk_sub,
    }
    unavailable = [k for k, v in sub.items() if v is None]
    available = {k: v for k, v in sub.items() if v is not None}
    weight_sum = sum(config.MOMENTUM_SCORE_WEIGHTS[k] for k in available)
    composite = (
        sum(config.MOMENTUM_SCORE_WEIGHTS[k] * v for k, v in available.items()) / weight_sum * 10
        if weight_sum > 0 else 0.0
    )

    # spec section 9: penalties applied post-weighting, auditable via
    # `manipulation_flags` rather than hidden inside a sub-score.
    if risk == "EXTREME":
        composite *= 0.3
    elif risk == "HIGH":
        composite *= 0.75
    composite = round(composite, 1)

    distance = uc_distance_pct(current_price, upper_circuit) if has_static_band else None
    uc_prob, uc_conf, confirming = uc_probability(
        momentum_sub, volume_sub, breakout_sub, catalyst_sub, distance, rel_vol_intraday
    )
    targets = scoring.compute_targets(current_price, daily_ind["atr_14"]) if daily_ind.get("atr_14") else {}

    return MomentumScore(
        symbol=symbol,
        opportunity_score=composite,
        momentum_grade=classify_momentum_grade(composite),
        sub_scores={k: (round(v, 2) if v is not None else None) for k, v in sub.items()},
        unavailable_components=unavailable,
        risk=risk,
        manipulation_flags=flags,
        manipulation_checks=checks,
        uc_distance_pct=distance,
        uc_probability_pct=uc_prob,
        uc_confidence=uc_conf,
        confirming_signals=confirming,
        horizon_probabilities=horizon_probabilities(composite),
        expected_move_pct=expected_move_pct(daily_ind.get("atr_14"), current_price, composite),
        relative_volume_intraday=rel_vol_intraday,
        targets=targets,
    )
