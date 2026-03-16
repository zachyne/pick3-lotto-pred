from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

import pandas as pd


PAIR_MAP = {0: 5, 1: 6, 2: 7, 3: 8, 4: 9, 5: 0, 6: 1, 7: 2, 8: 3, 9: 4}
GRID_ROWS = {
    row: ((row + 6) % 10, (row + 2) % 10, (row - 1) % 10)
    for row in range(1, 11)
}
TIER_PRIORITY = {"tier1": 1, "tier2": 2, "tier3": 3, "tier4": 4}
BASE_TIER_SCORES = {
    "tier1": 100.0,
    "tier2": 68.0,
    "tier3": 36.0,
    "tier4": 18.0,
}
RECENCY_WEIGHTS = [1.0, 0.62, 0.34, 0.18, 0.1]


@dataclass(frozen=True)
class WinnerAnalysis:
    label: str
    draw_type: str
    last_winner: tuple[int, int, int]
    grid_equivalent: tuple[int, int, int]
    is_double: bool
    anchor_row: int
    companion_row: int | None
    cluster_rows: tuple[int, ...]
    zone_plus_1_rows: tuple[int, int]
    zone_plus_2_rows: tuple[int, int]
    cluster_row_combos: tuple[tuple[int, int, int], ...]
    zone_row_combos_plus_1: tuple[tuple[int, int, int], ...]
    zone_row_combos_plus_2: tuple[tuple[int, int, int], ...]
    coverage_rows: tuple[int, ...]
    cluster_digits: tuple[int, ...]
    zone_digits_plus_1: tuple[int, ...]
    zone_digits_plus_2: tuple[int, ...]
    coverage_digits: tuple[int, ...]
    combined_zone_digits: tuple[int, ...]
    pair_extended_digits: tuple[int, ...]
    double_pairs_in_zone: tuple[int, ...]


@dataclass(frozen=True)
class PredictionCandidate:
    combo: tuple[int, int, int]
    total_score: float
    core_score: float
    history_score: float
    confidence: str
    support: tuple[str, ...]
    sources: tuple[str, ...]
    best_tier: str

    @property
    def combo_label(self) -> str:
        return "-".join(str(digit) for digit in self.combo)


def pair_of(digit: int) -> int:
    return PAIR_MAP[digit]


def canonical_combo(digits: Iterable[int]) -> tuple[int, int, int]:
    combo = tuple(sorted(int(digit) for digit in digits))
    if len(combo) != 3:
        raise ValueError("A combo must contain exactly three digits.")
    return combo


def derive_grid_equivalent(digits: tuple[int, int, int]) -> tuple[int, int, int]:
    counts: dict[int, int] = {}
    for digit in digits:
        counts[digit] = counts.get(digit, 0) + 1

    repeated = next((digit for digit, count in counts.items() if count > 1), None)
    if repeated is None:
        return digits

    replacement = pair_of(repeated)
    updated = list(digits)
    replace_index = max(index for index, digit in enumerate(updated) if digit == repeated)
    updated[replace_index] = replacement
    return tuple(updated)


