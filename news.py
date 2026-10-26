"""News scanner: RSS headlines + keyword-based catalyst scoring.

This is deliberately a lexicon, not an NLP sentiment model -- it's
auditable (you can see exactly why a headline scored what it did) and
needs no API key. The natural upgrade path is swapping score_headline()
for an LLM classification call (e.g. Claude Haiku, cheap enough to run
per-headline) if the keyword approach proves too coarse; keep the same
(score, tags) return shape and nothing downstream needs to change.
"""
import re
from datetime import datetime, timezone

import feedparser
import requests

import config

log = config.get_logger(__name__)

# Positive catalysts -> spec section 5 / 14. Score contribution is additive
# and clipped to [-10, 10] per headline.
POSITIVE_KEYWORDS = {
    r"order win|bags order|wins order|contract worth|order book": 6,
    r"defence order|defense order|railway order|government order": 7,
    r"beats estimates|earnings beat|profit (jumps|surges|soars)|net profit (rose|up|grew)": 6,
    r"revenue growth|record revenue|record profit": 4,
    r"acquisition|acquires|merger|stake sale to": 5,
    r"regulatory approval|drug approval|usfda approval|nod from": 6,
    r"capacity expansion|new plant|expansion plan": 3,
    r"buyback": 3,
    r"bonus share|stock split": 3,
    r"dividend": 2,
    r"credit rating upgrade|rating upgraded|upgraded to aaa": 5,
    r"analyst upgrade|brokerage (raises|upgrades)|target price raised": 4,
    r"positive guidance|strong guidance|raises guidance": 5,
    r"fii buying|institutional buying|block deal.*(institut|mutual fund)": 3,
}

NEGATIVE_KEYWORDS = {
    r"sebi (bars|action|order against|probe)|sfio probe": -7,
    r"fraud|scam|forensic audit": -8,
    r"promoter.*(sold|sells|pledge|pledged)|pledge.*promoter": -4,
    r"credit rating downgrade|downgraded to": -5,
    r"earnings miss|profit (falls|drops|plunges)|net loss": -6,
    r"resign(s|ed|ation).*(ceo|cfo|md|director)|management exit": -5,
    r"litigation|lawsuit|court order against": -4,
    r"debt (concerns|default|restructuring)": -6,
    r"auditor resign|auditor.*resign": -4,
    r"regulatory action|penalty imposed|fine imposed": -5,
}

_COMPILED_POSITIVE = [(re.compile(p, re.I), s) for p, s in POSITIVE_KEYWORDS.items()]
_COMPILED_NEGATIVE = [(re.compile(p, re.I), s) for p, s in NEGATIVE_KEYWORDS.items()]

_SUFFIXES_TO_STRIP = re.compile(
    r"\b(ltd\.?|limited|the|and|of|corp\.?|corporation|company|co\.?|inc\.?)\b", re.I
)


def fetch_headlines(max_per_feed: int = 40) -> list[dict]:
    headlines = []
    for source, url in config.RSS_FEEDS.items():
        try:
            resp = requests.get(
                url, headers={"User-Agent": config.USER_AGENT}, timeout=config.HTTP_TIMEOUT
            )
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            for entry in parsed.entries[:max_per_feed]:
                headlines.append(
                    {
                        "source": source,
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", ""),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                    }
                )
        except Exception:
            log.exception("Failed to fetch RSS feed %s (%s)", source, url)
    log.info("Fetched %d headlines across %d feeds", len(headlines), len(config.RSS_FEEDS))
    return headlines


def score_headline(text: str) -> tuple[int, list[str]]:
    score = 0
    tags = []
    for pattern, weight in _COMPILED_POSITIVE + _COMPILED_NEGATIVE:
        if pattern.search(text):
            score += weight
            tags.append(pattern.pattern.split("|")[0])
    return max(-10, min(10, score)), tags


def _normalized_name_tokens(company_name: str) -> list[str]:
    cleaned = _SUFFIXES_TO_STRIP.sub("", company_name).strip()
    tokens = [t for t in re.split(r"\s+", cleaned) if len(t) > 2]
    return tokens


def map_news_to_universe(headlines: list[dict], instruments: list) -> dict[str, dict]:
    """Aggregate a per-symbol news score from headline text matches.

    Matching is a coarse substring heuristic (company-name tokens against
    headline title+summary) -- good enough to flag "this stock had press
    today," not a guarantee every relevant headline is caught or that every
    match is truly about that company (e.g. common words can false-positive).
    """
    result: dict[str, dict] = {}
    for inst in instruments:
        tokens = _normalized_name_tokens(inst.name)
        if not tokens:
            continue
        matched = []
        for h in headlines:
            haystack = f"{h['title']} {h['summary']}".lower()
            if inst.symbol.lower() in haystack or any(t.lower() in haystack for t in tokens[:2]):
                matched.append(h)
        if not matched:
            continue
        scores_tags = [score_headline(f"{h['title']} {h['summary']}") for h in matched]
        agg_score = max(-10, min(10, sum(s for s, _ in scores_tags)))
        all_tags = sorted({t for _, tags in scores_tags for t in tags})
        result[inst.symbol] = {
            "news_score": agg_score,
            "headline_count": len(matched),
            "tags": all_tags,
            "headlines": [h["title"] for h in matched][:5],
        }
    return result


def fetched_at() -> str:
    return datetime.now(timezone.utc).isoformat()
