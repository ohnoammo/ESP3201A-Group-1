# Baselines correctness (blind sheet, unblinded)

Labels: `results\FOR_JAMES_baselines_labels\baselines_blind_sheet_labels.csv` (sha256 e33bb8a084f661e3...), 147 answers, final on 12 Nov 2026 (Clifton), before the key was opened.

| Arm | Answered (strict) /52 | correct | partial | wrong | Strict correct /52 | Lenient correct /52 |
|---|---|---|---|---|---|---|
| F0 | 43 | 30 | 12 | 1 | 30 | 42 |
| P0 | 52 | 30 | 17 | 5 | 30 | 47 |
| CB | 52 | 0 | 3 | 49 | 0 | 3 |

Exact McNemar, two-sided, unadjusted (pre-registered):

| Comparison | Scoring | F0 | Other | F0 only | Other only | p |
|---|---|---|---|---|---|---|
| F0 vs P0 | strict | 30 | 30 | 4 | 4 | 1 |
| F0 vs P0 | lenient | 42 | 47 | 1 | 6 | 0.125 |
| F0 vs CB | strict | 30 | 0 | 30 | 0 | 0 |
| F0 vs CB | lenient | 42 | 3 | 40 | 1 | 0 |

F0 new vs provisional labels: 32/43 F0 answers got the same label as in the provisional sheet; changes (old -> new): {'wrong->partial': 3, 'partial->correct': 2, 'correct->partial': 5, 'partial->wrong': 1}; mapping problems: []