def analyze_winner(digits: tuple[int, int, int], draw_type: str, label: str) -> WinnerAnalysis:
    grid_equivalent = derive_grid_equivalent(digits)
    match_digits = set(digits) | set(grid_equivalent)
    anchor_row, companion_row = _select_best_cluster(match_digits)
    cluster_rows = _ordered_cluster_rows(anchor_row, companion_row)
    zone_plus_1_rows = (_prev_row(cluster_rows[0]), _next_row(cluster_rows[-1]))
    zone_plus_2_rows = (_prev_row(zone_plus_1_rows[0]), _next_row(zone_plus_1_rows[1]))

    cluster_row_combos = tuple(GRID_ROWS[row] for row in cluster_rows)
    zone_row_combos_plus_1 = tuple(GRID_ROWS[row] for row in zone_plus_1_rows)
    zone_row_combos_plus_2 = tuple(GRID_ROWS[row] for row in zone_plus_2_rows)
    coverage_rows = tuple(dict.fromkeys(cluster_rows + zone_plus_1_rows))

    cluster_digits = tuple(sorted({digit for combo in cluster_row_combos for digit in combo}))
    zone_digits_plus_1 = tuple(sorted({digit for combo in zone_row_combos_plus_1 for digit in combo}))
    zone_digits_plus_2 = tuple(sorted({digit for combo in zone_row_combos_plus_2 for digit in combo}))
    coverage_digits = tuple(sorted({digit for row in coverage_rows for digit in GRID_ROWS[row]}))

    combined_zone_digits = tuple(
        sorted(set(cluster_digits) | set(zone_digits_plus_1) | set(zone_digits_plus_2))
    )
    pair_extended_digits = tuple(
        sorted({pair_of(digit) for digit in combined_zone_digits if pair_of(digit) not in combined_zone_digits})
    )
    double_pairs_in_zone = tuple(
        sorted(
            digit for digit in combined_zone_digits
            if pair_of(digit) in combined_zone_digits and digit <= pair_of(digit)
        )
    )

    return WinnerAnalysis(
        label=label,
        draw_type=draw_type,
        last_winner=digits,
        grid_equivalent=grid_equivalent,
        is_double=len(set(digits)) < 3,
        anchor_row=anchor_row,
        companion_row=companion_row,
        cluster_rows=cluster_rows,
        zone_plus_1_rows=zone_plus_1_rows,
        zone_plus_2_rows=zone_plus_2_rows,
        cluster_row_combos=cluster_row_combos,
        zone_row_combos_plus_1=zone_row_combos_plus_1,
        zone_row_combos_plus_2=zone_row_combos_plus_2,
        coverage_rows=coverage_rows,
        cluster_digits=cluster_digits,
        zone_digits_plus_1=zone_digits_plus_1,
        zone_digits_plus_2=zone_digits_plus_2,
        coverage_digits=coverage_digits,
        combined_zone_digits=combined_zone_digits,
        pair_extended_digits=pair_extended_digits,
        double_pairs_in_zone=double_pairs_in_zone,
    )


def _select_best_cluster(match_digits: set[int]) -> tuple[int, int | None]:
    candidates: list[tuple[tuple[float, float, float, float], int, int | None]] = []

    for row in GRID_ROWS:
        candidates.append((_cluster_score((row,), match_digits), row, None))
        candidates.append((_cluster_score((row, _next_row(row)), match_digits), row, _next_row(row)))

    _, anchor_row, companion_row = max(candidates, key=lambda item: item[0])
    return anchor_row, companion_row


def _cluster_score(rows: tuple[int, ...], match_digits: set[int]) -> tuple[float, float, float, float]:
    row_set = set(rows)
    cluster_digits = {digit for row in row_set for digit in GRID_ROWS[row]}
    matched_digits = len(match_digits.intersection(cluster_digits))

    center_bonus = sum(_row_center_weight(row) for row in row_set)
    edge_penalty = sum(1 for row in row_set if row in {1, 10})
    cluster_size_bonus = 0.2 if len(row_set) == 2 and matched_digits >= 3 else 0.0

    return (
        float(matched_digits),
        center_bonus,
        cluster_size_bonus,
        -float(edge_penalty),
    )


def _row_center_weight(row: int) -> float:
    # Rows near the visual middle are preferred when matches are tied.
    return 10.0 - abs(row - 5.5) * 2.0


def _ordered_cluster_rows(anchor_row: int, companion_row: int | None) -> tuple[int, ...]:
    if companion_row is None:
        return (anchor_row,)
    if _next_row(companion_row) == anchor_row:
        return (companion_row, anchor_row)
    return (anchor_row, companion_row)


def _prev_row(row: int) -> int:
    return 10 if row == 1 else row - 1


def _next_row(row: int) -> int:
    return 1 if row == 10 else row + 1


