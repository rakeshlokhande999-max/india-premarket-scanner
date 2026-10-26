"""Central config, loaded from environment variables (.env in dev).

Nothing in this file is a secret. Anything sensitive (broker keys, a paid
news API key) is read from the environment only -- never hardcoded here,
never logged.
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("SCANNER_DB_PATH", "./data/scanner.db")
LOG_LEVEL = os.getenv("SCANNER_LOG_LEVEL", "INFO").upper()
HTTP_TIMEOUT = float(os.getenv("SCANNER_HTTP_TIMEOUT", "12"))
UNIVERSE_LIMIT = int(os.getenv("SCANNER_UNIVERSE_LIMIT", "50"))

BROKER_API_KEY = os.getenv("BROKER_API_KEY", "")
BROKER_API_SECRET = os.getenv("BROKER_API_SECRET", "")
BROKER_ACCESS_TOKEN = os.getenv("BROKER_ACCESS_TOKEN", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

NIFTY50_CONSTITUENTS_URL = (
    "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
)
# Broader universe for the price-band screener. NSE doesn't publish a single
# clean CSV for the full ~2000-stock exchange list the way it does for index
# constituents, so we union two real index lists instead: Nifty Total Market
# (large+mid+small cap, 750ish names) and Nifty Microcap 250 (the segment
# most likely to hold sub-Rs100 names). Both real NSE data, no invented list.
NIFTY_TOTAL_MARKET_URL = (
    "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"
)
NIFTY_MICROCAP250_URL = (
    "https://archives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv"
)
NSE_HOME_URL = "https://www.nseindia.com"
NSE_PREOPEN_URL = "https://www.nseindia.com/api/market-data-pre-open?key={key}"
NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
NSE_QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol={symbol}"

RSS_FEEDS = {
    "moneycontrol_business": "https://www.moneycontrol.com/rss/business.xml",
    "et_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "business_standard_markets": "https://www.business-standard.com/rss/markets-106.rss",
}

# Weighted scoring model -- section 16 of the spec this app implements.
# Must sum to 1.0; enforced by a test.
SCORE_WEIGHTS = {
    "market_trend": 0.10,
    "sector_momentum": 0.10,
    "news_catalyst": 0.15,
    "technical_trend": 0.15,
    "price_action": 0.10,
    "volume": 0.10,
    "pre_open_strength": 0.10,
    "institutional": 0.05,
    "momentum_indicators": 0.05,
    "risk_reward": 0.10,
}

TOP_N_CANDIDATES = 10

# --- AI Momentum / Upper-Circuit Scanner (app-info.md spec) ---
# NSE's quote-equity endpoint is undocumented, unauthenticated and
# per-symbol -- no public batch endpoint exists for arbitrary symbols. This
# cap is what keeps "Run Market Research" from taking minutes or tripping
# NSE's bot protection: only the top-ranked names (by a cheap batched daily
# pre-filter) get the expensive per-symbol live-quote + intraday-bar pass.
MOMENTUM_UNIVERSE_LIMIT = int(os.getenv("SCANNER_MOMENTUM_UNIVERSE_LIMIT", "60"))
NSE_QUOTE_DELAY_SEC = float(os.getenv("SCANNER_NSE_QUOTE_DELAY_SEC", "0.15"))
MOMENTUM_MIN_SCORE = 60  # spec section 7: below this, DO NOT PRIORITIZE -- excluded from the primary list
HORIZON_MINUTES = [15, 30, 60, 120]

# Final Opportunity Score weights -- spec section 14. Kept separate from
# SCORE_WEIGHTS (the pre-market daily model): different product surface,
# different inputs (live intraday bars + UC distance vs. next-session
# targets). Must sum to 1.0; enforced by a test.
MOMENTUM_SCORE_WEIGHTS = {
    "short_term_momentum": 0.35,
    "volume_confirmation": 0.20,
    "catalyst_strength": 0.15,
    "technical_breakout": 0.10,
    "sector_market_strength": 0.10,
    "liquidity_quality": 0.05,
    "risk_adjustment": 0.05,
}

INDEX_TICKERS = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "INDIA VIX": "^INDIAVIX",
    "NIFTY IT": "^CNXIT",
}


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(LOG_LEVEL)
    return logger
