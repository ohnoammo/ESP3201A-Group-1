# Hallucination limit test, H0 vs F0: rule file (5 Nov)

Committed before computing any interval, but AFTER the H0 counts and the hybrid 16 tests were seen. So this
is **exploratory**: it sits outside every Holm family and changes no frozen arm, label or finding.

**Question.** The hybrid 16 tests give "no evidence of a reduction". That does not say how large a reduction
could still be there. This test puts limits on it: how much could hybrid retrieval plausibly lower (or raise)
hallucination compared with dense, given these questions?

**Data.** The existing rows only: H0 vs F0, same model and prompt, paired by question. No new generation,
labels or scoring. Answered and label as in `stats_hybrid.py`.

## Outcomes
1. **Unanswerable answered /17** (main). Any answer here is unsupported by the PR.
2. **Answered and judged wrong /50** (secondary). Codex labels; unanswered = not wrong.

## Method
Difference = H0 minus F0, so a negative value means fewer hallucinations with hybrid.
- **Per model x prompt:** Newcombe's paired score interval (method 10, Wilson limits, no continuity correction),
  95% two-sided. Exact McNemar is not used because it gives a p value and not a limit.
- **Interval check before any result:** exact coverage by enumerating every 2x2 table at n = 17 and n = 50, at
  fixed marginal rates. The check is reported whatever it shows.
- **Pooled, per model and all 4 cells:** cells share questions, so they are not independent. Mean difference per
  cell with a PR-family percentile bootstrap, 1,000 reps, seed 42, the same families as `gate_eval.py`.

## Reading
- **Largest reduction not ruled out** = the lower limit, in questions. **Largest increase not ruled out** = the
  upper limit.
- There is **no pass/fail margin**. Choosing one after seeing the counts would be tuning on test, so only the
  limits are reported, and the owner judges whether they are small enough to matter.
- A reduction cannot exceed the F0 count, so the 4B on v3 (3 of 17) has a floor. This is noted next to the row.
- Allowed wording: "compatible with anything from X fewer to Y more unanswerable answers of 17". Not allowed:
  "hybrid does not reduce hallucination", or any claim that the two are equivalent.

Outputs: `results/limit_hybrid.csv`, `results/limit_hybrid_coverage.csv`.
