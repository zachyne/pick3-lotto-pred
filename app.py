from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from lotto_app.data import (
    CUSTOM_RESULTS_PATH,
    NORMALIZED_EXPORT_PATH,
    TEMPLATES_DIR,
    append_custom_record,
    delete_custom_record,
    list_custom_records,
    load_all_records,
    update_custom_record,
)
from lotto_app.model import grid_table, predict_next


st.set_page_config(page_title="ANY 3 Predictor", page_icon="🔢", layout="wide")


@st.cache_data(show_spinner=False)
def get_records(cache_key: tuple[tuple[str, int, int], ...]) -> pd.DataFrame:
    del cache_key
    return load_all_records()


def clear_records_cache() -> None:
    get_records.clear()


def get_records_cache_key() -> tuple[tuple[str, int, int], ...]:
    paths = sorted(TEMPLATES_DIR.glob("*.xlsx")) + [CUSTOM_RESULTS_PATH]
    cache_key = []
    for path in paths:
        if path.exists():
            stat = path.stat()
            cache_key.append((str(path), stat.st_mtime_ns, stat.st_size))
        else:
            cache_key.append((str(path), 0, 0))
    return tuple(cache_key)


def main() -> None:
    st.title("ANY 3 Predictor")
    st.caption(
        "Rule-based prediction model using the repo's grid/zone logic, with the most recent "
        "winner as the primary signal, the previous winner as a secondary signal, and recent "
        "history only as a tiebreaker."
    )

    records = get_records(get_records_cache_key())
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

    manual_entries = list_custom_records()
    if not manual_entries.empty:
        recent_manual = manual_entries.copy()
        recent_manual["draw_date"] = pd.to_datetime(recent_manual["draw_date"])
        recent_manual = recent_manual.sort_values(
            by=["draw_date", "entry_id"],
            ascending=[False, False],
        ).reset_index(drop=True)
        recent_manual["draw_date"] = recent_manual["draw_date"].dt.date
        st.write("Recently added manual entries")
        st.dataframe(
            recent_manual[["draw_type", "draw_date", "draw_number", "number", "source"]].head(20),
            use_container_width=True,
            hide_index=True,
        )

    render_manage_manual_entries(manual_entries)


def render_manage_manual_entries(manual_entries: pd.DataFrame) -> None:
    if manual_entries.empty:
        return

    manual_entries = manual_entries.copy()
    manual_entries["draw_date"] = pd.to_datetime(manual_entries["draw_date"])
    manual_entries = manual_entries.sort_values(
        by=["draw_date", "entry_id"],
        ascending=[False, False],
    ).reset_index(drop=True)

    st.divider()
    st.subheader("Edit or Delete Manual Entry")

    date_options = []
    date_to_entry_id = {}
    for row in manual_entries.itertuples(index=False):
        draw_date = pd.Timestamp(row.draw_date).date()
        label = str(draw_date)
        if label in date_to_entry_id:
            label = f"{draw_date} ({row.draw_type}, #{row.entry_id})"
        date_options.append(label)
        date_to_entry_id[label] = int(row.entry_id)

    selected_label = st.selectbox("Select entry date", date_options)
    selected_entry_id = date_to_entry_id[selected_label]
    selected_row = manual_entries.loc[manual_entries["entry_id"] == selected_entry_id].iloc[0]
    selected_draw_number = str(int(selected_row["draw_number"])) if str(selected_row["draw_number"]).strip() else ""

    with st.form("edit-result-form"):
        edit_draw_type = st.selectbox(
            "Draw type",
            ["midday", "evening"],
            index=0 if selected_row["draw_type"] == "midday" else 1,
            key="edit_draw_type",
        )
        edit_draw_date = st.date_input(
            "Draw date",
            value=pd.Timestamp(selected_row["draw_date"]).date(),
            key="edit_draw_date",
        )
        edit_winning_number = st.text_input(
            "Winning number",
            value=str(selected_row["number"]),
            key="edit_winning_number",
        )
        edit_draw_number = st.text_input(
            "Draw number (optional)",
            value=selected_draw_number,
            key="edit_draw_number",
        )
        save_changes = st.form_submit_button("Save changes")

    if save_changes:
        try:
            parsed_draw_number = int(edit_draw_number) if edit_draw_number.strip() else None
            update_custom_record(
                entry_id=selected_entry_id,
                draw_type=edit_draw_type,
                draw_date=edit_draw_date,
                winning_number=edit_winning_number,
                draw_number=parsed_draw_number,
            )
            clear_records_cache()
            st.success("Manual entry updated.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if st.button("Delete selected entry", type="secondary"):
        try:
            delete_custom_record(selected_entry_id)
            clear_records_cache()
            st.success("Manual entry deleted.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def render_history(records: pd.DataFrame, draw_type: str) -> None:
    st.subheader("Dataset View")
    filtered = records[records["draw_type"] == draw_type].copy()
    filtered["draw_date"] = filtered["draw_date"].dt.date
    st.dataframe(filtered.head(50), use_container_width=True, hide_index=True)
    st.caption("The app merges both Excel templates with your manual entries, then exports a normalized CSV to `data/normalized_results.csv`.")


if __name__ == "__main__":
    main()
