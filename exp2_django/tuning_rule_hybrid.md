# Arm H0 (hybrid retrieval) for Exp 2: rule file (5 Nov)

Committed BEFORE any hybrid retrieval or generation on the Exp 2 questions.

**Question.** Does hybrid retrieval improve context relevance and reduce hallucination compared with
dense on our "why" questions?

**Status.** H0 was proposed after the frozen results (and W-F) were seen. It is outside the primary 60,
contain 20 and correctness 40 Holm families. It has its own family, "hybrid 16". No frozen arm, prompt,
threshold, label or rule changes because of H0. "Hybrid" here always means the retriever, not the
`qwen3:4b` hybrid model behind `results/gen_test_4b-hybrid.jsonl`.

## Arm definition
H0 = F0 with one change: the ranking comes from the group's hybrid retriever instead of dense alone.

| item | F0 | H0 |
|---|---|---|
| Retriever | Exp 1 dense | Exp 1 `retrieve.py` hybrid: RRF of code-aware BM25 (k1 1.2, b 0.75) + dense, k = 60, depth 100 |
| Dense model and query | Qwen3-Embedding-0.6B, Exp 2 "why" instruction | same (same swap as `exp1_retriever.py`) |
| BM25 query | - | the question text, no instruction |
| Excluded PRs | `exclude_prs` passed to `retrieve()` | same; the filter reaches both retrievers before fusion |
| Pool, chunks | pool A, fixed 512/77, chunk set `311d0480` | same |
| Candidates saved | top 100 | top 100 |
| Packing | Exp 1 `expand_and_pack`, alpha 0, budget 2,560 Exp 1 units, score order | same |

Alpha stays 0 to match F0. Exp 1's locked `fixed.hybrid` alpha of 0.5 was for code links and bug reports
and is not used. Hybrid has no tuned settings, so nothing is tuned for H0.

## Questions and generation
- Questions: the same 67 rows as W-F: 50 answerable test + 17 unanswerable (5 no-reason test, 5 no-reason
  dev, 5 whole PR excluded, rk16129, rk9789). rk11459 and rk12342 are in `questions_test_arms.jsonl` but
  dropped from every analysis, so they are not generated.
- rk16129 and rk9789 use the redacted documents with the hybrid retriever, as the frozen arms did with dense.
- Prompts v2 (`c`) and v3 (`c3`), hashes checked against `prompts/FROZEN.json`.
- Models qwen3:4b-instruct-2507-q4_K_M (digest 0edcdef34593) and qwen3:8b (500a1f067a9f); Ollama 0.40.4,
  temperature 0, seed 42, num_ctx 8192, num_predict 512, think off, version guard on.
- 67 x 2 prompts x 2 models = 268 rows -> `results/gen_test_arm_H0_{4b-instruct,8b}.jsonl`, new context
  condition `packh-fixed-0-score`. Existing conditions are not changed.

## Indexes
- No BM25 index exists yet for chunk set `311d0480`, in either Exp 1 copy. BM25 is built only in new
  copies, `C:/Users/kwekt/ESP3201A_local/exp1_copy_hybrid` and `exp1_copy_redacted_hybrid`.
- `exp1_copy` and `exp1_copy_redacted` hold the frozen dense indexes and stay read-only. Check their
  `qdrant_exp1/meta.json` SHA-256 after the build:
  6d599f58...1eeed513 and fd8dc25d...ba61e45e. Exp 1 files in OneDrive are never edited.
- Fallback: if the redacted hybrid index cannot be built within about 30 minutes, drop rk16129 and rk9789
  from both H0 and F0 comparisons. Unanswerables are then **/15 no-rk** (not to be confused with the
  existing /15 sensitivity, which removes nr9172 and nr13883). If this happens, add a dated note here and
  commit it before generation.

## Regression check before generation
Rebuild the F0 contexts with the modified code. `context_chunk_ids` must equal the committed F0 rows for
all 65 non-redacted questions, and for rk16129 and rk9789. Any difference stops the run.

## Scoring
Same rules as the frozen arms (`score.py`): strict abstention, hedged = answered, overlap-cited and
contain-cited, empty answers. Output `results/summary_test_arm_H0.csv`.

## Pre-declared comparison: family "hybrid 16"
H0 vs F0, same model and prompt, paired by question. Exact two-sided McNemar, as in `stats_arms.py`.
4 cells (2 models x 2 prompts) x 4 outcomes = 16 tests, Holm-adjusted as one family:
1. answered /50
2. overlap-cited /50
3. unanswerable answered /17
4. strict correct /50 (Codex label correct; unanswered = not correct)

