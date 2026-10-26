"""SQLite-backed prediction / backtest store (spec section 26).

SQLite, not Postgres -- this is a single-user MVP with one writer per
day; a server-based DB is unjustified complexity until this runs for
multiple users or needs concurrent writers.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import config

log = config.get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,          -- the trading day this prediction is FOR
    run_time TEXT NOT NULL,          -- when the scan was generated (ISO8601, IST)
    symbol TEXT NOT NULL,
    sector TEXT,
    entry_zone TEXT,
    target_1 REAL,
    target_2 REAL,
    target_3 REAL,
    stop_loss REAL,
    composite_score REAL,
    confidence_pct REAL,
    risk TEXT,
    market_regime TEXT,
    reasoning TEXT,                  -- JSON blob: sub-scores, news tags, unavailable components
    -- filled in by the T+1 backfill job -- never same-day, to avoid lookahead leakage
    actual_high REAL,
    actual_low REAL,
    actual_close REAL,
    target_1_hit INTEGER,
    target_2_hit INTEGER,
    target_3_hit INTEGER,
    stop_loss_hit INTEGER,
    max_favorable_excursion_pct REAL,
    max_adverse_excursion_pct REAL,
    outcome_filled_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_predictions_run_date ON predictions(run_date);
CREATE INDEX IF NOT EXISTS idx_predictions_symbol ON predictions(symbol);

-- AI Momentum / Upper-Circuit Scanner (app-info.md sections 22-23, 26).
-- Deliberately a separate table from `predictions` above: different
-- product surface (intraday horizons vs. next-session targets), different
-- backfill cadence (minutes, not T+1 days) -- keeping them apart means
-- neither model's schema changes can break the other's history.
CREATE TABLE IF NOT EXISTS momentum_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,             -- ISO8601 IST timestamp of the research run
    symbol TEXT NOT NULL,
    sector TEXT,
    current_price REAL,
    upper_circuit REAL,               -- NULL when the security has no static price band
    uc_distance_pct REAL,
    opportunity_score REAL,
    momentum_grade TEXT,
    uc_probability_pct REAL,
    uc_confidence TEXT,
    risk TEXT,
    prob_15m REAL,
    prob_30m REAL,
    prob_60m REAL,
    prob_120m REAL,
    catalyst TEXT,
    reasoning TEXT,                   -- JSON blob: sub-scores, flags, reasons
    -- filled in by the horizon-backfill pass, one horizon at a time, only
    -- once that much real time has actually elapsed -- never early, never fabricated
    price_after_15m REAL,
    price_after_30m REAL,
    price_after_60m REAL,
    price_after_120m REAL,
    uc_reached INTEGER,
    fully_filled_at TEXT,             -- set once all four horizons above are filled
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_momentum_run_at ON momentum_signals(run_at);
CREATE INDEX IF NOT EXISTS idx_momentum_symbol ON momentum_signals(symbol);
"""


@contextmanager
def _connect():
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
    log.info("Database initialized at %s", config.DB_PATH)


def insert_prediction(pred: dict) -> int:
    fields = [
        "run_date", "run_time", "symbol", "sector", "entry_zone",
        "target_1", "target_2", "target_3", "stop_loss",
        "composite_score", "confidence_pct", "risk", "market_regime", "reasoning",
    ]
    values = [pred.get(f) for f in fields]
    values[fields.index("reasoning")] = json.dumps(pred.get("reasoning", {}))
    with _connect() as conn:
        cur = conn.execute(
            f"INSERT INTO predictions ({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})",
            values,
        )
        return cur.lastrowid


def get_predictions_needing_outcome(before_date: str) -> list[sqlite3.Row]:
    """Predictions run on/before `before_date` that don't have an outcome
    filled in yet -- candidates for the T+1 backfill job.
    """
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM predictions WHERE run_date <= ? AND outcome_filled_at IS NULL",
            (before_date,),
        ).fetchall()


