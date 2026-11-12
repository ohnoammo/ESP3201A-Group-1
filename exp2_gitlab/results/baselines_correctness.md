# Baselines correctness (secondary, single labeller: Clifton, unadjusted)

Labels: `results\FOR_JAMES_baselines_labels\baselines_blind_sheet_labels.csv` (sha256 `e33bb8a084f6...`), 147 answers, final 12 Nov 2026, committed (e56c1f9, byte-exact in 4273d42) before the key was opened. Script: `score_baselines_correctness.py`.
Out of the 52 answerables per arm. An answer that is not on the sheet (not answered under strict) counts as not correct. Strict correct = `correct`; lenient correct = `correct` + `partial`.

| Arm | Answered (strict) /52 | Answered (lenient refusal rule) /52 | Strict correct /52 | Lenient correct /52 | Partial | Wrong | Not answered |
|---|---|---|---|---|---|---|---|
| F0 | 43 | 43 | 30 | 42 | 12 | 1 | 9 |
| P0 | 52 | 47 | 30 | 47 | 17 | 5 | 0 |
| CB | 52 | 51 | 0 | 3 | 3 | 49 | 0 |
| F0_rerun | 43 | 43 | 30 | 42 | 12 | 1 | 9 |

F0_rerun is a check only: its answers are mapped to the sheet by question and citation-stripped text. Same label as F0 on all 52: True; unmapped F0_rerun answers: none.

Labels on answers that the lenient refusal rule counts as refusals (they are on the sheet because the sheet takes strict-answered answers): F0 correct 0, partial 0, wrong 0; P0 correct 1, partial 0, wrong 4; CB correct 0, partial 0, wrong 1; F0_rerun correct 0, partial 0, wrong 0

## Exact McNemar, two-sided, unadjusted (secondary)

b = correct for F0 only, c = correct for the other arm only. p from `exp2_scale_stats.mcnemar`.

| Comparison | Scoring | F0 correct | Other correct | b | c | p (unadjusted) |
|---|---|---|---|---|---|---|
| F0 vs P0 | strict | 30 | 30 | 4 | 4 | 1 |
| F0 vs P0 | lenient | 42 | 47 | 1 | 6 | 0.125 |
| F0 vs CB | strict | 30 | 0 | 30 | 0 | 1.86e-09 |
| F0 vs CB | lenient | 42 | 3 | 40 | 1 | 3.82e-11 |

## Cross-checks

Answered per arm against `results/baselines_counts.csv` (answerables):

| Arm | Strict here | Strict in counts | Lenient here | Lenient in counts | Match |
|---|---|---|---|---|---|
| F0 | 43 | 43 | 43 | 43 | yes |
| P0 | 52 | 52 | 47 | 47 | yes |
| CB | 52 | 52 | 51 | 51 | yes |
| F0_rerun | 43 | 43 | 43 | 43 | yes |

F0: old provisional labels (`exp2_gitlab_A2000/correctness_sheet.csv`, mapped by `exp2_gitlab_baselines.f0_labels`, mapping problems: none) against Clifton's. Old: strict 33/52, lenient 40/52. New: strict 30/52, lenient 42/52. Answers labelled in one sheet only: none.

Agreement on the 43 F0 answers in both (rows old, columns Clifton):

| Old \ Clifton | correct | partial | wrong | total |
|---|---|---|---|---|
| correct | 28 | 5 | 0 | 33 |
| partial | 2 | 4 | 1 | 7 |
| wrong | 0 | 3 | 0 | 3 |
| total | 30 | 12 | 1 | 43 |

Exact agreement 32/43. Cohen's kappa (unweighted, 3 labels) 0.387; on strict correct vs not 0.587; on lenient correct vs wrong -0.036.
