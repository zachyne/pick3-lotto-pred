---
description: "Visualize a winning ANY 3 number on the reference grid. Usage: /visualize-lotto [winning number] [midday|evening]"
argument-hint: "[D1-D2-D3] [midday|evening]"
---

You are a lotto grid visualization specialist. The user has provided: $ARGUMENTS

Parse the input to extract:
- The winning 3-digit number (e.g., `0-6-1` or `061`)
- The draw type: midday or evening (default to midday if not specified)

Then perform the following steps:

## Step 1: Handle Double Digits

Check if the winning number has a repeated digit (e.g., `9-6-9`).

If yes, apply the **double-digit pairing template** to derive the grid-equivalent:
```
0  1  2  3  4
5  6  7  8  9
```
Pairs: 0↔5, 1↔6, 2↔7, 3↔8, 4↔9

Substitute one occurrence of the repeated digit with its pair.
Example: `9-6-9` → replace one `9` with `4` → grid-equivalent = `9-6-4`

Work with BOTH the original AND the grid-equivalent from here on.

## Step 2: Build the Reference Grid

The reference grid is a 3-column cyclic table anchored at **7-3-0** (top row):

```
Row  Col1  Col2  Col3
 1     7     3     0
 2     8     4     1
 3     9     5     2
 4     0     6     3
 5     1     7     4
 6     2     8     5
 7     3     9     6
 8     4     0     7
 9     5     1     8
10     6     2     9
11     7     3     0  (wrap)
```

Column starts: Col1=7, Col2=3, Col3=0. Each column cycles 0–9 mod 10.
To find digit D in a column starting at S: `row = (D − S) mod 10 + 1`

## Step 3: Find the Cluster Row(s)

**Do NOT assign D1→Col1, D2→Col2, D3→Col3.** Instead, scan every row to find where the winning digits naturally group together.

For each row R (1–10), the three digits are:
- Col1_R = (R + 6) mod 10
- Col2_R = (R + 2) mod 10
- Col3_R = (R − 1) mod 10

**Count matches**: For each row R, count how many of {D1, D2, D3} appear in {Col1_R, Col2_R, Col3_R}.

**Find the cluster**: Look for a single row or pair of adjacent rows (R, R+1) whose combined cells contain the most winning digits (ideally all 3). If multiple pairs tie, prefer the one with the lowest starting row.

- The row with the **most matches** = **anchor row**
- The adjacent row that contributes remaining winning digits = **companion row** (may be above or below)
- Together they form the **cluster** (1–2 rows)

> Example: Winner 1-3-4 → Row 2 = [8,4,1] has digits 4 and 1 (2 matches); Row 1 = [7,3,0] has digit 3 (1 match). Cluster = Rows 1–2 (anchor = Row 2, companion = Row 1). ✓

## Step 4: Define the Prediction Zone

The zone is defined relative to the **cluster boundaries** (not individual column rows).

Let cluster span rows [C_min, C_max] (e.g., rows 1–2 → C_min=1, C_max=2):

- **Cluster rows** (🟢): C_min through C_max — these are the highest-confidence rows
- **±1 zone** (🔴): one row above C_min and one row below C_max (wraps mod 10)
- **±2 zone** (🟡): two rows above C_min and two rows below C_max (wraps mod 10)

Collect all 3-digit values for each zone row. These row-triples (each complete row's digits) are direct prediction candidates — **each zone row read left-to-right as [Col1, Col2, Col3] is a combo**.

**Also compute the pair-extended pool**: For every digit D in the combined zone (all zone rows), compute its pair P using the double-digit template (0↔5, 1↔6, 2↔7, 3↔8, 4↔9). If P is NOT already in any zone row, add P to `pair_extended_digits`. Winner digits (D1, D2, D3) are never silently dropped — if any winner digit equals a pair-extended digit, it is automatically confirmed as a high-priority candidate.

## Step 5: Render the Grid

Print the full reference grid as a formatted table. Mark **entire rows** (all 3 cells):
- 🟢 = cluster row (anchor + companion) — entire row highlighted
- 🔴 = ±1 zone row — entire row highlighted
- 🟡 = ±2 zone row — entire row highlighted
- (blank) = outside zone

Example row format: `| Row 2 | 🟢 8 | 🟢 4 | 🟢 1 |`

Print the complete grid with all 11 rows (including the wrap row).

## Step 6: Output the ZONE_DATA Block

After the grid, output this structured block exactly (for use by `/predict-lotto`):

```
ZONE_DATA:
draw_type: [MIDDAY|EVENING]
last_winner: [D1-D2-D3]
is_double: [true|false]
grid_equivalent: [D1-D2-D3]
anchor_row: [R]           ← row with most winning digit matches
companion_row: [R' or "none"]  ← adjacent row completing the cluster
cluster_rows: [list]      ← anchor + companion
cluster_match_count: [N]  ← how many winning digits found in cluster
zone_±1_rows: [row numbers]   ← 1 row above/below cluster boundaries
zone_±2_rows: [row numbers]   ← 2 rows above/below cluster boundaries
cluster_row_combos: [each cluster row as a 3-digit combo, e.g. "8-4-1", "7-3-0"]
zone_row_combos_±1: [each ±1 row as a 3-digit combo]
zone_row_combos_±2: [each ±2 row as a 3-digit combo]
all_zone_digits_cluster: [flat unique sorted list from cluster rows]
all_zone_digits_±1: [flat unique sorted list from ±1 rows]
all_zone_digits_±2: [flat unique sorted list from ±2 rows]
double_pairs_in_zone: [digits in combined zone whose pair is also in zone, or "none"]
winner_digits: [unique sorted digits of last_winner]
pair_extended_digits: [digits NOT in combined zone whose pair IS in combined zone; flag winner digits that qualify]
```

Save the grid visualization to `templates/output/[midday|evening]_grid_[YYYY-MM-DD].txt` if the `templates/output/` directory exists. If it doesn't exist, skip saving and just display.

Finally, tell the user: "Run `/predict-lotto` with the ZONE_DATA above to get all possible winning combinations."
