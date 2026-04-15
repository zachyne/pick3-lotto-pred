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
    cluster_digits: tuple[int, ...]
    zone_digits_plus_1: tuple[int, ...]
    zone_digits_plus_2: tuple[int, ...]
    combined_zone_digits: tuple[int, ...]
    pair_extended_digits: tuple[int, ...]
    double_pairs_in_zone: tuple[int, ...]


@dataclass(frozen=True)
class PredictionCandidate:
    combo: tuple[int, int, int]
    total_score: float
    core_score: float
    history_score: float
    third_digit_score: float
    confidence: str
    support: tuple[str, ...]
    sources: tuple[str, ...]
    best_tier: str
    recommended_core: tuple[int, int]
    recommended_third_digit: int
    third_digit_signals: tuple[str, ...]

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


def generate_coverage_combos(
    analysis: WinnerAnalysis,
    include_doubles: bool = True,
) -> tuple[tuple[int, int, int], ...]:
    combos = {
        canonical_combo(combo)
        for combo in (
            analysis.cluster_row_combos
            + analysis.zone_row_combos_plus_1
            + analysis.zone_row_combos_plus_2
        )
    }

    cluster_subsets = {
        pair
        for combo in analysis.cluster_row_combos
        for pair in combinations(combo, 2)
    }
    for left, right in cluster_subsets:
        for digit in analysis.zone_digits_plus_1:
            combos.add(canonical_combo((left, right, digit)))

    repeated_digits = {
        digit
        for digit in analysis.last_winner
        if analysis.last_winner.count(digit) > 1
    }
    if include_doubles and repeated_digits:
        for repeated in sorted(repeated_digits):
            for digit in analysis.combined_zone_digits:
                combos.add(canonical_combo((repeated, repeated, digit)))
                combos.add(canonical_combo((pair_of(repeated), pair_of(repeated), digit)))

    return tuple(sorted(combos))


def _candidate_completion_paths(combo: tuple[int, int, int]) -> tuple[tuple[tuple[int, int], int], ...]:
    digits = list(combo)
    seen: set[tuple[tuple[int, int], int]] = set()
    paths: list[tuple[tuple[int, int], int]] = []
    for first, second in combinations(range(3), 2):
        third_index = next(index for index in range(3) if index not in {first, second})
        core = tuple(sorted((digits[first], digits[second])))
        completion = (core, digits[third_index])
        if completion in seen:
            continue
        seen.add(completion)
        paths.append(completion)
    return tuple(paths)


def _core_pair_completion_map(analyses: list[WinnerAnalysis]) -> dict[tuple[int, int], dict[int, dict[str, object]]]:
    completion_map: dict[tuple[int, int], dict[int, dict[str, object]]] = {}
    tier_weights = {
        ("latest", "cluster"): 36.0,
        ("latest", "zone1"): 24.0,
        ("latest", "zone2"): 12.0,
        ("previous", "cluster"): 22.0,
        ("previous", "zone1"): 14.0,
        ("previous", "zone2"): 8.0,
    }

    for analysis in analyses:
        recency_scale = {
            "latest": 1.0,
            "previous": 0.72,
        }.get(analysis.label, 0.46)
        combos_by_bucket = (
            ("cluster", analysis.cluster_row_combos),
            ("zone1", analysis.zone_row_combos_plus_1),
            ("zone2", analysis.zone_row_combos_plus_2),
        )
        for bucket, combos in combos_by_bucket:
            base_weight = tier_weights.get((analysis.label, bucket), {"cluster": 14.0, "zone1": 9.0, "zone2": 5.0}[bucket])
            for combo in combos:
                ordered = tuple(int(digit) for digit in combo)
                for core, third_digit in _candidate_completion_paths(canonical_combo(ordered)):
                    completions = completion_map.setdefault(core, {})
                    payload = completions.setdefault(
                        third_digit,
                        {"score": 0.0, "signals": set()},
                    )
                    payload["score"] += base_weight * recency_scale
                    payload["signals"].add(f"{analysis.label}-{bucket}-row")

    return completion_map


def _historical_pair_completion_stats(
    frame: pd.DataFrame,
    lookback: int = 160,
) -> dict[tuple[int, int], dict[int, float]]:
    stats: dict[tuple[int, int], dict[int, float]] = {}
    sample = frame.head(lookback).reset_index(drop=True)

    for index, number in enumerate(sample["number"]):
        combo = canonical_combo(int(part) for part in str(number).split("-"))
        weight = 1.0 / (1.0 + (index * 0.12))
        for core, third_digit in _candidate_completion_paths(combo):
            completions = stats.setdefault(core, {})
            completions[third_digit] = completions.get(third_digit, 0.0) + weight

    return stats


