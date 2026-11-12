# Correctness rule for Exp 2 (committed BEFORE any correctness McNemar test; owner decisions, 1 Nov)

Labels: Codex blind labels (`judging/codex_labels.csv`, 659 answered answerable test rows,
`judging/codex_instructions.md`) are the primary correctness labels. Joined to rows through
`judging/keys/judging_key.json` (built 23 Oct by `build_judging.py` + `extend_judging.py`).

- Unit: the 50 answerable test questions, per model x arm x prompt.
- Abstained or empty rows (`score.abstained_strict`, empty after citation removal) have no label and
  count as not correct.
- Hedged rows (refusal sentence plus other content) count as answered and are judged like any answer.
- strict = label correct; lenient = label correct or partial. "Answered but wrong" is answered minus
  correct and is not a separate outcome.
- Tests: exact two-sided McNemar on discordant pairs, 40 tests = 2 models x 10 pairs (F0 vs S0,
  S0 vs S0-G, S0-G vs S-0.25 within each prompt; v2 vs v3 within each of the 4 arms) x {strict,
  lenient}. Holm-adjusted as one family of 40, separate from the 60-test and 20-test families of
  `stats_arms.py`. Reported per test: b/c, exact p, min attainable p = 2^(1-(b+c)), Holm p.
- No arm is called best or most correct unless it wins a test with Holm p < 0.05 in this family;
  otherwise counts only.
- Judge agreement: Codex vs Alyssa on `judging/validation_sample.csv` (n = 80, 10 per model x prompt
  x chunking stratum, same blind ids as the Codex pack). Alyssa is the reference rater and labelled
  independently: only blind_id, question, gold answer, gold quotes and model answer; no Codex labels,
  model or condition; she never opened `judging/keys/` or `judging/codex_labels.csv`.
  Label file `judgements/validation_sample_alyssa.csv`, SHA-256 e7cea708...fdf775a
  (`results/run_provenance.md`). Reported: 3-label Cohen's kappa and binarised kappas (correct vs
  rest; correct or partial vs wrong), each with a row bootstrap 95% CI, 3x3 confusion table (rows =
  Alyssa), per-class specific agreement.

Implemented in `stats_correctness.py` (tests), `correctness_tables.py` (counts), `agreement.py`.

Timing: the 40-test design has been in `stats_correctness.py` since f987288 (23 Oct) and is
unchanged at 7208130, before any label was read row-level. The descriptive correctness tables
(`results/correctness_test_arms.csv`, 76cdb1c, 1 Nov) and the first 79-row agreement run were
produced before this rule file was committed.
