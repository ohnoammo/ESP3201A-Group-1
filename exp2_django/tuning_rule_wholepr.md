# Arm W-F (whole parent PRs, small-to-big) for Exp 2: exploratory (owner decision, 1 Nov)

Committed BEFORE any W generation.

**Status: exploratory.** Arm W was proposed after the test results were seen. It is not in the primary
60-test family, the contain-cited 20-test family or the correctness 40-test family. Every W comparison is
reported with unadjusted p only, no Holm, and labelled exploratory. No frozen arm, prompt, threshold or rule
changes because of W.

## Ranking (one arm, W-F)
- W uses the fixed 512/77 ranking: the saved top-100 fixed chunks per question
  (`results/candidates_fixed_s512_o77_k100.jsonl`; rk16129/rk9789 use `_redacted` and the redacted
  documents, as in the frozen arms). Fixed is the frozen Exp 2 chunk setting in `common.py`. It was chosen
  without reference to the fit results (structural's 34 vs 32 answer span in context was not used).
  There is no structural W arm.

## Packing (specified 23 Oct, before the fit analysis; unchanged)
- Ranked chunks -> parent PRs in first-appearance order; the row's `exclude_prs` removed (as in the
  frozen arms).
- Pack whole PR documents (`pr_document` text, Exp 1 units = `chunking.count_tokens`) in rank order into
  2,560, skipping any PR that doesn't fit. If the rank-1 PR alone exceeds 2,560, truncate it to its first
  2,560 units; nothing else then fits. No truncation at any other rank. Code: `wholepr_fit.pack_whole`.
- Rendering: one block per PR, `[PR<n>]` then the PR text, blocks joined by a blank line, in packing
  order (the frozen arms' `format_context` layout with a PR-level id). Truncation is **unmarked**, as in
  the frozen arms, where a chunk is shown with only its id and nothing marks it as partial text.
- Context length: the largest W prompt (67 questions x 2 prompts) is 3,481 Qwen tokens (q14142, v3), plus
  up to 8 Ollama tokens on 8B; num_ctx 8192.

## Generation
- Prompts v2 (`c`) and v3 (`c3`), unchanged and checked against `prompts/FROZEN.json`.
- Both models: qwen3:4b-instruct-2507-q4_K_M and qwen3:8b; temperature 0, seed 42, num_ctx 8192,
  num_predict 512, think off; Ollama 0.40.4, version guard on (the runner stops if the version changes).
- Questions: 50 answerable test + 17 unanswerable (5 no-reason test, 5 no-reason dev, 5 whole PR excluded,
  rk16129, rk9789) = 67 x 2 prompts x 2 models = 268 rows ->
  `results/gen_test_arm_W_{4b-instruct,8b}.jsonl`. Every row records config, budget, prompt version,
  Ollama version, git commit and machine/GPU.

## Scoring
- Abstention and hedged as in the frozen arms (`score.abstained_strict`, `score.hedged`), with W
  citations removed first.
- Citations are PR-level. `[PR<n>]` and `[PR<n>-c<k>]` both count as PR n; the prompts are unchanged.
  Overlap-cited and contain-cited do not apply. **Gold-PR-cited:** answered, >= 1 citation, every cited
  PR is shown in the context, and >= 1 cited PR is the question's gold PR.
- Answer span in context: a gold span is covered by the gold PR's block (whole, or the kept part of a
  truncated rank-1 PR).
- Faithfulness: premise (a) the cited whole PR block(s) as shown, primary; (b) the full context. Same
  MiniCheck-Flan-T5-Large / HHEM-2.1-Open settings and windowing as `faithfulness.py`. Answered
  answerable rows and answered unanswerable rows are scored.
- Gate (`tuning_rule_gate.md`: MiniCheck cited min < 0.5 -> abstain; no valid cited premise = gated;
  hedged = answered) is applied to W as in the frozen arms. Exploratory.
- Correctness: answered W answerable rows get new blind ids appended to `judging/codex_pack.csv`
  (`extend_judging.py` pattern, no reshuffle, citations stripped, key updated), judged with the same
  `judging/codex_instructions.md`. No human validation unless the owner asks.

## Pre-declared W comparisons (exploratory; exact McNemar on the paired questions; unadjusted p; no Holm)
- Per model x prompt (4 cells): W-F vs F0 and W-F vs S-0.25, on
  (1) strict correct /50 (Codex label correct; unanswered = not correct),
  (2) answered /50,
  (3) unanswerable answered /17.
- **W-F vs F0 is the primary exploratory comparison:** same ranking, and only packing differs (chunks vs
  whole parent PRs). **W-F vs S-0.25 differs in both ranking and packing.** It is descriptive context,
  not a packing effect.
- Descriptive subset (counts only, no test): questions where both W-F and the comparison arm have the
  answer span in context.
- The fit loss is reported as a finding: answer span in context 32/50 for W-F (fit analysis, a1c141a)
  vs 42 (F0) and 43-44 (structural arms). The packing is not changed because of it.