def _digit_gap_map(frame: pd.DataFrame, lookback: int = 120) -> dict[int, int]:
    sample = frame.head(lookback).reset_index(drop=True)
    gaps = {digit: len(sample) for digit in range(10)}

    for index, number in enumerate(sample["number"]):
        digits = {int(part) for part in str(number).split("-")}
        for digit in digits:
            if gaps[digit] == len(sample):
                gaps[digit] = index

    return gaps


def _recent_digit_frequency(frame: pd.DataFrame, lookback: int = 35) -> dict[int, int]:
    sample = frame.head(lookback)
    frequencies = {digit: 0 for digit in range(10)}
    for number in sample["number"]:
        for digit in (int(part) for part in str(number).split("-")):
            frequencies[digit] += 1
    return frequencies


def _pair_affinity_map(frame: pd.DataFrame, lookback: int = 80) -> dict[int, dict[int, float]]:
    affinity: dict[int, dict[int, float]] = {digit: {} for digit in range(10)}
    sample = frame.head(lookback).reset_index(drop=True)

    for index, number in enumerate(sample["number"]):
        unique_digits = sorted({int(part) for part in str(number).split("-")})
        weight = 1.0 / (1.0 + (index * 0.08))
        for left, right in combinations(unique_digits, 2):
            affinity[left][right] = affinity[left].get(right, 0.0) + weight
            affinity[right][left] = affinity[right].get(left, 0.0) + weight

    return affinity


def _score_completion_path(
    core: tuple[int, int],
    third_digit: int,
    combo: tuple[int, int, int],
    analyses: list[WinnerAnalysis],
    completion_map: dict[tuple[int, int], dict[int, dict[str, object]]],
    pair_stats: dict[tuple[int, int], dict[int, float]],
    digit_gaps: dict[int, int],
    digit_frequency: dict[int, int],
    pair_affinity: dict[int, dict[int, float]],
) -> tuple[float, tuple[str, ...]]:
    score = 0.0
    signals: list[str] = []
    core_set = set(core)
    latest = analyses[0]
    previous = analyses[1] if len(analyses) > 1 else None

    row_hits = completion_map.get(core, {}).get(third_digit)
    if row_hits is not None:
        score += float(row_hits["score"])
        signals.extend(sorted(str(signal) for signal in row_hits["signals"]))

    pair_completion = pair_stats.get(core, {})
    pair_total = sum(pair_completion.values())
    if pair_total > 0:
        completion_ratio = pair_completion.get(third_digit, 0.0) / pair_total
        completion_score = round(completion_ratio * 32.0, 2)
        if completion_score > 0:
            score += completion_score
            signals.append(f"pair-history:{core[0]}-{core[1]}->{third_digit}")

    max_frequency = max(digit_frequency.values()) or 1
    hot_score = (digit_frequency[third_digit] / max_frequency) * 11.0
    if hot_score >= 5:
        score += hot_score
        signals.append(f"hot-digit:{third_digit}")

    max_gap = max(digit_gaps.values()) or 1
    overdue_score = (digit_gaps[third_digit] / max_gap) * 9.0
    if overdue_score >= 4:
        score += overdue_score
        signals.append(f"overdue-digit:{third_digit}")

    affinity_left = pair_affinity.get(core[0], {}).get(third_digit, 0.0)
    affinity_right = pair_affinity.get(core[1], {}).get(third_digit, 0.0)
    if affinity_left > 0 and affinity_right > 0:
        pair_affinity_score = min((affinity_left + affinity_right) * 3.2, 14.0)
        score += pair_affinity_score
        signals.append(f"pair-affinity:{core[0]}-{core[1]}")

    if third_digit in {pair_of(core[0]), pair_of(core[1])}:
        score += 8.0
        signals.append(f"mirror-pair:{third_digit}")

    combo_is_double = len(set(combo)) < 3
    if combo_is_double:
        double_pressure = 0.0
        if latest.is_double:
            double_pressure += 10.0
            signals.append("latest-double-carry")
        if previous and previous.is_double:
            double_pressure += 5.0
            signals.append("previous-double-carry")
        if any(digit in latest.double_pairs_in_zone for digit in combo):
            double_pressure += 8.0
            signals.append("latest-double-pair-zone")
        if previous and any(digit in previous.double_pairs_in_zone for digit in combo):
            double_pressure += 4.0
            signals.append("previous-double-pair-zone")
        score += double_pressure

    latest_pool = set(latest.combined_zone_digits) | set(latest.pair_extended_digits)
    if third_digit in latest_pool and core_set.issubset(latest_pool):
        score += 6.0
        signals.append("latest-zone-completion")
    if previous:
        previous_pool = set(previous.combined_zone_digits) | set(previous.pair_extended_digits)
        if third_digit in previous_pool and core_set.issubset(previous_pool):
            score += 3.0
            signals.append("previous-zone-completion")

    return round(score, 2), tuple(dict.fromkeys(signals))


