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

BASE_TIER_SCORES = {
    "tier1": 100.0,
    "tier2": 70.0,
    "tier3": 40.0,
    "tier4": 25.0,
}
RECENCY_MULTIPLIERS = {
    "latest": 1.0,
    "previous": 0.65,
}


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
    cluster_digits: tuple[int, ...]
    zone_digits_plus_1: tuple[int, ...]
    zone_digits_plus_2: tuple[int, ...]
    combined_zone_digits: tuple[int, ...]
    pair_extended_digits: tuple[int, ...]
    double_pairs_in_zone: tuple[int, ...]


@dataclass(frozen=True)
class PredictionCandidate:
    combo: tuple[int, int, int]
    score: float
    confidence: str
    support: tuple[str, ...]
    sources: tuple[str, ...]

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

    row_match_counts = {
        row: len(match_digits.intersection(GRID_ROWS[row]))
        for row in GRID_ROWS
    }
    anchor_row = min(
        row for row, score in row_match_counts.items()
        if score == max(row_match_counts.values())
    )

    anchor_matches = row_match_counts[anchor_row]
    companion_row = _choose_companion_row(anchor_row, anchor_matches, match_digits)
    cluster_rows = _ordered_cluster_rows(anchor_row, companion_row)
    zone_plus_1_rows = (_prev_row(cluster_rows[0]), _next_row(cluster_rows[-1]))
    zone_plus_2_rows = (_prev_row(zone_plus_1_rows[0]), _next_row(zone_plus_1_rows[1]))

    cluster_row_combos = tuple(GRID_ROWS[row] for row in cluster_rows)
    zone_row_combos_plus_1 = tuple(GRID_ROWS[row] for row in zone_plus_1_rows)
    zone_row_combos_plus_2 = tuple(GRID_ROWS[row] for row in zone_plus_2_rows)

    cluster_digits = tuple(sorted({digit for combo in cluster_row_combos for digit in combo}))
    zone_digits_plus_1 = tuple(sorted({digit for combo in zone_row_combos_plus_1 for digit in combo}))
    zone_digits_plus_2 = tuple(sorted({digit for combo in zone_row_combos_plus_2 for digit in combo}))

    combined_zone_digits = tuple(
        sorted(set(cluster_digits) | set(zone_digits_plus_1) | set(zone_digits_plus_2))
    )
    pair_extended_digits = tuple(
        sorted(
            {
                pair_of(digit)
            for digit in combined_zone_digits
            if pair_of(digit) not in combined_zone_digits
            }
        )
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
        cluster_digits=cluster_digits,
        zone_digits_plus_1=zone_digits_plus_1,
        zone_digits_plus_2=zone_digits_plus_2,
        combined_zone_digits=combined_zone_digits,
        pair_extended_digits=pair_extended_digits,
        double_pairs_in_zone=double_pairs_in_zone,
    )


def _choose_companion_row(anchor_row: int, anchor_matches: int, match_digits: set[int]) -> int | None:
    best_row = None
    best_score = anchor_matches
    best_start = None

    for row in (_prev_row(anchor_row), _next_row(anchor_row)):
        combined_score = len(match_digits.intersection(set(GRID_ROWS[anchor_row]) | set(GRID_ROWS[row])))
        start_row = row if _next_row(row) == anchor_row else anchor_row
        normalized_start = 0 if start_row == 10 else start_row
        if combined_score > best_score or (
            combined_score == best_score and best_row is not None and normalized_start < best_start
        ):
            best_row = row
            best_score = combined_score
            best_start = normalized_start

    return best_row if best_score > anchor_matches else None


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