Reported per test: b (only H0), c (only F0), exact p, min attainable p = 2^(1-(b+c)), Holm p.
Output `results/stats_hybrid.csv`. No arm is called best unless it wins a Holm-adjusted test in this family.

**Limits, stated before seeing any data.** To survive Holm, the smallest p must be below 0.05/16 = 0.003125,
which takes at least 10 discordant pairs all one way (10/0, p = 0.00195; 9/0 gives 0.0039). F0 answers
3 (v3) and 7 (v2) of 17 unanswerables on the 4B, so a fall on the 4B cannot survive: 3/0 gives p = 0.25 and
7/0 gives p = 0.0156. Only the 8B (13 of 17 in both prompts) can show a surviving fall on this outcome. So
outcome 3 is reported mainly as counts, and a non-significant result here is not evidence of no effect.

## Strict and lenient correctness
- Lenient correct /50 (label correct or partial) is a sensitivity: exact McNemar, unadjusted, not in the family.
- Reason: H0 rows are judged in a later Codex session than F0. In the W-F drift check 3 of 20 labels changed,
  all partial -> correct, which can favour a newly judged arm on strict.
- A correctness difference counts as supported only if strict has Holm p < 0.05 and lenient goes the same way
  with unadjusted p < 0.05. A strict result without that is reported as not robust to label drift.

## Descriptive, no tests
- Context relevance, 50 answerables, H0 vs F0: gold PR in the first 5 distinct ranked PRs; answer span in context.
- Hallucination on answerable questions: answered and Codex label wrong /50, per cell. This uses the same
  labels and is not a third correctness outcome; it adds no test.
- Faithfulness: MiniCheck cited min and HHEM (cited and full-context premises), same settings as `faithfulness.py`,
  on answered answerable and answered unanswerable rows.
- Gate at 0.5 (`tuning_rule_gate.md`), MiniCheck cited min: answerable and unanswerable answers kept, as counts.
- Identical contexts: number of questions per cell where H0 and F0 have the same `context_chunk_ids`.
  On those rows any change of answer is non-determinism, and any change of label on identical text is label drift.
  Both are reported.

## How the research question is answered
One line per part, with counts and these caveats (50 + 17 questions, labels from a later session):
- **Context relevance:** the retrieval counts.
- **Hallucination:** unanswerable answered /17 and answered-wrong /50, with faithfulness and gate counts in support.
- "Hybrid reduces hallucination" may be written only if H0 wins outcome 3 with Holm p < 0.05, or wins outcome 4
  under the strict and lenient rule. Otherwise the wording is "no evidence of a reduction", with the counts.
  The same applies to "increases".

## Correctness labels
- Answered H0 answerable rows are appended to `judging/codex_pack.csv` through `extend_judging.py` as new blind
  ids from J0793, no reshuffle, first 792 rows byte-identical, citations stripped, key updated.
- Judged with the unchanged `judging/codex_instructions.md`, in a new file `judging/codex_labels_h.csv`. The key
  is not opened while labels are pending.
- Drift check: 20 old ids re-judged in the same session: the first 20 of J0001-J0659 in SHA-256 order of
  `h0-drift:<blind_id>`. Drift labels are used in no analysis. Direction of every change is reported.
- Existing label files are never overwritten. H0 labels are appended as `merge_w_labels.py` did, with the
  original bytes checked. New SHA-256 recorded in `HANDOVER.md`.
- Duplicate-answer check across H0 and existing rows. Conflicts are reported and not relabelled.
- No human validation of H0 labels unless the owner asks (same as W-F).

## Setup check (5 Nov, before this rule was committed)
Clean tree at 0777ebf apart from the three deliberately untracked files. `score_arms.py` on both frozen gen
files reproduces `results/summary_test_arms.csv` byte-for-byte (SHA-256 91557e4b...8e8f466d). Ollama client
0.40.4; model digests from the local manifests equal the frozen rows; prompt hashes equal `prompts/FROZEN.json`.
RTX 5070 12 GB. The running Ollama server version is checked by the runner's guard at generation.

## Amendment (5 Nov, before any hybrid retrieval or generation)
A fall in unanswerable answered can come from worse retrieval and not better abstention. So "hybrid reduces hallucination" may not rest on outcome 3 if answered /50 or answer span in context also fell for H0 in that model x prompt cell. In that case the wording is "fewer answers overall, not evidence of reduced hallucination", with the counts. This changes wording only; tests and families are unchanged.