def build_candidates(analysis: WinnerAnalysis, recency_weight: float) -> dict[tuple[int, int, int], dict[str, object]]:
    pool = set(analysis.combined_zone_digits) | set(analysis.pair_extended_digits)
    candidate_map: dict[tuple[int, int, int], dict[str, object]] = {}

    def register(combo: tuple[int, int, int], tier: str, support: str) -> None:
        existing = candidate_map.get(combo)
        weighted_score = BASE_TIER_SCORES[tier] * recency_weight
        if existing is None:
            candidate_map[combo] = {
                "core_score": weighted_score,
                "supports": {support},
                "sources": {analysis.label},
                "tiers": {tier},
            }
            return

        existing["core_score"] += weighted_score
        existing["supports"].add(support)
        existing["sources"].add(analysis.label)
        existing["tiers"].add(tier)

    for combo in analysis.cluster_row_combos:
        register(canonical_combo(combo), "tier1", f"{analysis.label}:cluster-row")

    for combo in analysis.zone_row_combos_plus_1:
        register(canonical_combo(combo), "tier2", f"{analysis.label}:zone-±1-row")

    cluster_subsets = {
        pair for combo in analysis.cluster_row_combos
        for pair in combinations(combo, 2)
    }
    tier2_pool = set(analysis.zone_digits_plus_1) | set(analysis.pair_extended_digits)
    for left, right in cluster_subsets:
        for digit in tier2_pool:
            register(canonical_combo((left, right, digit)), "tier2", f"{analysis.label}:cluster-mix")

    for combo in analysis.zone_row_combos_plus_2:
        register(canonical_combo(combo), "tier3", f"{analysis.label}:zone-±2-row")

    mixed_pool = sorted(pool)
    for combo in combinations(mixed_pool, 3):
        register(canonical_combo(combo), "tier3", f"{analysis.label}:mixed-pool")

    for repeated in mixed_pool:
        for digit in mixed_pool:
            register(canonical_combo((repeated, repeated, digit)), "tier4", f"{analysis.label}:double")

    return candidate_map


def predict_next(
    records: pd.DataFrame,
    draw_type: str,
    history_depth: int = 20,
    top_n: int = 18,
    winners_to_use: int = 3,
    include_hit_rates: bool = True,
) -> dict[str, object]:
    frame = records[records["draw_type"] == draw_type.lower()].copy().reset_index(drop=True)
    winners_to_use = max(2, min(winners_to_use, 5))
    if len(frame) < 2:
        raise ValueError(f"Need at least two {draw_type} results to predict the next draw.")

    analyses = _build_analyses(frame, draw_type, winners_to_use)
    combined = _combine_core_scores(analyses)

    core_only_snapshot = {
        combo: payload["core_score"]
        for combo, payload in combined.items()
    }
    _apply_overlap_bonus(combined, analyses)
    _apply_history_tiebreaker(combined, frame.iloc[winners_to_use : winners_to_use + history_depth])

    candidates = [
        PredictionCandidate(
            combo=combo,
            total_score=round(payload["core_score"] + payload["history_score"], 2),
            core_score=round(payload["core_score"], 2),
            history_score=round(payload["history_score"], 2),
            confidence=_confidence_from_score(float(payload["core_score"] + payload["history_score"])),
            support=tuple(sorted(payload["supports"])),
            sources=tuple(sorted(payload["sources"])),
            best_tier=min(payload["tiers"], key=lambda item: TIER_PRIORITY[item]),
        )
        for combo, payload in combined.items()
    ]
    candidates.sort(key=lambda item: (-item.total_score, -item.core_score, item.combo))

    hit_rates = (
        backtest_hit_rates(records, draw_type=draw_type, winners_to_use=winners_to_use, history_depth=history_depth, top_n=top_n)
        if include_hit_rates else None
    )

    dataset_freshness_days = _dataset_gap_days(frame)
    return {
        "draw_type": draw_type.upper(),
        "latest_inputs": frame.head(winners_to_use).copy(),
        "analyses": analyses,
        "top_candidates": candidates[:top_n],
        "all_candidates": candidates,
        "core_score_snapshot": core_only_snapshot,
        "hit_rates": hit_rates,
        "dataset_freshness_days": dataset_freshness_days,
    }


