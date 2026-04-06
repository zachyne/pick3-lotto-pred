from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from lotto_app.data import (
    DB_PATH,
    NORMALIZED_EXPORT_PATH,
    append_record,
    delete_record,
    list_records,
    load_all_records,
    update_record,
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
    paths = [DB_PATH]
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

    coverage_set = set(result["coverage_candidates"])
    coverage_ranked = [
        candidate for candidate in result["all_candidates"]
        if candidate.combo in coverage_set
    ]
    coverage_candidates = pd.DataFrame(
        {
            "rank": list(range(1, len(coverage_ranked) + 1)),
            "combo": [candidate.combo_label for candidate in coverage_ranked],
            "total_score": [candidate.total_score for candidate in coverage_ranked],
            "best_tier": [candidate.best_tier for candidate in coverage_ranked],
            "confidence": [candidate.confidence for candidate in coverage_ranked],
        }
    )
    coverage_digits = ", ".join(str(digit) for digit in result["coverage_digits"])
    with st.expander(
        f"All possible combinations within coverage ({len(result['coverage_candidates'])})",
        expanded=False,
    ):
        st.caption(f"Generated from the latest coverage digits: {coverage_digits}")
        st.dataframe(coverage_candidates, use_container_width=True, hide_index=True)

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
    st.caption("This writes to `data/lotto.db` and is immediately included in the next prediction run.")

    with st.form("add-result-form", clear_on_submit=True):
        draw_type = st.selectbox("Draw type", ["midday", "evening"], key="add_draw_type")
        draw_date = st.date_input("Draw date", value=date.today(), key="add_draw_date")
        winning_number = st.text_input("Winning number", placeholder="e.g. 0-6-1 or 061")
        draw_number_text = st.text_input("Draw number (optional)", placeholder="e.g. 2625")
        submitted = st.form_submit_button("Save result")

    existing_slot = records[
        (records["draw_type"] == draw_type)
        & (records["draw_date"].dt.date == draw_date)
    ].copy()
    if not existing_slot.empty:
        slot_row = existing_slot.sort_values(by=["draw_date"], ascending=False).iloc[0]
        draw_number_label = (
            str(int(slot_row["draw_number"])) if pd.notna(slot_row["draw_number"]) else "-"
        )
        st.warning(
            f"A {draw_type} record already exists for {draw_date.isoformat()} "
            f"(draw #{draw_number_label}, number {slot_row['number']}, source {slot_row['source']}). "
            "Update or delete it before creating a new one."
        )

    if submitted:
        try:
            draw_number = int(draw_number_text) if draw_number_text.strip() else None
            append_record(
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

    record_entries = list_records()
    if not record_entries.empty:
        recent_records = record_entries.copy()
        recent_records["draw_date"] = pd.to_datetime(recent_records["draw_date"])
        recent_records = recent_records.sort_values(
            by=["draw_date", "entry_id"],
            ascending=[False, False],
        ).reset_index(drop=True)
        recent_records["draw_date"] = recent_records["draw_date"].dt.date
        st.write("Recent records in the database")
        st.dataframe(
            recent_records[["draw_type", "draw_date", "draw_number", "number", "source"]].head(20),
            use_container_width=True,
            hide_index=True,
        )

    render_manage_records(record_entries)


def render_manage_records(records_df: pd.DataFrame) -> None:
    if records_df.empty:
        return

    records_df = records_df.copy()
    records_df["draw_date"] = pd.to_datetime(records_df["draw_date"])
    records_df = records_df.sort_values(
        by=["draw_date", "entry_id"],
        ascending=[False, False],
    ).reset_index(drop=True)

    st.divider()
    st.subheader("Edit or Delete Record")
    filter_col1, filter_col2 = st.columns([1, 2])
    with filter_col1:
        draw_type_filter = st.selectbox("Filter draw type", ["all", "midday", "evening"])
    with filter_col2:
        search_text = st.text_input(
            "Find record",
            placeholder="Search by date, number, draw number, or source",
        ).strip().lower()

    filtered_records = records_df.copy()
    if draw_type_filter != "all":
        filtered_records = filtered_records[filtered_records["draw_type"] == draw_type_filter]
    if search_text:
        search_series = (
            filtered_records["draw_date"].dt.strftime("%Y-%m-%d")
            + " "
            + filtered_records["draw_type"].astype(str)
            + " "
            + filtered_records["draw_number"].fillna("").astype(str)
            + " "
            + filtered_records["number"].astype(str)
            + " "
            + filtered_records["source"].astype(str)
        ).str.lower()
        filtered_records = filtered_records[search_series.str.contains(search_text, regex=False)]

    if filtered_records.empty:
        st.info("No records match the current filters.")
        return

    preview = filtered_records.head(25).copy()
    preview["draw_date"] = preview["draw_date"].dt.date

    header_cols = st.columns([1.1, 1.1, 1.0, 1.0, 1.0, 0.8])
    header_cols[0].markdown("**Date**")
    header_cols[1].markdown("**Draw Type**")
    header_cols[2].markdown("**Draw #**")
    header_cols[3].markdown("**Number**")
    header_cols[4].markdown("**Source**")
    header_cols[5].markdown("**Actions**")

    selected_entry_id = st.session_state.get("selected_record_id")
    for row in preview.itertuples(index=False):
        cols = st.columns([1.1, 1.1, 1.0, 1.0, 1.0, 0.8], vertical_alignment="center")
        cols[0].write(pd.Timestamp(row.draw_date).date().isoformat())
        cols[1].write(str(row.draw_type).title())
        cols[2].write(str(int(row.draw_number)) if str(row.draw_number).strip() else "-")
        cols[3].write(str(row.number))
        cols[4].write(str(row.source))

        action_cols = cols[5].columns(2)
        if action_cols[0].button(
            "✎",
            key=f"edit_record_{row.entry_id}",
            use_container_width=True,
        ):
            st.session_state["selected_record_id"] = int(row.entry_id)
            st.session_state["edit_record_id"] = int(row.entry_id)
            st.session_state.pop("delete_record_id", None)
            selected_entry_id = int(row.entry_id)
        if action_cols[1].button(
            "🗑",
            key=f"delete_record_{row.entry_id}",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state["selected_record_id"] = int(row.entry_id)
            st.session_state["delete_record_id"] = int(row.entry_id)
            st.session_state.pop("edit_record_id", None)
            selected_entry_id = int(row.entry_id)

    if selected_entry_id is None:
        selected_entry_id = int(preview.iloc[0]["entry_id"])
        st.session_state["selected_record_id"] = selected_entry_id

    selected_row = filtered_records.loc[filtered_records["entry_id"] == selected_entry_id]
    if selected_row.empty:
        selected_entry_id = int(preview.iloc[0]["entry_id"])
        st.session_state["selected_record_id"] = selected_entry_id
        selected_row = filtered_records.loc[filtered_records["entry_id"] == selected_entry_id]
    selected_row = selected_row.iloc[0]
    edit_record_id = st.session_state.get("edit_record_id")
    if edit_record_id == selected_entry_id:
        st.caption(
            "Editing: "
            f"{pd.Timestamp(selected_row['draw_date']).date().isoformat()} | "
            f"{selected_row['draw_type']} | draw #{int(selected_row['draw_number']) if str(selected_row['draw_number']).strip() else '-'}"
        )
        with st.form("edit-result-form"):
            edit_winning_number = st.text_input(
                "Winning number",
                value=str(selected_row["number"]),
                key=f"edit_winning_number_{selected_entry_id}",
            )
            save_col, cancel_col = st.columns([1, 1])
            save_changes = save_col.form_submit_button("Save number")
            cancel_edit = cancel_col.form_submit_button("Cancel")

        if cancel_edit:
            st.session_state.pop("edit_record_id", None)
            st.rerun()

        if save_changes:
            try:
                parsed_draw_number = (
                    int(selected_row["draw_number"])
                    if str(selected_row["draw_number"]).strip()
                    else None
                )
                update_record(
                    entry_id=selected_entry_id,
                    draw_type=str(selected_row["draw_type"]),
                    draw_date=pd.Timestamp(selected_row["draw_date"]).date(),
                    winning_number=edit_winning_number,
                    draw_number=parsed_draw_number,
                )
                st.session_state.pop("edit_record_id", None)
                clear_records_cache()
                st.success("Record updated.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    pending_delete_id = st.session_state.get("delete_record_id")
    if pending_delete_id == selected_entry_id:
        st.warning(
            "Delete this record permanently? "
            f"{pd.Timestamp(selected_row['draw_date']).date().isoformat()} | "
            f"{selected_row['draw_type']} | {selected_row['number']}"
        )
        confirm_col, cancel_col = st.columns([1, 1])
        if confirm_col.button("Yes, delete", type="secondary", use_container_width=True):
            try:
                delete_record(selected_entry_id)
                st.session_state.pop("delete_record_id", None)
                st.session_state.pop("selected_record_id", None)
                clear_records_cache()
                st.success("Record deleted.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        if cancel_col.button("Cancel", key="cancel_delete_record", use_container_width=True):
            st.session_state.pop("delete_record_id", None)
            st.rerun()


def render_history(records: pd.DataFrame, draw_type: str) -> None:
    st.subheader("Dataset View")
    filtered = records[records["draw_type"] == draw_type].copy()
    filtered["draw_date"] = filtered["draw_date"].dt.date
    st.dataframe(filtered.head(50), use_container_width=True, hide_index=True)
    st.caption("The app reads from `data/lotto.db` and exports the current snapshot to `data/normalized_results.csv`.")


if __name__ == "__main__":
    main()
