from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from lotto_app.data import (
    CUSTOM_RESULTS_PATH,
    NORMALIZED_EXPORT_PATH,
    append_custom_record,
    load_all_records,
)
from lotto_app.model import grid_table, predict_next


st.set_page_config(page_title="ANY 3 Predictor", page_icon="🔢", layout="wide")


@st.cache_data(show_spinner=False)
def get_records() -> pd.DataFrame:
    return load_all_records()


def clear_records_cache() -> None:
    get_records.clear()


def main() -> None:
    st.title("ANY 3 Predictor")
    st.caption(
        "Rule-based prediction model using the repo's grid/zone logic, with the most recent "
        "winner as the primary signal, the previous winner as a secondary signal, and recent "
        "history only as a tiebreaker."
    )

    records = get_records()
    if records.empty:
        st.error("No draw records were loaded.")
        return

    with st.sidebar:
        st.header("Prediction Setup")
        draw_type = st.selectbox("Draw type", ["midday", "evening"], index=0)
        winners_to_use = st.slider("Recent winners to use", min_value=2, max_value=5, value=3)
        top_n = st.slider("How many candidates to show", min_value=5, max_value=30, value=18)
        history_depth = st.slider("Recent history tiebreaker depth", min_value=10, max_value=30, value=20)
        st.write(f"Normalized dataset: `{NORMALIZED_EXPORT_PATH}`")
        st.write(f"Manual entries file: `{CUSTOM_RESULTS_PATH}`")

    prediction_tab, add_tab, history_tab = st.tabs(["Predict", "Add Result", "History"])

    with prediction_tab:
        render_prediction(records, draw_type, history_depth, top_n, winners_to_use)

    with add_tab:
        render_add_result(records)

    with history_tab:
        render_history(records, draw_type)


