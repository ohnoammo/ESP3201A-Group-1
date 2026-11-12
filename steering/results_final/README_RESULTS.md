# Steering results: final (10 Nov 2026)

These are the final results of the activation-steering run on the GitLab Runner 70. This is not RL or fine-tuning.

- James ran the experiment with the `CODEX_steering` build. Claude's independent checker (`verify_codex_results.py`) passed every check.
- Clifton labelled all 87 blind answers (`blind_sheet_labels.csv`). The key (`keys/`) was opened only after labelling.

What to read:
- `codex_report.md`: the full results, including the pre-registered tests (Holm, 9 tests) and the correctness tables.
- `posthoc_paraphrased_refusals.md`: the re-scoring that counts reworded refusals as refusals. It is post hoc and must be labelled that way in the report.
- `sweep.png` / `sweep.csv`: a descriptive trade-off figure (refusal vs answering across settings).
- `stats.json`, `stats_tests.csv`, `stats_arms.csv`: the numbers in machine-readable form.
- `gen_*.jsonl`: every model answer. `selection.json`: the setting chosen for each fold. `vector_info.json`: the vector norms.

Results in one paragraph:
- **40:60** never steered, so its results equal the unsteered model's.
- **60:40** roughly halved hallucinated answers on the unanswerables (7 → 3 /18, post hoc, not significant). The cost: 10 more refusals of questions that had an answer, and correct answers fell from 39 to 12 out of 52.
- **Overall:** the unsteered model is the best.