def _build_analyses(frame: pd.DataFrame, draw_type: str, winners_to_use: int) -> list[WinnerAnalysis]:
    analyses: list[WinnerAnalysis] = []
    recent = frame.head(winners_to_use).reset_index(drop=True)
    for index, row in recent.iterrows():
        digits = tuple(int(part) for part in str(row["number"]).split("-"))
        label = "latest" if index == 0 else "previous" if index == 1 else f"older-{index + 1}"
        analyses.append(analyze_winner(digits, draw_type, label))
    return analyses


def _combine_core_scores(analyses: list[WinnerAnalysis]) -> dict[tuple[int, int, int], dict[str, object]]:
    combined: dict[tuple[int, int, int], dict[str, object]] = {}
    for index, analysis in enumerate(analyses):
        recency_weight = RECENCY_WEIGHTS[min(index, len(RECENCY_WEIGHTS) - 1)]
        for combo, payload in build_candidates(analysis, recency_weight).items():
            current = combined.setdefault(
                combo,
                {
                    "core_score": 0.0,
                    "history_score": 0.0,
                    "supports": set(),
                    "sources": set(),
                    "tiers": set(),
                },
            )
            current["core_score"] += float(payload["core_score"])
            current["supports"].update(payload["supports"])
            current["sources"].update(payload["sources"])
            current["tiers"].update(payload["tiers"])
    _apply_pattern_completion_bonus(combined, analyses)
    _apply_coverage_window_bonus(combined, analyses)
    return combined


def _apply_pattern_completion_bonus(
    combined: dict[tuple[int, int, int], dict[str, object]],
    analyses: list[WinnerAnalysis],
) -> None:
    for index, analysis in enumerate(analyses):
        recency_weight = RECENCY_WEIGHTS[min(index, len(RECENCY_WEIGHTS) - 1)]
        cluster_pool = set(analysis.cluster_digits)
        near_pool = set(analysis.zone_digits_plus_1)
        outer_pool = set(analysis.zone_digits_plus_2)
        local_pool = cluster_pool | near_pool | outer_pool | set(analysis.pair_extended_digits)
        center_neighbors = _middle_pattern_digits(analysis)

        for combo, payload in combined.items():
            combo_set = set(combo)
            bonus = 0.0

            # All three digits exist inside the same local neighborhood.
            if combo_set.issubset(local_pool):
                bonus += 14.0 * recency_weight
                payload["supports"].add(f"{analysis.label}:local-pattern-complete")

            # Bridge pattern: 2 digits from the cluster + 1 from the nearest supporting rows.
            cluster_count = len(combo_set.intersection(cluster_pool))
            near_count = len(combo_set.intersection(near_pool))
            if cluster_count >= 2 and near_count >= 1:
                bonus += 20.0 * recency_weight
                payload["supports"].add(f"{analysis.label}:bridge-combo")

            # Softer bridge: 2 digits from cluster/±1 plus one from ±2.
            inner_count = len(combo_set.intersection(cluster_pool | near_pool))
            outer_count = len(combo_set.intersection(outer_pool))
            if inner_count >= 2 and outer_count >= 1:
                bonus += 9.0 * recency_weight
                payload["supports"].add(f"{analysis.label}:outer-bridge")

            # Middle completion: reward the digit that completes the visual center around the cluster.
            center_count = len(combo_set.intersection(center_neighbors))
            if center_count >= 1 and inner_count >= 2:
                bonus += 16.0 * recency_weight
                payload["supports"].add(f"{analysis.label}:middle-pattern-completion")

            # If the candidate captures all winner digits or their grid-equivalent set nearby, bump it.
            winner_shape = set(analysis.last_winner) | set(analysis.grid_equivalent)
            if len(combo_set.intersection(winner_shape)) >= 2 and combo_set.issubset(local_pool):
                bonus += 8.0 * recency_weight
                payload["supports"].add(f"{analysis.label}:winner-shape-echo")

            payload["core_score"] += bonus


