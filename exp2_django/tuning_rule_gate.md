# Faithfulness gate rule for Exp 2 (written and committed BEFORE computing anything; James, 23 Oct)

Gate: an answered row is replaced by an abstention if its cited-chunk MiniCheck min-sentence score
(`minicheck_cited_min` from `faithfulness.py`, chunk-aligned windows) is < 0.5.

- Threshold fixed at 0.5. No tuning, on test or dev.
- Rows with no valid citation (no cited-chunk premise, score None) are gated.
- Hedged rows (refusal sentence plus other content) count as answered, so they are gated by the
  same rule.
- Applies to every answered row: the 50 test answerables and the 17 unanswerable rows (5 no-reason
  test, 5 no-reason dev, 5 whole PR excluded, PR kept rk16129 and rk9789), both models, all arms
  and prompts.
- Primary result: threshold 0.5. A threshold sweep 0.1-0.9 (step 0.1) is secondary and is not used
  to pick a threshold.

Implemented in `gate_eval.py`.

Threshold 0.5 specified in planning before the full faithfulness run (only a 30-row check existed). The rule file was committed after results/summary_faithfulness.csv (2da7d48 before 074812c).