def backfill_outcome(pred_id: int, actual_high: float, actual_low: float, actual_close: float, entry_ref: float) -> None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM predictions WHERE id = ?", (pred_id,)).fetchone()
        if row is None:
            return
        mfe_pct = round((actual_high - entry_ref) / entry_ref * 100, 2) if entry_ref else None
        mae_pct = round((actual_low - entry_ref) / entry_ref * 100, 2) if entry_ref else None
        conn.execute(
            """UPDATE predictions SET
                actual_high = ?, actual_low = ?, actual_close = ?,
                target_1_hit = ?, target_2_hit = ?, target_3_hit = ?, stop_loss_hit = ?,
                max_favorable_excursion_pct = ?, max_adverse_excursion_pct = ?,
                outcome_filled_at = datetime('now')
               WHERE id = ?""",
            (
                actual_high, actual_low, actual_close,
                int(row["target_1"] is not None and actual_high >= row["target_1"]),
                int(row["target_2"] is not None and actual_high >= row["target_2"]),
                int(row["target_3"] is not None and actual_high >= row["target_3"]),
                int(row["stop_loss"] is not None and actual_low <= row["stop_loss"]),
                mfe_pct, mae_pct, pred_id,
            ),
        )


def compute_accuracy_stats(since_date: str | None = None) -> dict:
    query = "SELECT * FROM predictions WHERE outcome_filled_at IS NOT NULL"
    params: tuple = ()
    if since_date:
        query += " AND run_date >= ?"
        params = (since_date,)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    n = len(rows)
    if n == 0:
        return {"n": 0}

    t1_hits = sum(r["target_1_hit"] or 0 for r in rows)
    t2_hits = sum(r["target_2_hit"] or 0 for r in rows)
    sl_hits = sum(r["stop_loss_hit"] or 0 for r in rows)
    mfe_values = [r["max_favorable_excursion_pct"] for r in rows if r["max_favorable_excursion_pct"] is not None]
    mae_values = [r["max_adverse_excursion_pct"] for r in rows if r["max_adverse_excursion_pct"] is not None]

    return {
        "n": n,
        "target_1_hit_rate_pct": round(t1_hits / n * 100, 1),
        "target_2_hit_rate_pct": round(t2_hits / n * 100, 1),
        "stop_loss_hit_rate_pct": round(sl_hits / n * 100, 1),
        "avg_max_favorable_excursion_pct": round(sum(mfe_values) / len(mfe_values), 2) if mfe_values else None,
        "avg_max_adverse_excursion_pct": round(sum(mae_values) / len(mae_values), 2) if mae_values else None,
    }


def get_recent(limit: int = 50) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM predictions ORDER BY run_date DESC, composite_score DESC LIMIT ?", (limit,)
        ).fetchall()


# --- AI Momentum / Upper-Circuit Scanner store ---

_MOMENTUM_FIELDS = [
    "run_at", "symbol", "sector", "current_price", "upper_circuit", "uc_distance_pct",
    "opportunity_score", "momentum_grade", "uc_probability_pct", "uc_confidence", "risk",
    "prob_15m", "prob_30m", "prob_60m", "prob_120m", "catalyst", "reasoning",
]


def insert_momentum_signal(sig: dict) -> int:
    """`sig` is a candidate dict as produced by momentum._candidate_to_dict(),
    plus `run_at`.
    """
    horizon = sig.get("horizon_probabilities", {})
    values = {
        "run_at": sig["run_at"],
        "symbol": sig["symbol"],
        "sector": sig.get("sector"),
        "current_price": sig.get("current_price"),
        "upper_circuit": sig.get("upper_circuit"),
        "uc_distance_pct": sig.get("uc_distance_pct"),
        "opportunity_score": sig.get("opportunity_score"),
        "momentum_grade": sig.get("momentum_grade"),
        "uc_probability_pct": sig.get("uc_probability_pct"),
        "uc_confidence": sig.get("uc_confidence"),
        "risk": sig.get("risk"),
        "prob_15m": horizon.get("15m"),
        "prob_30m": horizon.get("30m"),
        "prob_60m": horizon.get("60m"),
        "prob_120m": horizon.get("120m"),
        "catalyst": ", ".join(sig.get("news_tags", [])) or None,
        "reasoning": json.dumps({
            "sub_scores": sig.get("sub_scores"),
            "unavailable_components": sig.get("unavailable_components"),
            "manipulation_flags": sig.get("manipulation_flags"),
            "reasons": sig.get("reasons"),
        }),
    }
    with _connect() as conn:
        cur = conn.execute(
            f"INSERT INTO momentum_signals ({', '.join(_MOMENTUM_FIELDS)}) "
            f"VALUES ({', '.join(':' + f for f in _MOMENTUM_FIELDS)})",
            values,
        )
        return cur.lastrowid


