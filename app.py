"""Streamlit dashboard.

The pre-market scanner tabs (Market Overview onward) are read-only: they
display whatever `scanner.py scan` last wrote and never fetch on page
load. The AI Momentum Scanner tab is the one exception, by design -- its
"Run Market Research" / "Refresh Data" buttons are explicit user actions
(app-info.md's primary objective), not something that fires on every page
load.

Run:
    streamlit run app.py
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

import config
import momentum
import storage

st.set_page_config(page_title="India Pre-Market Scanner", layout="wide")

# Idempotent, additive-only (CREATE TABLE IF NOT EXISTS) -- safe to run on
# every page load. Needed here, not just in scanner.py's CLI entrypoint,
# so the dashboard works even when it's the first thing run against a
# pre-existing DB (e.g. one created before the momentum_signals table
# existed).
storage.init_db()

DISCLAIMER = (
    "Model-generated, probability-based signals -- not investment advice and not a "
    "guarantee of any return. Market predictions are probabilistic and can be wrong. "
    "Past performance does not guarantee future results. This tool has not been "
    "reviewed for SEBI Research Analyst / Investment Adviser compliance; do not "
    "distribute its output to other users without resolving that first."
)


def load_json(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text())


st.title("🇮🇳 India Pre-Market Scanner")
st.warning(DISCLAIMER, icon="⚠️")

scan = load_json("./data/latest_scan.json")
preopen = load_json("./data/latest_preopen.json")

tabs = st.tabs([
    "🚀 AI Momentum Scanner", "Market Overview", "Sector Heatmap", "AI Top Picks",
    "Pre-Open Validation", "News Scanner", "Backtest / Accuracy",
])

# ---------------------------------------------------------------------------
# AI Momentum & Upper-Circuit Scanner (app-info.md)
# ---------------------------------------------------------------------------
with tabs[0]:
    st.subheader("AI Short-Term Momentum & Upper-Circuit Scanner")
    st.caption(
        "Scans the broader NSE universe (Nifty Total Market + Nifty Microcap 250) for stocks "
        "showing signs of a short-term (1-2 hour) upward move, with a distance/probability read "
        "toward each stock's exchange-defined upper circuit where a static one applies. Most "
        "large/F&O-eligible names (most of Nifty-50) trade on a dynamic range instead of a static "
        "circuit -- those show 'N/A' rather than a fabricated circuit price."
    )
    st.info(
        "This is an AI-generated market research signal, not a guarantee of future price movement "
        "or investment advice. Horizon probabilities below are a transparent heuristic, not yet "
        "calibrated against historical outcomes -- see the calibration numbers at the bottom of the "
        "Backtest / Accuracy tab once enough signals have been backfilled.",
        icon="ℹ️",
    )

    if "momentum_result" not in st.session_state:
        st.session_state["momentum_result"] = load_json("./data/latest_momentum.json")

    bcol1, bcol2, bcol3 = st.columns([1, 1, 2])
    run_clicked = bcol1.button("▶️ Run Market Research", type="primary")
    refresh_clicked = bcol2.button("🔄 Refresh Data")
    bcol3.caption(
        "**Auto Monitor:** not available yet -- needs a live broker feed "
        "(`BROKER_API_KEY` is unset). Use Run Market Research / Refresh Data manually for now."
    )

    if run_clicked or refresh_clicked:
        with st.spinner(
            "Scanning the broad NSE universe -- one batched yfinance call for the full universe, "
            "then a live NSE quote + intraday read per shortlisted name. Usually 30-90s..."
        ):
            st.session_state["momentum_result"] = momentum.run_market_research()

    mres = st.session_state.get("momentum_result")
    if not mres:
        st.info("No research run yet this session. Click **Run Market Research** to start.")
    elif mres.get("error"):
        st.error(f"Research run failed: {mres['error']}")
    else:
        st.caption(
            f"Last research: {mres['generated_at']} · universe: {mres['universe_size']} names "
            f"({mres['stage1_scored']} scored in stage 1, {mres['stage2_shortlist_size']} shortlisted "
            f"for a live quote + intraday read"
            + (f", {mres['stage2_dropped_by_cap']} dropped by the universe cap" if mres.get("stage2_dropped_by_cap") else "")
            + f") · {len(mres.get('nse_quote_failures', []))} live-quote lookups failed this run"
        )
        if mres.get("nse_quote_failures"):
            fails = mres["nse_quote_failures"]
            st.caption(f"⚠️ No live quote for: {', '.join(fails[:15])}" + ("..." if len(fails) > 15 else ""))

        regime_color = {"STRONG BULLISH": "green", "BULLISH": "green", "NEUTRAL": "orange",
                         "BEARISH": "red", "HIGH RISK": "red"}.get(mres["market_regime"], "gray")
        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(f"**Market regime**  \n:{regime_color}[{mres['market_regime']}]")
        m2.metric("Market breadth", f"{mres['market_breadth_pct']}%" if mres.get("market_breadth_pct") is not None else "—")
        m3.metric("Strongest sector", mres.get("strongest_sector") or "—")
        m4.metric("High-momentum found", mres["high_momentum_found"])

        candidates = mres.get("candidates", [])
        if not candidates:
            st.info("No candidate cleared the momentum threshold (score >= 60, risk != EXTREME) this run.")
        else:
            st.markdown("### Top 5 Short-Term Momentum Candidates")
            for i, cand in enumerate(candidates[:5], start=1):
                with st.container(border=True):
                    st.markdown(f"**Rank #{i} — {cand['symbol']} · {cand['name']}**")
                    st.caption(cand["sector"])
                    r1, r2, r3, r4, r5 = st.columns(5)
                    r1.metric("Price", f"₹{cand['current_price']}")
                    r2.metric("Upper Circuit", f"₹{cand['upper_circuit']}" if cand.get("upper_circuit") else "N/A")
                    r3.metric("UC Distance", f"{cand['uc_distance_pct']}%" if cand.get("uc_distance_pct") is not None else "—")
                    r4.metric("Score", f"{cand['opportunity_score']}/100", cand["momentum_grade"])
                    r5.metric(
                        "UC Probability",
                        f"{cand['uc_probability_pct']}%" if cand.get("uc_probability_pct") is not None else "N/A",
                        cand["uc_confidence"],
                    )
                    hp = cand.get("horizon_probabilities", {})
                    st.caption("Horizon probability (model estimate): " + " · ".join(f"{k}: {v}%" for k, v in hp.items()))
                    st.caption(f"Risk: {cand['risk']} · Catalyst: {', '.join(cand['news_tags']) or '—'}")
                    if cand.get("uc_distance_pct") is not None and cand["uc_distance_pct"] < 2:
                        st.warning("⚠️ APPROACHING UPPER CIRCUIT (< 2% away)")

            st.markdown("### Ranked Research List")
            with st.expander("Filters", expanded=False):
                f1, f2 = st.columns(2)
                min_score = f1.slider("Minimum score", 0, 100, config.MOMENTUM_MIN_SCORE)
                max_uc_dist = f2.slider("Max UC distance % (ignored for no-static-band names)", 0.0, 20.0, 20.0)
                sectors = sorted({c["sector"] for c in candidates})
                sel_sectors = st.multiselect("Sector", sectors, default=sectors)
                risk_filter = st.multiselect("Risk", ["LOW", "MEDIUM", "HIGH"], default=["LOW", "MEDIUM", "HIGH"])

            filtered = [
                c for c in candidates
                if c["opportunity_score"] >= min_score
                and c["sector"] in sel_sectors
                and c["risk"] in risk_filter
                and (c.get("uc_distance_pct") is None or c["uc_distance_pct"] <= max_uc_dist)
            ]

            table_df = pd.DataFrame([
                {
                    "Rank": i + 1, "Symbol": c["symbol"], "Company": c["name"], "Price": c["current_price"],
                    "UC Price": c.get("upper_circuit") or "N/A",
                    "UC Dist %": c.get("uc_distance_pct") if c.get("uc_distance_pct") is not None else "N/A",
                    "Score": c["opportunity_score"], "Grade": c["momentum_grade"],
                    "UC Prob %": c.get("uc_probability_pct") if c.get("uc_probability_pct") is not None else "N/A",
                    "Confidence": c["uc_confidence"], "Risk": c["risk"],
                }
                for i, c in enumerate(filtered)
            ])
            st.dataframe(table_df, width="stretch", hide_index=True)

            st.markdown("### Stock Detail")
            for cand in filtered:
                with st.expander(f"{cand['symbol']} — {cand['name']} ({cand['momentum_grade']})"):
                    st.markdown("**Price**")
                    p1, p2, p3 = st.columns(3)
                    p1.metric("Current", f"₹{cand['current_price']}")
                    p2.metric("Upper Circuit", f"₹{cand['upper_circuit']}" if cand.get("upper_circuit") else "N/A")
                    p3.metric("Lower Circuit", f"₹{cand['lower_circuit']}" if cand.get("lower_circuit") else "N/A")

                    st.markdown("**Prediction** _(model estimate, not yet backtest-calibrated)_")
                    hp = cand.get("horizon_probabilities", {})
                    st.table(pd.DataFrame([{"Horizon": k, "Probability": f"{v}%"} for k, v in hp.items()]))
                    if cand.get("expected_move_pct") is not None:
                        st.caption(f"Expected move (ATR-based heuristic): {cand['expected_move_pct']}%")

                    st.markdown("**AI Score Breakdown**")
                    st.json(cand["sub_scores"])
                    if cand["unavailable_components"]:
                        st.caption(f"⚠️ Computed without: {', '.join(cand['unavailable_components'])} (weights renormalized)")

                    st.markdown("**Why This Stock?**")
                    for r in cand["reasons"]:
                        st.write(f"- {r}")

                    st.markdown("**What Could Invalidate the Signal**")
                    for iv in cand["invalidation_watch"]:
                        st.write(f"- {iv}")

                    if cand["manipulation_flags"]:
                        st.error("Risk flags: " + "; ".join(cand["manipulation_flags"]))
                    if cand["news_headlines"]:
                        st.caption("News: " + " · ".join(cand["news_headlines"][:3]))
                    st.caption(f"Data as of: {cand['data_as_of']} · Risk: {cand['risk']}")

if scan is None:
    with tabs[1]:
        st.error("No pre-market scan found yet. Run `python scanner.py scan` first.")
    st.stop()

if scan.get("error"):
    with tabs[1]:
        st.error(f"Last scan failed: {scan['error']}")
    st.stop()

with tabs[1]:
    st.caption(f"Generated at {scan['generated_at']} · universe: {scan['universe_size']} names "
               f"({len(scan.get('skipped_symbols', []))} skipped for insufficient history)")
    cols = st.columns(len(scan["index_snapshot"]) or 1)
    for col, (label, vals) in zip(cols, scan["index_snapshot"].items()):
        col.metric(label, vals["price"], f"{vals['change_pct']:+.2f}%")

    regime = scan["market_regime"]
    regime_color = {"STRONG BULLISH": "green", "BULLISH": "green", "NEUTRAL": "orange",
                     "BEARISH": "red", "HIGH RISK": "red"}.get(regime, "gray")
    st.markdown(f"**Market regime:** :{regime_color}[{regime}]")

    fii_dii = scan.get("fii_dii", {})
    if fii_dii.get("as_of"):
        c1, c2 = st.columns(2)
        c1.metric(f"FII net (cash, {fii_dii['as_of']})", f"₹{fii_dii['fii_net_cr']:.0f} cr")
        c2.metric(f"DII net (cash, {fii_dii['as_of']})", f"₹{fii_dii['dii_net_cr']:.0f} cr")
    else:
        st.info("FII/DII data unavailable this run (NSE endpoint unreachable).")

    if scan.get("no_trade_reason"):
        st.error(f"🚫 NO TRADE: {scan['no_trade_reason']}")

with tabs[2]:
    sector_df = pd.DataFrame(
        [{"Sector": s, "Momentum score (0-10)": v} for s, v in scan.get("sector_scores", {}).items()]
    ).sort_values("Momentum score (0-10)", ascending=False)
    st.dataframe(sector_df, width="stretch", hide_index=True)
    st.caption("Momentum score = today's percentile rank of each sector's average % change, "
               "within this scanned universe only -- not an official NSE sector index.")

with tabs[3]:
    candidates = scan.get("candidates", [])
    if not candidates:
        st.info("No candidates cleared the scoring threshold this run.")
    for cand in candidates:
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.subheader(f"{cand['symbol']} — {cand['name']}")
            c1.caption(cand["sector"])
            c2.metric("Score", f"{cand['composite_score']}/100", cand["score_label"])
            c3.metric("Confidence", f"{cand['confidence_pct']}%", cand["confidence_label"])

            g1, g2, g3, g4, g5 = st.columns(5)
            g1.metric("Entry zone", cand.get("entry_zone", "—"))
            g2.metric("Target 1", cand.get("target_1", "—"))
            g3.metric("Target 2", cand.get("target_2", "—"))
            g4.metric("Stop loss", cand.get("stop_loss", "—"))
            g5.metric("Risk", cand["risk"])

            if cand["unavailable_components"]:
                st.caption(f"⚠️ Computed without: {', '.join(cand['unavailable_components'])} "
                           "(weights renormalized over available data)")
            if cand["news_headlines"]:
                st.caption("News: " + " · ".join(cand["news_headlines"][:3]))

with tabs[4]:
    if preopen is None:
        st.info("No pre-open validation run yet. Run `python scanner.py preopen` between 9:00-9:15 IST.")
    else:
        st.caption(f"Generated at {preopen['generated_at']}")
        rows = preopen.get("validated_candidates", [])
        if rows:
            df = pd.DataFrame(rows)[["symbol", "composite_score", "preopen_status", "preopen_change_pct", "preopen_reason"]]
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            st.info("No candidates to validate.")

with tabs[5]:
    st.caption(f"{scan.get('headline_count', 0)} headlines scanned this run across configured RSS feeds.")
    for cand in scan.get("candidates", []):
        if cand.get("news_tags"):
            st.write(f"**{cand['symbol']}**: {', '.join(cand['news_tags'])}")
            for h in cand.get("news_headlines", []):
                st.caption(f"  · {h}")

with tabs[6]:
    st.markdown("#### Pre-market scanner accuracy (next-session targets)")
    stats = storage.compute_accuracy_stats()
    if stats["n"] == 0:
        st.info("No backtested predictions yet -- run `scanner.py backfill` the day after a scan.")
    else:
        st.json(stats)
    recent = storage.get_recent(limit=100)
    if recent:
        st.dataframe(pd.DataFrame([dict(r) for r in recent]), width="stretch", hide_index=True)

    st.markdown("---")
    st.markdown("#### AI Momentum Scanner accuracy (15/30/60/120-min horizons)")
    st.caption(
        "spec section 23: this compares each horizon's average *predicted* probability against the "
        "*realized* rate of an upward move. Small-N and not a real calibration curve until many "
        "signals have been backfilled -- treat n as the headline number here, not the percentages."
    )
    if st.button("Check for due horizon outcomes now"):
        with st.spinner("Fetching live quotes for open signals with a due horizon..."):
            result = momentum.run_momentum_backfill()
        st.success(f"Checked {result['checked']} open signal(s), {result.get('due', 0)} horizon(s) due, "
                   f"{result.get('filled', 0)} filled.")
    mstats = storage.compute_momentum_accuracy_stats()
    if mstats["n"] == 0:
        st.info("No momentum signals backfilled yet.")
    else:
        st.json(mstats)