def render_prediction(
    records: pd.DataFrame,
    draw_type: str,
    history_depth: int,
    top_n: int,
    winners_to_use: int,
) -> None:
    st.subheader(f"Next {draw_type.title()} Prediction")
    filtered = records[records["draw_type"] == draw_type].copy()
    if len(filtered) < 2:
        st.warning(f"Need at least two {draw_type} results in the dataset.")
        return

    result = predict_next(
        records,
        draw_type=draw_type,
        history_depth=history_depth,
        top_n=top_n,
        winners_to_use=winners_to_use,
    )

    latest_inputs = result["latest_inputs"][["draw_date", "draw_number", "number", "source"]].copy()
    latest_inputs["draw_date"] = latest_inputs["draw_date"].dt.date
    st.write("Recent winners used by the model")
    st.dataframe(latest_inputs, use_container_width=True, hide_index=True)

    if result["dataset_freshness_days"] > 3:
        st.warning(
            f"Dataset freshness warning: latest {draw_type} result is {result['dataset_freshness_days']} day(s) old. "
            "Predictions are less reliable when recent draws are missing."
        )

    candidates = pd.DataFrame(
        {
            "combo": [candidate.combo_label for candidate in result["top_candidates"]],
            "total_score": [candidate.total_score for candidate in result["top_candidates"]],
            "core_score": [candidate.core_score for candidate in result["top_candidates"]],
            "history_score": [candidate.history_score for candidate in result["top_candidates"]],
            "best_tier": [candidate.best_tier for candidate in result["top_candidates"]],
            "confidence": [candidate.confidence for candidate in result["top_candidates"]],
            "source_signal": [", ".join(candidate.sources) for candidate in result["top_candidates"]],
            "why": ["; ".join(candidate.support[:3]) for candidate in result["top_candidates"]],
        }
    )

    st.write("Top candidate bets")
    st.dataframe(candidates, use_container_width=True, hide_index=True)

    hit_rates = result["hit_rates"]
    if hit_rates and hit_rates["sample_size"] > 0:
        st.write("Recent backtest snapshot")
        metric_1, metric_2, metric_3 = st.columns(3)
        metric_1.metric("Backtest sample", hit_rates["sample_size"])
        metric_2.metric(f"Top {top_n} hit rate", f"{hit_rates['top_n_hit_rate']}%")
        strongest_tier = max(hit_rates["tier_hit_rates"], key=hit_rates["tier_hit_rates"].get)
        metric_3.metric("Best recent tier", f"{strongest_tier} ({hit_rates['tier_hit_rates'][strongest_tier]}%)")

        st.dataframe(
            pd.DataFrame(
                {
                    "tier": list(hit_rates["tier_hit_rates"].keys()),
                    "hit_rate_percent": list(hit_rates["tier_hit_rates"].values()),
                    "direct_hits": [hit_rates["direct_tier_hits"][tier] for tier in hit_rates["tier_hit_rates"]],
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    for analysis in result["analyses"]:
        with st.expander(f"{analysis.label.title()} winner analysis: {'-'.join(map(str, analysis.last_winner))}"):
            left, right = st.columns(2)
            with left:
                st.markdown(
                    "\n".join(
                        [
                            f"Draw type: `{analysis.draw_type}`",
                            f"Grid equivalent: `{'-'.join(map(str, analysis.grid_equivalent))}`",
                            f"Is double: `{analysis.is_double}`",
                            f"Anchor row: `{analysis.anchor_row}`",
                            f"Companion row: `{analysis.companion_row if analysis.companion_row else 'none'}`",
                            f"Cluster rows: `{list(analysis.cluster_rows)}`",
                            f"Zone ±1 rows: `{list(analysis.zone_plus_1_rows)}`",
                            f"Zone ±2 rows: `{list(analysis.zone_plus_2_rows)}`",
                        ]
                    )
                )
            with right:
                st.markdown(
                    "\n".join(
                        [
                            f"Cluster digits: `{list(analysis.cluster_digits)}`",
                            f"Zone ±1 digits: `{list(analysis.zone_digits_plus_1)}`",
                            f"Zone ±2 digits: `{list(analysis.zone_digits_plus_2)}`",
                            f"Combined zone: `{list(analysis.combined_zone_digits)}`",
                            f"Pair-extended digits: `{list(analysis.pair_extended_digits)}`",
                            f"Double pairs in zone: `{list(analysis.double_pairs_in_zone)}`",
                        ]
                    )
                )

    with st.expander("Reference grid"):
        st.dataframe(pd.DataFrame(grid_table()), use_container_width=True, hide_index=True)


def render_add_result(records: pd.DataFrame) -> None:
    st.subheader("Add a Winning Number")
    st.caption("This writes to `data/custom_results.csv` and is immediately included in the next prediction run.")

    with st.form("add-result-form", clear_on_submit=True):
        draw_type = st.selectbox("Draw type", ["midday", "evening"], key="add_draw_type")
        draw_date = st.date_input("Draw date", value=date.today())
        winning_number = st.text_input("Winning number", placeholder="e.g. 0-6-1 or 061")
        draw_number_text = st.text_input("Draw number (optional)", placeholder="e.g. 2625")
        submitted = st.form_submit_button("Save result")

    if submitted:
        try:
            draw_number = int(draw_number_text) if draw_number_text.strip() else None
            append_custom_record(
                draw_type=draw_type,
                draw_date=draw_date,
                winning_number=winning_number,
                draw_number=draw_number,
            )
            clear_records_cache()
            st.success("Result saved. Refreshing predictions with the updated dataset.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    recent_manual = records[records["source"] == "manual"].copy()
    if not recent_manual.empty:
        recent_manual["draw_date"] = recent_manual["draw_date"].dt.date
        st.write("Recently added manual entries")
        st.dataframe(recent_manual.head(20), use_container_width=True, hide_index=True)


def render_history(records: pd.DataFrame, draw_type: str) -> None:
    st.subheader("Dataset View")
    filtered = records[records["draw_type"] == draw_type].copy()
    filtered["draw_date"] = filtered["draw_date"].dt.date
    st.dataframe(filtered.head(50), use_container_width=True, hide_index=True)
    st.caption("The app merges both Excel templates with your manual entries, then exports a normalized CSV to `data/normalized_results.csv`.")


if __name__ == "__main__":
    main()