def get_open_momentum_signals() -> list[sqlite3.Row]:
    """Signals with at least one horizon still unfilled -- callers check
    elapsed time themselves (Python-side, since `run_at` is a
    timezone-offset ISO string SQLite's datetime() can't compare directly).
    """
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM momentum_signals WHERE fully_filled_at IS NULL ORDER BY run_at"
        ).fetchall()


_VALID_HORIZON_FIELDS = {"price_after_15m", "price_after_30m", "price_after_60m", "price_after_120m"}


def backfill_momentum_horizon(signal_id: int, horizon_minutes: int, price: float, uc_reached: bool) -> None:
    field = f"price_after_{horizon_minutes}m"
    if field not in _VALID_HORIZON_FIELDS:
        raise ValueError(f"Unsupported horizon: {horizon_minutes}")
    with _connect() as conn:
        row = conn.execute("SELECT * FROM momentum_signals WHERE id = ?", (signal_id,)).fetchone()
        if row is None or row[field] is not None:
            return
        # max(), not COALESCE(): UC can first show reached on any horizon
        # (15m clear, 120m reached is a real, common shape) -- COALESCE
        # would lock in whatever the *first*-checked horizon saw and never
        # update on a later one that actually got there.
        conn.execute(
            f"UPDATE momentum_signals SET {field} = ?, uc_reached = max(COALESCE(uc_reached, 0), ?) WHERE id = ?",
            (price, int(uc_reached), signal_id),
        )
        refreshed = conn.execute("SELECT * FROM momentum_signals WHERE id = ?", (signal_id,)).fetchone()
        if all(refreshed[f"price_after_{h}m"] is not None for h in (15, 30, 60, 120)):
            conn.execute("UPDATE momentum_signals SET fully_filled_at = datetime('now') WHERE id = ?", (signal_id,))


def compute_momentum_accuracy_stats() -> dict:
    """spec section 23 (calibration), MVP scale: compares each horizon's
    average *predicted* probability against the *realized* rate of an
    upward move, plus the realized upper-circuit-reached rate among
    candidates that had a static band. Small-N until more signals have
    been backfilled -- report the n, don't pretend more precision than
    the sample supports.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM momentum_signals WHERE price_after_15m IS NOT NULL "
            "OR price_after_30m IS NOT NULL OR price_after_60m IS NOT NULL OR price_after_120m IS NOT NULL"
        ).fetchall()

    if not rows:
        return {"n": 0}

    stats: dict = {"n": len(rows)}
    for h in (15, 30, 60, 120):
        field = f"price_after_{h}m"
        prob_field = f"prob_{h}m"
        sample = [r for r in rows if r[field] is not None]
        if not sample:
            stats[f"{h}m"] = {"n": 0}
            continue
        moved_up = sum(1 for r in sample if r[field] > r["current_price"])
        preds = [r[prob_field] for r in sample if r[prob_field] is not None]
        stats[f"{h}m"] = {
            "n": len(sample),
            "moved_up_rate_pct": round(moved_up / len(sample) * 100, 1),
            "avg_predicted_probability_pct": round(sum(preds) / len(preds), 1) if preds else None,
        }

    uc_candidates = [r for r in rows if r["upper_circuit"] is not None]
    stats["uc_reached_rate_pct"] = (
        round(sum(1 for r in uc_candidates if r["uc_reached"]) / len(uc_candidates) * 100, 1)
        if uc_candidates else None
    )
    return stats
