"""Direct calls to NSE's own public JSON endpoints: pre-open snapshot and
FII/DII cash-market flows. No API key -- these are the same endpoints
nseindia.com's own web pages call. They're undocumented and NSE can
change or rate-limit them without notice, so every call degrades to an
empty/None result plus a logged warning rather than raising -- a scan
should never crash because NSE reshuffled a response shape.
"""
import requests

import config

log = config.get_logger(__name__)

_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
}


def warmed_session() -> requests.Session:
    """NSE's API endpoints expect cookies set by first hitting the
    homepage. The homepage request itself may 403 (bot detection) while
    still setting a usable cookie -- so its status is ignored on purpose.

    Public so callers looping over many symbols (e.g. momentum.py's
    momentum scanner) can warm up once and reuse the session, instead of
    a fresh homepage hit per symbol.
    """
    session = requests.Session()
    try:
        session.get(config.NSE_HOME_URL, headers=_HEADERS, timeout=config.HTTP_TIMEOUT)
    except requests.RequestException:
        log.warning("NSE homepage warm-up request failed; continuing anyway")
    return session


_warmed_session = warmed_session  # backward-compat alias for in-module callers


def fetch_fii_dii() -> list[dict]:
    """Latest available FII/DII net cash-market flow (usually T-1, since
    same-day figures aren't published until after that session closes).

    Returns a list like:
        [{"category": "DII", "date": "21-Aug-2026", "netValue": "2124.14", ...}, ...]
    or [] on failure.
    """
    try:
        session = _warmed_session()
        resp = session.get(config.NSE_FII_DII_URL, headers=_HEADERS, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        log.info("Fetched FII/DII data: %d rows", len(data))
        return data
    except Exception:
        log.exception("Failed to fetch NSE FII/DII data")
        return []


_QUOTE_HEADERS = {**_HEADERS, "Accept": "application/json, text/plain, */*"}


def fetch_quote(symbol: str, session: requests.Session | None = None) -> dict | None:
    """Live-ish NSE quote for one symbol: LTP, VWAP, intraday high/low, and
    the exchange's own static price-band circuit limits (spec section 4).

    Many large/F&O-eligible names (most of Nifty-50) have NO static daily
    band -- they trade on a dynamically-adjusted operating range instead.
    NSE's API reports this as pPriceBand == "No Band". In that case
    upper_circuit/lower_circuit come back None and has_static_band is
    False; callers must show "not applicable", never invent a circuit
    value for a security that doesn't have a static one.

    Pass a pre-warmed `session` when calling this in a loop over many
    symbols to skip re-hitting the homepage warm-up every time.

    In practice this endpoint is behind a stricter WAF than
    fetch_fii_dii()/fetch_preopen() and can 403 even with a warmed session
    and browser-shaped headers -- observed in testing, not hypothetical.
    This function does not attempt to work around that (no header
    spoofing beyond a normal browser Accept header, no proxying, no retry
    storms); when it fails, upstream code treats the quote as unavailable
    for that name this run, same as any other missing data source. See
    README "Known limitations".

    Returns None on failure (network error, unknown symbol, WAF block, NSE
    reshaping the response) -- never a partial/fabricated quote.
    """
    try:
        sess = session or _warmed_session()
        url = config.NSE_QUOTE_URL.format(symbol=symbol)
        resp = sess.get(url, headers=_QUOTE_HEADERS, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        price = data.get("priceInfo", {}) or {}
        band = str(price.get("pPriceBand", "")).strip()
        has_band = band.lower() not in ("", "no band")
        intraday = price.get("intraDayHighLow") or {}

        def _to_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return {
            "symbol": symbol,
            "last_price": _to_float(price.get("lastPrice")),
            "previous_close": _to_float(price.get("previousClose")),
            "vwap": _to_float(price.get("vwap")),
            "intraday_high": _to_float(intraday.get("max")),
            "intraday_low": _to_float(intraday.get("min")),
            "price_band_pct": band if has_band else None,
            "has_static_band": has_band,
            "upper_circuit": _to_float(price.get("upperCP")) if has_band else None,
            "lower_circuit": _to_float(price.get("lowerCP")) if has_band else None,
            "as_of": data.get("lastUpdateTime"),
        }
    except Exception:
        log.exception("Failed to fetch NSE quote for %s", symbol)
        return None


def fetch_preopen(index: str = "NIFTY") -> dict:
    """NSE's pre-open session snapshot (advances/declines + per-stock
    indicative price and % change). Only meaningful ~9:00-9:15 IST on a
    trading day; outside that window NSE may return the prior session's
    data or an empty payload -- callers should sanity-check `as_of`-style
    freshness themselves (this endpoint doesn't reliably provide one).

    Returns {} on failure.
    """
    try:
        session = _warmed_session()
        url = config.NSE_PREOPEN_URL.format(key=index)
        resp = session.get(url, headers=_HEADERS, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        log.info(
            "Fetched pre-open snapshot for %s: %d advances, %d declines",
            index, payload.get("advances", 0), payload.get("declines", 0),
        )
        return payload
    except Exception:
        log.exception("Failed to fetch NSE pre-open snapshot for %s", index)
        return {}
