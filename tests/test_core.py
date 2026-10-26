"""Fast, no-network unit tests -- run with: python -m pytest tests/ -q
These check the math/logic layer only; market_data/nse_live/news hit
real endpoints and are exercised via `python scanner.py scan` instead
(an integration smoke test, not a unit test suited to CI on every commit).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from datetime import datetime, timedelta, timezone

import config
import indicators
import momentum_scoring
import scoring


def _synthetic_ohlcv(n=120, start=100.0, daily_drift=0.3, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + daily_drift / 100 + rng.normal(0, 0.01)))
    closes = np.array(closes)
    highs = closes * (1 + abs(rng.normal(0, 0.005, n)))
    lows = closes * (1 - abs(rng.normal(0, 0.005, n)))
    opens = closes * (1 + rng.normal(0, 0.003, n))
    volumes = rng.integers(500_000, 1_500_000, n)
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes}, index=idx
    )


def test_weights_sum_to_one():
    assert abs(sum(config.SCORE_WEIGHTS.values()) - 1.0) < 1e-9


def test_indicators_none_on_short_history():
    short_df = _synthetic_ohlcv(n=10)
    assert indicators.compute_indicators(short_df) is None


def test_indicators_uptrend_has_bullish_ema_alignment():
    df = _synthetic_ohlcv(n=220, daily_drift=0.4)
    ind = indicators.compute_indicators(df)
    assert ind is not None
    assert ind["ema_alignment_bullish_count"] >= ind["ema_alignment_total"] - 1
    assert ind["rsi_14"] > 50


def test_indicators_downtrend_has_low_rsi():
    df = _synthetic_ohlcv(n=220, daily_drift=-0.4)
    ind = indicators.compute_indicators(df)
    assert ind["rsi_14"] < 50


def test_market_regime_high_vix_forces_high_risk():
    assert scoring.classify_market_regime(nifty_change_pct=1.5, india_vix=25) == "HIGH RISK"


def test_market_regime_strong_bullish_needs_breadth():
    assert scoring.classify_market_regime(1.5, india_vix=12, breadth_pct=70) == "STRONG BULLISH"
    assert scoring.classify_market_regime(1.5, india_vix=12, breadth_pct=30) == "BULLISH"


def test_targets_are_ordered_and_positive_risk_reward():
    t = scoring.compute_targets(last_close=1000.0, atr=20.0)
    assert t["target_1"] < t["target_2"] < t["target_3"]
    assert t["stop_loss"] < 1000.0
    assert t["risk_reward_ratio"] > 0


def test_extreme_risk_from_very_negative_news():
    df = _synthetic_ohlcv(n=220)
    ind = indicators.compute_indicators(df)
    risk = scoring.classify_risk(ind, news_score=-8, avg_turnover_cr=50)
    assert risk == "EXTREME"


def test_score_instrument_handles_missing_optional_inputs():
    df = _synthetic_ohlcv(n=220, daily_drift=0.5)
    ind = indicators.compute_indicators(df)
    result = scoring.score_instrument(
        symbol="TEST",
        ind=ind,
        market_regime="BULLISH",
        sector_score=None,       # sector data unavailable
        news_info=None,          # no news matched
        fii_net_cr=None,
        dii_net_cr=None,
        preopen_change_pct=None,  # outside 9:00-9:15 IST window
        avg_turnover_cr=40,
    )
    assert 0 <= result.composite_score <= 100
    assert "sector_momentum" in result.unavailable_components
    assert "news_catalyst" in result.unavailable_components
    assert "pre_open_strength" in result.unavailable_components


def test_score_label_thresholds():
    assert scoring.score_label(95) == "Exceptional setup"
    assert scoring.score_label(55) == "Weak"
    assert scoring.score_label(10) == "Avoid"


# --- AI Momentum / Upper-Circuit Scanner (momentum_scoring.py) ---

IST = timezone(timedelta(hours=5, minutes=30))


def test_momentum_weights_sum_to_one():
    assert abs(sum(config.MOMENTUM_SCORE_WEIGHTS.values()) - 1.0) < 1e-9


def test_uc_distance_matches_spec_example():
    # app-info.md section 4's own worked example: 42.50 -> 44.60 == 4.94%
    assert momentum_scoring.uc_distance_pct(42.50, 44.60) == 4.94


def test_uc_distance_none_without_a_static_band():
    assert momentum_scoring.uc_distance_pct(100.0, None) is None


def test_uc_probability_none_without_distance():
    prob, confidence, confirming = momentum_scoring.uc_probability(
        momentum_sub=8, volume_sub=8, breakout_sub=8, catalyst_sub=8,
        distance_pct=None, relative_volume=2.0,
    )
    assert prob is None
    assert confidence == "Not applicable"
    assert confirming == []


def test_uc_probability_high_confidence_needs_multiple_signals():
    prob, confidence, confirming = momentum_scoring.uc_probability(
        momentum_sub=8, volume_sub=8, breakout_sub=8, catalyst_sub=8,
        distance_pct=3.0, relative_volume=2.0,
    )
    assert confidence == "High"
    assert len(confirming) >= 3
    assert 0 < prob < 100  # never displayed as a guarantee


def test_uc_probability_price_move_alone_is_not_high_confidence():
    # Only momentum is strong; no confirming volume/catalyst/breakout --
    # spec section 8's own example (price increase alone != high confidence).
    prob, confidence, confirming = momentum_scoring.uc_probability(
        momentum_sub=8, volume_sub=3, breakout_sub=3, catalyst_sub=None,
        distance_pct=3.0, relative_volume=None,
    )
    assert confidence != "High"


def test_classify_momentum_grade_thresholds():
    assert momentum_scoring.classify_momentum_grade(95) == "EXTREME MOMENTUM"
    assert momentum_scoring.classify_momentum_grade(85) == "VERY HIGH MOMENTUM"
    assert momentum_scoring.classify_momentum_grade(75) == "HIGH MOMENTUM"
    assert momentum_scoring.classify_momentum_grade(65) == "MODERATE MOMENTUM"
    assert momentum_scoring.classify_momentum_grade(40) == "DO NOT PRIORITIZE"


def test_horizon_probabilities_decay_toward_midpoint():
    probs = momentum_scoring.horizon_probabilities(90)
    # further out == closer to the uncertain 50% midpoint for a strong score
    assert probs["15m"] > probs["30m"] > probs["60m"] > probs["120m"] > 50


def test_detect_manipulation_flags_low_liquidity_as_extreme():
    df = _synthetic_ohlcv(n=220, daily_drift=0.3)
    ind = indicators.compute_indicators(df)
    risk, flags, checks = momentum_scoring.detect_manipulation(ind, None, news_score=0, avg_turnover_cr=2.0)
    assert risk == "EXTREME"
    assert any("liquidity" in f.lower() for f in flags)
    assert checks["wide_bid_ask_spread"] == "unavailable_no_data_source"


def test_score_candidate_handles_missing_optional_inputs():
    df = _synthetic_ohlcv(n=220, daily_drift=0.5)
    ind = indicators.compute_indicators(df)
    result = momentum_scoring.score_candidate(
        symbol="TEST",
        current_price=ind["last_close"],
        upper_circuit=None,          # no static band -- most Nifty-50 names
        has_static_band=False,
        daily_ind=ind,
        intraday_ind=None,           # no intraday bars available
        sector_score=None,           # sector data unavailable
        news_info=None,              # no news matched
        market_regime="BULLISH",
        avg_turnover_cr=40,
        now_ist=datetime(2026, 8, 24, 11, 0, tzinfo=IST),
    )
    assert 0 <= result.opportunity_score <= 100
    assert result.uc_distance_pct is None
    assert result.uc_probability_pct is None
    assert result.uc_confidence == "Not applicable"
    assert "sector_market_strength" in result.unavailable_components
    assert "catalyst_strength" in result.unavailable_components
