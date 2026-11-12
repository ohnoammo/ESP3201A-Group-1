# Post-hoc re-scoring: paraphrased refusals (added 10 Nov 2026, AFTER seeing the results)

**Not pre-registered. Report it as post hoc, next to (not instead of) the pre-registered tests in `codex_report.md`.**

Steered answers often refuse in their own words ("The excerpts do not state the reason why ...") instead of the exact
sentence "Not found in the provided PRs". The pre-registered scorer (`abstained_strict` from Exp 2) only recognises the exact
sentence, so it counts these as answers (uncited ones), which is why `answered` barely moves while `overlap-cited` collapses.

Here an answer also counts as a refusal if it matches, case-insensitive:
`(do(es)? not (state|contain|mention|provide|explain|specify)|not found in the provided)`

| Arm | Unanswerables answered /18 | only unsteered / only steered | p | Answerables answered /52 | only unsteered / only steered | p | Paraphrased refusals |
|---|---|---|---|---|---|---|---|
| unsteered | 7 | | | 48 | | | 0 |
| steered 40:60 | 7 | 0 / 0 | 1.0000 | 48 | 0 / 0 | 1.0000 | 0 |
| steered 50:50 | 5 | 2 / 0 | 0.5000 | 41 | 7 / 0 | 0.0156 | 3 |
| steered 60:40 | 3 | 4 / 0 | 0.1250 | 38 | 10 / 0 | 0.0020 | 8 |

Exact McNemar, two-sided, unadjusted. Two of the unsteered model's 7 answered unanswerables (nr3177, nr4460) have doubtful
`no_reason` labels (their answers are grounded; see the pair check), so the hallucination count is itself uncertain.
