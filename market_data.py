"""Market data access: Nifty-50 universe, OHLCV history, index snapshots.

Backed by yfinance (free, ~15-minute-delayed NSE quotes) and NSE's own
public constituent list. No API key required. Swap-in point for a real
broker feed (Kite Connect / Upstox / Angel One) is fetch_ohlcv() and
fetch_index_snapshot() -- keep the same return shape and everything
downstream (indicators, scoring) keeps working unchanged.
"""
import io
from dataclasses import dataclass

import pandas as pd
import requests
import yfinance as yf

import config

log = config.get_logger(__name__)


@dataclass
class Instrument:
    symbol: str          # NSE symbol, e.g. "RELIANCE"
    yf_ticker: str        # yfinance ticker, e.g. "RELIANCE.NS"
    name: str
    sector: str


def fetch_universe() -> list[Instrument]:
    """Live Nifty-50 constituent list with sector classification.

    Falls back to an empty list (never a stale hardcoded one) if NSE's
    archive is unreachable -- callers must handle an empty universe
    rather than silently scanning stale/wrong constituents.
    """
    try:
        resp = requests.get(
            config.NIFTY50_CONSTITUENTS_URL,
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        instruments = [
            Instrument(
                symbol=row["Symbol"].strip(),
                yf_ticker=f"{row['Symbol'].strip()}.NS",
                name=row["Company Name"].strip(),
                sector=row["Industry"].strip(),
            )
            for _, row in df.iterrows()
        ]
        log.info("Fetched %d Nifty-50 constituents from NSE archive", len(instruments))
        return instruments[: config.UNIVERSE_LIMIT]
    except Exception:
        log.exception("Failed to fetch Nifty-50 constituent list")
        return []


def _fetch_index_csv(url: str) -> list[Instrument]:
    """Shared parser for NSE's per-index constituent CSVs (same 5-column
    shape as the Nifty-50 one). Returns [] on failure -- never partial/stale
    data passed off as current.
    """
    resp = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    return [
        Instrument(
            symbol=row["Symbol"].strip(),
            yf_ticker=f"{row['Symbol'].strip()}.NS",
            name=row["Company Name"].strip(),
            sector=row["Industry"].strip(),
        )
        for _, row in df.iterrows()
    ]


def fetch_broad_universe() -> list[Instrument]:
    """Union of Nifty Total Market + Nifty Microcap 250 constituents, deduped
    by symbol. Used by the price-band screener, which needs real coverage
    below the large-cap-only Nifty-50 range. Not a substitute for NSE's full
    ~2000-symbol exchange list (no single clean public CSV for that exists);
    this is the broadest *reliable* index-backed real list available.

    Returns [] if both sources fail; a partial union if only one does.
    """
    instruments: dict[str, Instrument] = {}
    for label, url in (
        ("Nifty Total Market", config.NIFTY_TOTAL_MARKET_URL),
        ("Nifty Microcap 250", config.NIFTY_MICROCAP250_URL),
    ):
        try:
            rows = _fetch_index_csv(url)
            for inst in rows:
                instruments.setdefault(inst.symbol, inst)
            log.info("Fetched %d constituents from %s", len(rows), label)
        except Exception:
            log.exception("Failed to fetch %s constituent list", label)
    return list(instruments.values())


def fetch_ohlcv(yf_ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Daily OHLCV history. Returns an empty DataFrame on failure."""
    try:
        df = yf.Ticker(yf_ticker).history(period=period, interval="1d")
        if df.empty:
            log.warning("No OHLCV data returned for %s", yf_ticker)
        return df
    except Exception:
        log.exception("Failed to fetch OHLCV for %s", yf_ticker)
        return pd.DataFrame()


def fetch_ohlcv_batch(yf_tickers: list[str], period: str = "1y", interval: str = "1d") -> dict[str, pd.DataFrame]:
    """Batched OHLCV fetch: as few network round-trips as yfinance's own
    chunking needs to cover the whole ticker list, instead of one call per
    symbol. Used by the AI Momentum Scanner to run indicators over a broad
    universe (or a shortlist's intraday bars) without a request per name.

    Returns {yf_ticker: DataFrame}; a ticker that's missing, delisted, or
    has any-NaN rows for the OHLCV columns is simply absent from the
    result -- never backfilled with a guess.
    """
    result: dict[str, pd.DataFrame] = {}
    if not yf_tickers:
        return result
    try:
        data = yf.download(
            yf_tickers, period=period, interval=interval, group_by="ticker",
            threads=True, progress=False, auto_adjust=False,
        )
    except Exception:
        log.exception(
            "Batched OHLCV download failed (period=%s interval=%s, %d tickers)",
            period, interval, len(yf_tickers),
        )
        return result

    for ticker in yf_tickers:
        try:
            raw = data[ticker] if len(yf_tickers) > 1 else data
            df = raw.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
            if not df.empty:
                result[ticker] = df
        except Exception:
            continue
    log.info("Batched OHLCV: %d/%d tickers returned usable data (period=%s interval=%s)",
              len(result), len(yf_tickers), period, interval)
    return result


def fetch_index_snapshot() -> dict[str, dict]:
    """Latest close + % change for each tracked index."""
    snapshot = {}
    for label, ticker in config.INDEX_TICKERS.items():
        try:
            df = yf.Ticker(ticker).history(period="5d", interval="1d")
            if len(df) < 2:
                log.warning("Not enough history for index %s", label)
                continue
            last, prev = df["Close"].iloc[-1], df["Close"].iloc[-2]
            snapshot[label] = {
                "price": round(float(last), 2),
                "change_pct": round(float((last - prev) / prev * 100), 2),
                "as_of": str(df.index[-1]),
            }
        except Exception:
            log.exception("Failed to fetch index snapshot for %s", label)
    return snapshot