def _apply_coverage_window_bonus(
    combined: dict[tuple[int, int, int], dict[str, object]],
    analyses: list[WinnerAnalysis],
) -> None:
    for index, analysis in enumerate(analyses):
        recency_weight = RECENCY_WEIGHTS[min(index, len(RECENCY_WEIGHTS) - 1)]
        coverage_pool = set(analysis.coverage_digits)
        cluster_pool = set(analysis.cluster_digits)
        near_pool = set(analysis.zone_digits_plus_1)
        outer_pool = set(analysis.zone_digits_plus_2)

        for combo, payload in combined.items():
            combo_set = set(combo)
            coverage_count = len(combo_set.intersection(coverage_pool))
            cluster_count = len(combo_set.intersection(cluster_pool))
            near_count = len(combo_set.intersection(near_pool))
            outer_count = len(combo_set.intersection(outer_pool))
            bonus = 0.0

            if coverage_count == 3:
                bonus += 18.0 * recency_weight
                payload["supports"].add(f"{analysis.label}:coverage-retention")
            elif coverage_count == 2:
                bonus += 6.0 * recency_weight
                payload["supports"].add(f"{analysis.label}:partial-coverage")

            if cluster_count >= 1 and near_count >= 2:
                bonus += 24.0 * recency_weight
                payload["supports"].add(f"{analysis.label}:anchor-plus-two-supporters")
            elif cluster_count >= 2 and near_count >= 1:
                bonus += 16.0 * recency_weight
                payload["supports"].add(f"{analysis.label}:coverage-concentration")

            # Penalize combos drifting outside the active middle coverage when outer rows dominate.
            if outer_count >= 2 and coverage_count <= 1:
                bonus -= 10.0 * recency_weight
                payload["supports"].add(f"{analysis.label}:coverage-drift")

            payload["core_score"] += bonus


def _apply_overlap_bonus(
    combined: dict[tuple[int, int, int], dict[str, object]],
    analyses: list[WinnerAnalysis],
) -> None:
    if len(analyses) < 2:
        return

    primary = analyses[0]
    secondary = analyses[1]
    primary_pool = set(primary.combined_zone_digits) | set(primary.pair_extended_digits)
    secondary_pool = set(secondary.combined_zone_digits) | set(secondary.pair_extended_digits)

    primary_rows = {
        canonical_combo(combo)
        for combo in primary.cluster_row_combos + primary.zone_row_combos_plus_1
    }
    secondary_rows = {
        canonical_combo(combo)
        for combo in secondary.cluster_row_combos + secondary.zone_row_combos_plus_1
    }
    overlap_rows = primary_rows.intersection(secondary_rows)
    overlap_digits = primary_pool.intersection(secondary_pool)

    for combo, payload in combined.items():
        combo_set = set(combo)
        bonus = 0.0
        if combo in overlap_rows:
            bonus += 45.0
            payload["supports"].add("latest+previous-row-overlap")
        if combo_set.issubset(overlap_digits):
            bonus += 22.0
            payload["supports"].add("latest+previous-digit-overlap")
        if any(digit in primary.last_winner for digit in combo):
            bonus += 10.0
            payload["supports"].add("latest-winner-recurrence")
        if any(digit in secondary.last_winner for digit in combo):
            bonus += 5.0
            payload["supports"].add("previous-winner-recurrence")
        payload["core_score"] += bonus

    if len(analyses) <= 2:
        return

    for extra_index, analysis in enumerate(analyses[2:], start=2):
        extra_pool = set(analysis.combined_zone_digits) | set(analysis.pair_extended_digits)
        overlap_with_primary = primary_pool.intersection(extra_pool)
        decay_bonus = 8.0 / extra_index
        for combo, payload in combined.items():
            if set(combo).issubset(overlap_with_primary):
                payload["core_score"] += decay_bonus
                payload["supports"].add(f"{analysis.label}-digit-overlap")


