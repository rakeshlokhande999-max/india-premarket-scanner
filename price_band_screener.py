"""Price-band screener: buckets a broad NSE universe (Nifty Total Market +
Nifty Microcap 250 -- see market_data.fetch_broad_universe) into price bands
and reports each name's last close + day change %.

This is a separate, simpler read from the Nifty-50 premarket scanner
(scanner.py): no composite scoring, no targets/stop-loss, because that
model's risk assumptions (liquidity, volume) were built for Nifty-50 names
and don't hold for micro-caps. Just real price + day change, bucketed.

Usage:
    python price_band_screener.py            # default bands
    python price_band_screener.py --bands 10-30,30-60,60-100,100-250,250-999999

Writes data/price_bands.json (read by nothing else yet -- standalone report).
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta

import yfinance as yf

import config
import market_data

log = config.get_logger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_BANDS = [
    (10, 30),
    (30, 60),
    (60, 100),
    (100, 250),
    (250, float("inf")),
]


def parse_bands(spec: str) -> list[tuple[float, float]]:
    bands = []
    for part in spec.split(","):
        lo, hi = part.split("-")
        bands.append((float(lo), float(hi) if float(hi) < 999999 else float("inf")))
    return bands


def fetch_quotes(yf_tickers: list[str]) -> dict[str, dict]:
    """Batch download last 2 daily closes for every ticker in one shot
    (yfinance threads internally). Returns {yf_ticker: {"last_close":...,
    "prev_close":...}}; a ticker missing from the result (delisted, no
    history, yfinance miss) is simply absent -- never backfilled with a
    guess.
    """
    quotes: dict[str, dict] = {}
    if not yf_tickers:
        return quotes
    try:
        data = yf.download(
            yf_tickers,
            period="5d",
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
        )
    except Exception:
        log.exception("Batch quote download failed")
        return quotes

    for ticker in yf_tickers:
        try:
            if len(yf_tickers) == 1:
                closes = data["Close"].dropna()
            else:
                closes = data[ticker]["Close"].dropna()
            if len(closes) < 2:
                continue
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            quotes[ticker] = {
                "last_close": round(last, 2),
                "day_change_pct": round((last - prev) / prev * 100, 2),
            }
        except Exception:
            continue
    return quotes


def run(bands: list[tuple[float, float]]) -> dict:
    universe = market_data.fetch_broad_universe()
    if not universe:
        return {"error": "Could not fetch broad universe (NSE archive unreachable)", "bands": {}}

    quotes = fetch_quotes([inst.yf_ticker for inst in universe])

    bucketed = {f"{lo:g}-{hi:g}" if hi != float("inf") else f"{lo:g}+": []
                for lo, hi in bands}
    unmatched_price = 0

    for inst in universe:
        q = quotes.get(inst.yf_ticker)
        if not q:
            continue
        price = q["last_close"]
        placed = False
        for lo, hi in bands:
            if lo <= price < hi:
                key = f"{lo:g}-{hi:g}" if hi != float("inf") else f"{lo:g}+"
                bucketed[key].append({
                    "symbol": inst.symbol,
                    "name": inst.name,
                    "sector": inst.sector,
                    "last_close": price,
                    "day_change_pct": q["day_change_pct"],
                })
                placed = True
                break
        if not placed:
            unmatched_price += 1  # below lowest band's lo (e.g. <10)

    for key in bucketed:
        bucketed[key].sort(key=lambda r: -r["day_change_pct"])

    return {
        "generated_at": datetime.now(IST).isoformat(),
        "universe_size": len(universe),
        "quoted": len(quotes),
        "unquoted": len(universe) - len(quotes),
        "below_lowest_band": unmatched_price,
        "bands": bucketed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bands", default=None,
                         help="comma-separated lo-hi pairs, e.g. 10-30,30-60,60-100,100-250,250-999999")
    args = parser.parse_args()
    bands = parse_bands(args.bands) if args.bands else DEFAULT_BANDS

    result = run(bands)
    out_path = "./data/price_bands.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    if result.get("error"):
        log.error(result["error"])
        sys.exit(1)

    print(f"Universe: {result['universe_size']} | Quoted: {result['quoted']} | "
          f"Unquoted (no data): {result['unquoted']} | Below lowest band: {result['below_lowest_band']}")
    for key, rows in result["bands"].items():
        print(f"\n=== Rs {key} ({len(rows)} names) ===")
        for r in rows:
            print(f"  {r['symbol']:14s} {r['last_close']:>9.2f}  {r['day_change_pct']:+6.2f}%  {r['name']}")
    print(f"\nFull data written to {out_path}")


if __name__ == "__main__":
    main()
