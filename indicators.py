"""Technical indicators computed from real OHLCV history via the `ta`
library. Every value here is a genuine calculation on real price/volume
data -- nothing here is a placeholder or an invented number.
"""
import pandas as pd
from ta.momentum import ROCIndicator, RSIIndicator, StochRSIIndicator
from ta.trend import ADXIndicator, EMAIndicator, MACD
from ta.volatility import AverageTrueRange, BollingerBands

import config

log = config.get_logger(__name__)

MIN_ROWS_REQUIRED = 60  # need ~60 daily bars for a stable 50-EMA/ADX read


def compute_indicators(df: pd.DataFrame) -> dict | None:
    """Returns a flat dict of indicator values as of the last row, or
    None if there isn't enough history to compute them reliably.
    """
    if df is None or len(df) < MIN_ROWS_REQUIRED:
        return None

    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]

    emas = {
        f"ema_{span}": EMAIndicator(close, window=span).ema_indicator().iloc[-1]
        for span in (5, 9, 20, 50, 100, 200)
        if len(df) >= span
    }

    rsi = RSIIndicator(close, window=14).rsi().iloc[-1]
    stoch_rsi = StochRSIIndicator(close, window=14).stochrsi().iloc[-1] * 100
    macd_ind = MACD(close)
    macd_line = macd_ind.macd().iloc[-1]
    macd_signal = macd_ind.macd_signal().iloc[-1]
    macd_hist = macd_ind.macd_diff().iloc[-1]
    adx = ADXIndicator(high, low, close, window=14).adx().iloc[-1]
    atr = AverageTrueRange(high, low, close, window=14).average_true_range().iloc[-1]
    roc = ROCIndicator(close, window=10).roc().iloc[-1]

    avg_volume_20 = volume.rolling(20).mean().iloc[-1]
    last_volume = volume.iloc[-1]
    relative_volume = float(last_volume / avg_volume_20) if avg_volume_20 else None

    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    day_change_pct = (last_close - prev_close) / prev_close * 100 if prev_close else 0.0

    trend_up_count = sum(1 for v in emas.values() if last_close > v)

    return {
        "last_close": round(last_close, 2),
        "prev_close": round(prev_close, 2),
        "day_change_pct": round(day_change_pct, 2),
        "prev_day_high": round(float(high.iloc[-2]), 2),
        "prev_day_low": round(float(low.iloc[-2]), 2),
        "week_high": round(float(high.tail(5).max()), 2),
        "week_low": round(float(low.tail(5).min()), 2),
        "high_52w": round(float(high.tail(252).max()), 2) if len(df) >= 50 else None,
        "low_52w": round(float(low.tail(252).min()), 2) if len(df) >= 50 else None,
        **{k: round(float(v), 2) for k, v in emas.items()},
        "ema_alignment_bullish_count": trend_up_count,
        "ema_alignment_total": len(emas),
        "rsi_14": round(float(rsi), 2) if pd.notna(rsi) else None,
        "stoch_rsi": round(float(stoch_rsi), 2) if pd.notna(stoch_rsi) else None,
        "macd": round(float(macd_line), 4) if pd.notna(macd_line) else None,
        "macd_signal": round(float(macd_signal), 4) if pd.notna(macd_signal) else None,
        "macd_hist": round(float(macd_hist), 4) if pd.notna(macd_hist) else None,
        "adx_14": round(float(adx), 2) if pd.notna(adx) else None,
        "atr_14": round(float(atr), 2) if pd.notna(atr) else None,
        "roc_10": round(float(roc), 2) if pd.notna(roc) else None,
        "avg_volume_20": round(float(avg_volume_20), 0) if pd.notna(avg_volume_20) else None,
        "last_volume": int(last_volume),
        "relative_volume": round(relative_volume, 2) if relative_volume else None,
    }


INTRADAY_MIN_ROWS_REQUIRED = 6  # ~30 minutes of 5-minute bars -- enough for an opening range


def compute_intraday_indicators(df: pd.DataFrame, prev_close: float | None) -> dict | None:
    """Short-term (intraday-bar) indicators for the AI Momentum Scanner --
    spec section 2's intraday half (VWAP, opening-range breakout, EMA9/20,
    Bollinger %B, gap strength), layered on top of compute_indicators()'s
    daily-bar view rather than replacing it.

    `df` is intraday OHLCV (5-minute bars expected); `prev_close` is the
    *prior session's* close (from compute_indicators' "prev_close"), used
    for gap % since the intraday frame alone doesn't carry it.

    Returns None if there isn't enough same-session history yet (e.g. the
    first few minutes after open, or no bars for today at all) -- never a
    guess standing in for a real reading.
    """
    if df is None or df.empty or not prev_close:
        return None

    today = df.index[-1].date()
    session = df[df.index.date == today]
    if len(session) < INTRADAY_MIN_ROWS_REQUIRED:
        return None

    close, high, low, volume = session["Close"], session["High"], session["Low"], session["Volume"]
    ltp = float(close.iloc[-1])
    open_price = float(session["Open"].iloc[0])
    gap_pct = round((open_price - prev_close) / prev_close * 100, 2) if prev_close else None

    or_bars = min(len(session), 6)  # first ~30 minutes at 5-min bars
    opening_range_high = float(session["High"].iloc[:or_bars].max())
    opening_range_low = float(session["Low"].iloc[:or_bars].min())

    typical_price = (high + low + close) / 3
    vwap_den = volume.cumsum().iloc[-1]
    vwap = float((typical_price * volume).cumsum().iloc[-1] / vwap_den) if vwap_den else None

    ema9 = EMAIndicator(close, window=9).ema_indicator().iloc[-1] if len(session) >= 9 else None
    ema20 = EMAIndicator(close, window=20).ema_indicator().iloc[-1] if len(session) >= 20 else None
    rsi_i = RSIIndicator(close, window=14).rsi().iloc[-1] if len(session) >= 15 else None
    bb_pct_b = None
    if len(session) >= 20:
        val = BollingerBands(close, window=20).bollinger_pband().iloc[-1]
        bb_pct_b = float(val) if pd.notna(val) else None

    def _clean(v):
        return round(float(v), 2) if v is not None and pd.notna(v) else None

    ema9_c, ema20_c = _clean(ema9), _clean(ema20)

    return {
        "ltp": round(ltp, 2),
        "session_open": round(open_price, 2),
        "gap_pct": gap_pct,
        "opening_range_high": round(opening_range_high, 2),
        "opening_range_low": round(opening_range_low, 2),
        "opening_range_breakout": ltp > opening_range_high,
        "vwap": round(vwap, 2) if vwap else None,
        "above_vwap": (ltp > vwap) if vwap else None,
        "ema9": ema9_c,
        "ema20": ema20_c,
        "ema9_above_ema20": (ema9_c > ema20_c) if ema9_c is not None and ema20_c is not None else None,
        "rsi_intraday": _clean(rsi_i),
        "bb_pct_b": round(bb_pct_b, 2) if bb_pct_b is not None else None,
        "session_volume": float(volume.sum()),
        "session_bars": len(session),
        "prev_day_close": round(float(prev_close), 2),
    }