def _apply_history_tiebreaker(
    combined: dict[tuple[int, int, int], dict[str, object]],
    history: pd.DataFrame,
) -> None:
    if history.empty:
        return

    digit_frequency = {digit: 0 for digit in range(10)}
    pair_frequency: dict[tuple[int, int], int] = {}
    for number in history["number"]:
        digits = tuple(int(part) for part in str(number).split("-"))
        for digit in digits:
            digit_frequency[digit] += 1
        for left, right in combinations(sorted(set(digits)), 2):
            pair = (left, right)
            pair_frequency[pair] = pair_frequency.get(pair, 0) + 1

    max_digit = max(digit_frequency.values()) or 1
    max_pair = max(pair_frequency.values()) if pair_frequency else 1

    for combo, payload in combined.items():
        digit_score = sum(digit_frequency[digit] / max_digit for digit in combo)
        pair_score = sum(
            pair_frequency.get(pair, 0) / max_pair
            for pair in combinations(sorted(set(combo)), 2)
        )
        history_score = round((digit_score * 1.75) + (pair_score * 1.0), 2)
        payload["history_score"] += history_score
        payload["supports"].add("recent-history-tiebreaker")


def backtest_hit_rates(
    records: pd.DataFrame,
    draw_type: str,
    winners_to_use: int = 3,
    history_depth: int = 20,
    top_n: int = 18,
    lookback_predictions: int = 60,
) -> dict[str, object]:
    frame = records[records["draw_type"] == draw_type.lower()].copy().reset_index(drop=True)
    if len(frame) <= winners_to_use:
        return {"sample_size": 0, "top_n_hit_rate": 0.0, "tier_hit_rates": {}, "direct_tier_hits": {}}

    sample_size = 0
    top_hits = 0
    tier_hits = {tier: 0 for tier in TIER_PRIORITY}
    direct_tier_hits = {tier: 0 for tier in TIER_PRIORITY}

    max_target_index = min(len(frame) - winners_to_use, lookback_predictions)
    for target_index in range(max_target_index):
        target_number = canonical_combo(int(part) for part in str(frame.iloc[target_index]["number"]).split("-"))
        prediction_slice = frame.iloc[target_index + 1 :].reset_index(drop=True)
        if len(prediction_slice) < winners_to_use:
            continue

        predicted = predict_next(
            records=prediction_slice,
            draw_type=draw_type,
            history_depth=history_depth,
            top_n=top_n,
            winners_to_use=winners_to_use,
            include_hit_rates=False,
        )
        ranked = predicted["top_candidates"]
        all_ranked = predicted["all_candidates"]
        sample_size += 1

        if any(candidate.combo == target_number for candidate in ranked):
            top_hits += 1

        for tier in TIER_PRIORITY:
            tier_candidates = [candidate for candidate in ranked if candidate.best_tier == tier]
            if any(candidate.combo == target_number for candidate in tier_candidates):
                tier_hits[tier] += 1

        exact_candidate = next((candidate for candidate in all_ranked if candidate.combo == target_number), None)
        if exact_candidate is not None:
            direct_tier_hits[exact_candidate.best_tier] += 1

    return {
        "sample_size": sample_size,
        "top_n_hit_rate": round((top_hits / sample_size) * 100, 2) if sample_size else 0.0,
        "tier_hit_rates": {
            tier: round((hits / sample_size) * 100, 2) if sample_size else 0.0
            for tier, hits in tier_hits.items()
        },
        "direct_tier_hits": direct_tier_hits,
    }


def _dataset_gap_days(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    latest_date = pd.Timestamp(frame.iloc[0]["draw_date"]).normalize()
    now = pd.Timestamp.now().normalize()
    return max(int((now - latest_date).days), 0)


def _middle_pattern_digits(analysis: WinnerAnalysis) -> set[int]:
    rows = list(analysis.cluster_rows)
    if not rows:
        return set()

    middle_rows = set(rows)
    for row in rows:
        middle_rows.add(_prev_row(row))
        middle_rows.add(_next_row(row))

    digits: set[int] = set()
    for row in middle_rows:
        digits.update(GRID_ROWS[row])
    return digits


def _confidence_from_score(score: float) -> str:
    if score >= 170:
        return "High"
    if score >= 115:
        return "Medium"
    return "Speculative"


def grid_table() -> list[dict[str, int]]:
    return [
        {"row": row, "col1": values[0], "col2": values[1], "col3": values[2]}
        for row, values in GRID_ROWS.items()
    ]
