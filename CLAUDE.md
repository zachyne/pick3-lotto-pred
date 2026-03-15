# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Predict the next ANY 3 lotto winning number using a two-step pipeline:
1. **Visualize** the last winning number on a reference grid to identify the prediction zone
2. **Predict** all possible winning combinations from that zone

## Two-Agent Architecture

### Agent 1: `lotto-pattern-visualizer`
- **Input**: Last winning number (e.g., `0-6-1`) + draw type (midday/evening)
- **Output**: PNG visualization of the reference grid (green = winner, red = zone) + structured `ZONE_DATA` block
- **Does NOT** predict combinations — visualization only

### Agent 2: `lotto-predictor`
- **Input**: `ZONE_DATA` block from the visualizer
- **Output**: All possible 3-digit combinations ranked in confidence tiers (Tier 1–4) + 2-of-3 partial win pairs
- **Does NOT** render grids — prediction only

Agents are defined in `.claude/agents/`.

## Core Game Rules (ANY 3)

- 3 digits drawn from 0–9
- "ANY" bet type: order doesn't matter — `1-2-3` wins on any permutation
- Partial win: matching 2 of 3 digits in any position also pays
- Midday and evening are completely separate games — never mix their data
- Double digits are valid wins (e.g., `9-6-9`)

## The Two Reference Systems

### 1. Reference Grid (3-column cyclic chart)
```
Row  Col1  Col2  Col3
 1     7     3     0
 2     8     4     1
 ...   (cycles 0–9 per column, wraps mod 10)
```
- Previous winner's row position on the grid defines the **prediction zone** (±1 and ±2 rows)
- The zone's digits are the raw material for combination generation

### 2. Double Digit Pairing Template
```
0  1  2  3  4
5  6  7  8  9
```
- Pairs: 0↔5, 1↔6, 2↔7, 3↔8, 4↔9
- When a winning number has a repeated digit (e.g., `9-6-9`), substitute one occurrence with its pair (`9→4`) to get the grid-equivalent (`9-6-4`) for grid mapping
- Digits that are pairs of each other appearing together in the zone signal a likely double in the next draw

## Prediction Philosophy

- **The previous winning draw is the primary signal** — not historical frequency
- All-time stats are only a tiebreaker using the last 10–30 draws
- Always check both the standard grid AND the double-digit template for every prediction

## Data & Output Paths

- Source data (Excel files): `templates/`
- Visualization outputs: `templates/output/`
- Filename convention: `[midday|evening]_grid_YYYY-MM-DD.png`