def build_candidates(analysis: WinnerAnalysis, recency: str) -> dict[tuple[int, int, int], dict[str, object]]:
    pool = set(analysis.combined_zone_digits) | set(analysis.pair_extended_digits)
    candidate_map: dict[tuple[int, int, int], dict[str, object]] = {}

    def register(combo: tuple[int, int, int], tier: str, support: str) -> None:
        existing = candidate_map.get(combo)
        score = BASE_TIER_SCORES[tier] * RECENCY_MULTIPLIERS[recency]
        if existing is None or existing["score"] < score:
            candidate_map[combo] = {
                "score": score,
                "tier": tier,
                "supports": {support},
                "sources": {analysis.label},
            }
        else:
            existing["supports"].add(support)
            existing["sources"].add(analysis.label)

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
) -> dict[str, object]:
    frame = records[records["draw_type"] == draw_type.lower()].copy()
    if len(frame) < 2:
        raise ValueError(f"Need at least two {draw_type} results to predict the next draw.")

    latest_two = frame.head(2).reset_index(drop=True)
    analyses = [
        analyze_winner(tuple(int(part) for part in latest_two.iloc[0]["number"].split("-")), draw_type, "latest"),
        analyze_winner(tuple(int(part) for part in latest_two.iloc[1]["number"].split("-")), draw_type, "previous"),
    ]

    combined: dict[tuple[int, int, int], dict[str, object]] = {}
    for analysis in analyses:
        for combo, payload in build_candidates(analysis, analysis.label).items():
            current = combined.setdefault(
                combo,
                {"score": 0.0, "supports": set(), "sources": set(), "tiers": []},
            )
            current["score"] += float(payload["score"])
            current["supports"].update(payload["supports"])
            current["sources"].update(payload["sources"])
            current["tiers"].append(payload["tier"])

    _apply_overlap_bonus(combined, analyses)
    _apply_history_tiebreaker(combined, frame.iloc[2 : 2 + history_depth])

    candidates = [
        PredictionCandidate(
            combo=combo,
            score=round(payload["score"], 2),
            confidence=_confidence_from_score(float(payload["score"])),
            support=tuple(sorted(payload["supports"])),
            sources=tuple(sorted(payload["sources"])),
        )
        for combo, payload in combined.items()
    ]
    candidates.sort(key=lambda item: (-item.score, item.combo))

    return {
        "draw_type": draw_type.upper(),
        "latest_two": latest_two,
        "analyses": analyses,
        "top_candidates": candidates[:top_n],
        "all_candidates": candidates,
    }


def _apply_overlap_bonus(
    combined: dict[tuple[int, int, int], dict[str, object]],
    analyses: list[WinnerAnalysis],
) -> None:
    latest_pool = set(analyses[0].combined_zone_digits) | set(analyses[0].pair_extended_digits)
    previous_pool = set(analyses[1].combined_zone_digits) | set(analyses[1].pair_extended_digits)

    latest_rows = {canonical_combo(combo) for combo in analyses[0].cluster_row_combos + analyses[0].zone_row_combos_plus_1}
    previous_rows = {canonical_combo(combo) for combo in analyses[1].cluster_row_combos + analyses[1].zone_row_combos_plus_1}

    for combo, payload in combined.items():
        combo_set = set(combo)
        if combo in latest_rows and combo in previous_rows:
            payload["score"] += 55
            payload["supports"].add("shared-row-signal")
        if combo_set.issubset(latest_pool.intersection(previous_pool)):
            payload["score"] += 25
            payload["supports"].add("shared-digit-pool")
        if any(digit in analyses[0].last_winner for digit in combo):
            payload["score"] += 8
            payload["supports"].add("latest-winner-recurrence")
        if any(digit in analyses[1].last_winner for digit in combo):
            payload["score"] += 4
            payload["supports"].add("previous-winner-recurrence")


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
            key = (left, right)
            pair_frequency[key] = pair_frequency.get(key, 0) + 1

    max_digit = max(digit_frequency.values()) or 1
    max_pair = max(pair_frequency.values()) if pair_frequency else 1

    for combo, payload in combined.items():
        digit_score = sum(digit_frequency[digit] / max_digit for digit in combo)
        pair_score = sum(
            pair_frequency.get(pair, 0) / max_pair
            for pair in combinations(sorted(set(combo)), 2)
        )
        payload["score"] += round((digit_score * 2.5) + (pair_score * 1.5), 2)
        payload["supports"].add("recent-history-tiebreaker")


def _confidence_from_score(score: float) -> str:
    if score >= 150:
        return "High"
    if score >= 100:
        return "Medium"
    return "Speculative"


def grid_table() -> list[dict[str, int]]:
    return [
        {"row": row, "col1": values[0], "col2": values[1], "col3": values[2]}
        for row, values in GRID_ROWS.items()
    ]