def _apply_third_digit_reranker(
    combined: dict[tuple[int, int, int], dict[str, object]],
    frame: pd.DataFrame,
    analyses: list[WinnerAnalysis],
) -> None:
    completion_map = _core_pair_completion_map(analyses)
    pair_stats = _historical_pair_completion_stats(frame.iloc[len(analyses):].reset_index(drop=True))
    digit_gaps = _digit_gap_map(frame.iloc[len(analyses):].reset_index(drop=True))
    digit_frequency = _recent_digit_frequency(frame.iloc[len(analyses):].reset_index(drop=True))
    pair_affinity = _pair_affinity_map(frame.iloc[len(analyses):].reset_index(drop=True))

    for combo, payload in combined.items():
        best_score = -1.0
        best_core = combo[:2]
        best_third_digit = combo[-1]
        best_signals: tuple[str, ...] = ()

        for core, third_digit in _candidate_completion_paths(combo):
            score, signals = _score_completion_path(
                core=core,
                third_digit=third_digit,
                combo=combo,
                analyses=analyses,
                completion_map=completion_map,
                pair_stats=pair_stats,
                digit_gaps=digit_gaps,
                digit_frequency=digit_frequency,
                pair_affinity=pair_affinity,
            )
            if score > best_score:
                best_score = score
                best_core = core
                best_third_digit = third_digit
                best_signals = signals

        payload["third_digit_score"] += max(best_score, 0.0)
        payload["core_score"] += max(best_score, 0.0)
        payload["third_digit_core"] = best_core
        payload["third_digit_value"] = best_third_digit
        payload["third_digit_signals"] = best_signals
        for signal in best_signals[:3]:
            payload["supports"].add(f"third-digit:{signal}")


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
    _apply_third_digit_reranker(combined, frame, analyses)

    candidates = [
        PredictionCandidate(
            combo=combo,
            total_score=round(payload["core_score"] + payload["history_score"], 2),
            core_score=round(payload["core_score"], 2),
            history_score=round(payload["history_score"], 2),
            third_digit_score=round(float(payload["third_digit_score"]), 2),
            confidence=_confidence_from_score(float(payload["core_score"] + payload["history_score"])),
            support=tuple(sorted(payload["supports"])),
            sources=tuple(sorted(payload["sources"])),
            best_tier=min(payload["tiers"], key=lambda item: TIER_PRIORITY[item]),
            recommended_core=tuple(int(digit) for digit in payload["third_digit_core"]),
            recommended_third_digit=int(payload["third_digit_value"]),
            third_digit_signals=tuple(sorted(payload["third_digit_signals"])),
        )
        for combo, payload in combined.items()
    ]
    candidates.sort(key=lambda item: (-item.total_score, -item.core_score, item.combo))

    hit_rates = (
        backtest_hit_rates(records, draw_type=draw_type, winners_to_use=winners_to_use, history_depth=history_depth, top_n=top_n)
        if include_hit_rates else None
    )

    dataset_freshness_days = _dataset_gap_days(frame)
    primary_analysis = analyses[0]
    return {
        "draw_type": draw_type.upper(),
        "latest_inputs": frame.head(winners_to_use).copy(),
        "analyses": analyses,
        "top_candidates": candidates[:top_n],
        "all_candidates": candidates,
        "coverage_candidates": generate_coverage_combos(primary_analysis),
        "coverage_digits": primary_analysis.combined_zone_digits,
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
                    "third_digit_score": 0.0,
                    "supports": set(),
                    "sources": set(),
                    "tiers": set(),
                    "third_digit_core": None,
                    "third_digit_value": None,
                    "third_digit_signals": tuple(),
                },
            )
            current["core_score"] += float(payload["core_score"])
            current["supports"].update(payload["supports"])
            current["sources"].update(payload["sources"])
            current["tiers"].update(payload["tiers"])
    return combined


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
