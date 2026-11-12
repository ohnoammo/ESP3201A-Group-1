# Exp 2 baselines on GitLab Runner: plain RAG, closed book, the gate, and retrieval carry-through

Run unattended on the night of 11 Nov 2026 (branch `exp2-baselines`). Rule: `tuning_rule_baselines.md`, committed at `f33ead5` and revised after advisor check 1 at `da8e9d8`. Both commits came before any P0, CB or re-run answer existed. Log of every step and decision: `results/RUN_LOG.md`.

**Status:** exploratory transfer check on GitLab Runner (pool A2000, 70 questions: 52 answerable, 8 no_reason, 10 removed; `exp2_gitlab_A2000/questions.jsonl`). It is not in the Exp 2 Findings and not compared with Django as like for like. Nothing was trained; the arms differ only in prompt and context. So nothing here is RL or learning.

**Arms.** All use the 4B (`qwen3:4b-instruct-2507-q4_K_M`, digest `0edcdef34593`) with F0's settings:
- Ollama 0.40.4, temperature 0, seed 42, `num_ctx` 8192, `num_predict` 512, think off.
- These were read from all 70 F0 rows and `exp2_gitlab_scale.py`, and recorded in `exp2_gitlab_A2000/run_meta_baselines.json`.

| Arm | Context | Prompt |
|---|---|---|
| F0 | dense, fixed 512/77, alpha 0, budget 2,560 | strict grounded v3: cite `[PRn-cm]` or say "Not found in the provided PRs" |
| P0, plain RAG | F0's exact chunks, rebuilt and asserted equal on ids and tokens for all 70 | "You are a helpful assistant. Use the following context from GitLab Runner merge requests to answer the question." No citation or refusal rule |
| CB, closed book | none | "You are a helpful assistant. Answer the question about the GitLab Runner project." |

F0 is the stored `gen_F0.jsonl`.

**Reproducibility.**
- Re-generating F0 on the first 10 sorted ids gave 9/10 byte-identical answers (`q106` differed after the first 120 characters; `results/baselines_repro10.csv`). That passes the pre-registered bar of 8.
- A full 70-question F0 re-run then matched the stored F0 on 70/70, `q106` included (`exp2_gitlab_A2000/gen_F0_rerun.jsonl`). So F0 and the baselines ran under the same decoding conditions. Decoding is close to repeatable but not exactly so.

## Task 1: does the grounded prompt reduce hallucination compared with ordinary RAG? (pre-registered)

**Scoring.**
- **Lenient (primary):** an answer is a refusal if it is empty or matches the pre-registered regex; otherwise it is "answered".
- **Strict (secondary):** P0 and CB answer 18/18 and 52/52 by construction, because they are never told the exact "Not found in the provided PRs" sentence. So strict says nothing about the baselines; that is why lenient is primary.
- **Broad (sensitivity):** lenient OR a wider refusal regex, added after advisor check 1 but before any generation.
- **"Unanswerable answered"** is the pre-registered hallucination outcome: an answer given where the MR states no reason, or where the MR was removed from the pool. As read after the run (below), it also counts some answers that reject the question's premise, and one refusal written in markdown bold.

**Counts per arm** (`results/baselines_counts.csv`):

| Arm | Unanswerables answered /18: lenient (primary) | strict | broad | Answerables answered /52: lenient (primary) | strict | broad | Any citation /52 | Valid citation /52 | Overlap-cited /52 |
|---|---|---|---|---|---|---|---|---|---|
| CB | **18** | 18 | 17 | **51** | 52 | 47 | 0 | 0 | 0 |
| P0 | **13** | 18 | 12 | **47** | 52 | 44 | 12 | 12 | 10 |
| F0 | **5** | 5 | 5 | **43** | 43 | 42 | 43 | 43 | 40 |
| F0 re-run | 5 | 5 | 5 | 43 | 43 | 42 | 43 | 43 | 40 |

The citation columns are descriptive only.

**Tests:** exact McNemar, two-sided; b = only F0 answered, c = only the other arm answered (`results/baselines_tests.csv`).

| Family | Comparison | Outcome | n | F0 | Other | b / c | p | Holm p |
|---|---|---|---|---|---|---|---|---|
| **Primary, lenient (Holm over 4)** | F0 vs P0 | unanswerable answered | 18 | 5 | 13 | 0 / 8 | 0.0078 | **0.023** |
| | F0 vs P0 | answerable answered | 52 | 43 | 47 | 1 / 5 | 0.219 | 0.219 |
| | F0 vs CB | unanswerable answered | 18 | 5 | 18 | 0 / 13 | 0.00024 | **0.00098** |
| | F0 vs CB | answerable answered | 52 | 43 | 51 | 1 / 9 | 0.021 | **0.043** |
| Secondary, strict (Holm over 4) | F0 vs P0 | unanswerable / answerable | 18 / 52 | 5 / 43 | 18 / 52 | 0/13, 0/9 | 0.00024, 0.0039 | 0.00098, 0.0078 |
| | F0 vs CB | unanswerable / answerable | 18 / 52 | 5 / 43 | 18 / 52 | 0/13, 0/9 | 0.00024, 0.0039 | 0.00098, 0.0078 |
| Sensitivity: without nr3177, nr4460 (Holm over 4) | F0 vs P0 | unanswerable answered | 16 | 3 | 11 | 0 / 8 | 0.0078 | 0.023 |
| | F0 vs CB | unanswerable answered | 16 | 3 | 16 | 0 / 13 | 0.00024 | 0.00098 |
| | both | answerable answered | 52 | as primary | | | | |
| Sensitivity: broad refusal (Holm over 4) | F0 vs P0 | unanswerable / answerable | 18 / 52 | 5 / 42 | 12 / 44 | 0/7, 3/5 | 0.016, 0.727 | 0.047, 0.727 |
| | F0 vs CB | unanswerable / answerable | 18 / 52 | 5 / 42 | 17 / 47 | 0/12, 4/9 | 0.00049, 0.267 | 0.0020, 0.534 |
| Sensitivity: F0 re-run (unadjusted) | vs P0, vs CB | all four | | identical to primary | | | | |

**For the report (pre-registered result, then post-hoc reading).**
- **As pre-registered:** with the same retrieved context, the strict grounded prompt (F0) answered 5 of 18 unanswerable questions and the plain RAG prompt (P0) answered 13. All 8 discordant questions favoured F0 (0 / 8; exact McNemar Holm p = 0.023 in the pre-registered family of four).
- The closed-book model (CB) answered all 18 (0 / 13, Holm p < 0.001).
- **Sensitivities:**
  - without the two doubtful no_reason questions: same direction and Holm p (3 vs 11 of 16, 0.023);
  - with the broad refusal regex: same direction (5 vs 12, Holm p = 0.047), marginal;
  - against a fresh F0 re-run: identical.
- **On answerables:** P0 answered slightly more than F0 (47 vs 43, not significant), and CB answered 51 (Holm p = 0.043).
- **Answering is not being right.** CB answered without seeing any MR, and the correctness of P0's and CB's answers is not yet labelled (see the blank sheet below).
- **Post-hoc reading (advisor check 3 and my own reading; not rescored, the pre-registered scores stand).** The F0 vs P0 hallucination difference is less sturdy than its p value suggests:
  - **P0 `nr3147` is a plain refusal** ("the text does **not** explain why…"). Both regexes miss it because of the markdown bold. Read as a refusal, the primary test becomes 0 / 7 (p 0.016, Holm 0.047) and the broad test 0 / 6 (p 0.031, Holm 0.094).
  - **Four more P0 "answers" reject the question's premise instead of inventing a reason:** `rm3960`, `rm3119`, `nr4102`, `rm584`. For example, "the backoff does NOT top out at 5 seconds". These are confident claims that contradict a true premise, so whether they count as hallucinations is a judgement. If all five were read as non-answers, F0 vs P0 would be 0 / 3 (p 0.25).
  - **P0's three other extra answers invent a reason:** `rm2971`, `nr5841`, `nr1372`. F0's 5 answered unanswerables all give a reason ("Because…").
  - **CB's 18 also include premise rejections** (for example `rm4142`, `rm7008`) and "no official documentation" statements (`rm3846`, `rm3119`). But CB answers every one of them without context, and F0 vs CB stays far apart under any of these readings.
  - **So:** a person should read P0's 13 and CB's 18 answered unanswerables (`results/baselines_unanswerable_answered.csv` has the first 200 characters; full text in `gen_P0.jsonl` and `gen_CB.jsonl`). Claim that grounding reduces hallucination compared with plain RAG only after that read.
- **Reading the discordant answerable pairs (post hoc, not rescored):** in both answerable tests, the single b question is not a clear F0-only answer. P0 `q3958` is a real answer that the lenient regex reads as a refusal ("does not provide"), and CB `q3246` is borderline ("there is no official option"). See `results/baselines_audit_lenient.csv`.

**Which unanswerables were answered** (`results/baselines_unanswerable_answered.csv`):
- F0: `rm3846`, `nr3177`, `nr1781`, `nr3805`, `nr4460`.
- P0: those 5 plus `rm584`, `rm3960`, `rm2971`, `rm3119`, `nr5841`, `nr3147`, `nr1372`, `nr4102`.
- CB: all 18.

**Audits (pre-registered, nothing rescored):**
- `results/baselines_audit_lenient.csv` has 11 rows that strict counts as answered and lenient as refusals. By my reading most are real refusals ("there is no information explaining…"). P0 `q3958` is a false refusal, and CB `q3246` and P0 `rm3265` are borderline.
- `results/baselines_audit_broad.csv` has 11 rows that only the broad regex calls refusals. Most are real answers, such as F0 and P0 `q1754`, "forks … do not have access to the container registry". So the broad sensitivity under-counts answering for every arm, and for P0/CB it is a conservative check.

## Task 2: the faithfulness gate on new data (exploratory; P0 is new, F0 is a repeat)

**The gate.** It is Django's rule unchanged (`ESP3201A_Exp2/tuning_rule_gate.md`). An answered row abstains if its minimum MiniCheck-Flan-T5-Large support over sentences, with the cited chunks as premise, is below 0.5. An answer with no valid citation is gated. The code was imported from `ESP3201A_Exp2/faithfulness.py` and `gate_eval.py`, not copied. It ran at revision `96eafd01` on the GPU and scored 118 rows (`results/baselines_gate_rows.jsonl`).

**Counts, before → after the gate, lenient** (`results/baselines_gate.csv`; strict is in the same file):

| Arm | Unanswerables answered /18 | Answerables answered /52 | Strictly correct kept /52 (provisional labels) |
|---|---|---|---|
| F0 | 5 → 2 | 43 → 42 | 33 → 32 |
| P0 | 13 → 0 | 47 → 4 | not labelled |

**Exploratory McNemar, gate vs no gate** (`results/baselines_gate_tests.csv`; the gate only removes answers, so c = 0). The P0 tests are mechanical: uncited answers are gated by rule.

| Arm | Outcome | b | p | Holm over the 4, for reference |
|---|---|---|---|---|
| F0 | unanswerables | 3 | 0.25 | 0.5 |
| F0 | answerables | 1 | 1.0 | 1.0 |
| P0 | unanswerables | 13 | 0.00024 | 0.00073 |
| P0 | answerables | 43 | 2.3e-13 | 9.1e-13 |

**For the report (exploratory).**
- Applied unchanged with its Django threshold, the gate removed 3 of F0's 5 answered unanswerables:
  - `rm3846` (support 0.25);
  - `nr3177` (0.07);
  - `nr3805` (0.41).
- It cost one answerable (`q3831`, 0.497) and one provisionally correct answer.
- On P0 the gate removes almost everything, because by rule it gates every answer without a valid citation. 46 of P0's 60 lenient-answered rows (13 unanswerable + 47 answerable) had no valid cited chunk. So "P0 + gate" says that P0 rarely cites, not that P0's answers are unsupported.
- The F0 numbers repeat the earlier GitLab gate run exactly. All 48 decisions match `exp2_gitlab_A2000/gate_F0.jsonl`, with a maximum score difference of 0.0 (`results/baselines_gate_crosscheck.json`). So the new information here is that the Django code, imported directly, gives the same result, plus the P0 rows.
- F0's correctness labels are provisional: James's 20 plus Codex's 67, with Alyssa's review still due. They are mapped without opening `keys/`: 87/87 sheet rows were re-derived and their text checked, with 0 problems.

## Task 3: does retrieval carry through into generation? (descriptive)

**GitLab F0, 52 answerables** (`results/baselines_carry.csv`, rows in `results/baselines_carry_rows.csv`):

| Split | Group | n | Answered | Overlap-cited | Correct / partial / wrong (provisional) |
|---|---|---|---|---|---|
| Gold answer span in context | yes | 47 | 42 | 40 | 33 / 7 / 2 |
| | no | 5 | 1 | 0 | 0 / 0 / 1 |
| Gold MR rank in candidates | top 5 | 51 | 43 | 40 | 33 / 7 / 3 |
| | lower (`q3137`, rank 20) | 1 | 0 | 0 | 0 / 0 / 0 |
| Finer rank (chosen in the rule) | rank 1 | 44 | 39 | 37 | 30 / 7 / 2 |
| | rank 2-5 | 7 | 4 | 3 | 3 / 0 / 1 |

- **GitLab H0 vs F0:** skipped. No GitLab `gen_H0.jsonl` exists; the only H0 generations are Django's and SymPy's (RUN_LOG).
- **Django Exp 2, cited without recomputing** (`results/baselines_django_extract.csv`, copied from `ESP3201A_Exp2/results/stats_test_arms.csv` and `pr_length_tertiles.csv`):
  - 4B, prompt v3, fixed (F0) vs structural (S0) chunking: overlap-cited 31 vs 20 of 50, discordant 14 / 3, exact McNemar p = 0.013 unadjusted (Holm 0.76 in Django's 60-test family).
  - The gap sits in the longest gold PRs. In length tertiles of 17 / 17 / 16 questions (371-1,026, 1,036-2,201 and 2,233-3,784 tokens), answered / overlap-cited is:

| Arm (4B, v3) | Tertile 1 | Tertile 2 | Tertile 3, longest |
|---|---|---|---|
| F0 | 10 / 10 | 11 / 9 | 14 / 12 |
| S0 | 13 / 10 | 9 / 6 | 10 / 4 |

**For the report (descriptive; the expected message checked against the numbers).** The message holds, with small-n caveats:
- When retrieval put the gold answer span in context (47 of 52), the 4B answered 42 and was strictly correct on 33. That is 70% of those questions, or 79% of its answers, on provisional labels.
- When it did not (5 questions), the model refused on 4 and answered 1 (`q1189`), wrongly. So with the evidence missing it mostly refused rather than hallucinated, but n = 5.
- The rank split says little: the gold MR was in the top 5 for 51 of 52.
- In Django, F0 had more overlap-cited answers than structural chunking (S0): 31 vs 20 of 50, p 0.013 unadjusted, Holm 0.76. The gap was mostly in the longest tertile (12 vs 4 of 16; counts only, no test).

## Blank correctness sheet (prepared, not labelled)
- **The sheet:** `results/baselines_blind_sheet_blank.csv` (+ `.xlsx`), 147 rows.
  - Every distinct answered (strict) answerable answer: F0 43, P0 52, CB 52. No answer text was shared between arms.
  - Citations are stripped, rows shuffled with seed 42, and columns are as the steering blind sheet.
- **The key:** `results/keys/baselines_blind_key.json`, git-ignored and not opened.
- **Rules:** `exp2_gitlab_A2000/LABELLING.txt`.
- Once labelled, P0's and CB's correctness can be compared with F0's.

## Limits
- **Labels are provisional:** James's 20 rows plus Codex's 67, not Alyssa's review, which is still due. The raters are mixed: James read the MR, but Codex's 67 had only the gold quotes. Correctness exists only for F0. P0's and CB's "answered" is not "correct".
- **The hallucination outcome is coarse.** "Unanswerable answered" counts invented reasons, premise rejections and one bold-formatted refusal alike (see the post-hoc reading in Task 1). Under the strictest reading, F0 vs P0 is 0 / 3 (p 0.25).
- **One seed (42), temperature 0.** The model was not perfectly repeatable between runs (q106 differed once, then matched). Ollama stayed at 0.40.4 with the same model digest throughout, so nothing changed there.
- **Low power on hallucination:** only 18 unanswerables. Two of them (`nr3177`, `nr4460`) have doubtful no_reason labels. Excluding them gives the same direction and Holm p.
- **The refusal regexes are imperfect.**
  - The fixed lenient regex misses free-form refusals ("doesn't mention", "I don't have information", and markdown such as "does **not** explain"). That inflates P0's and CB's answered counts and favours F0.
  - The broad sensitivity covers the plain cases, and the result vs P0 is marginal there (Holm p = 0.047; 0.094 if `nr3147` is read as a refusal).
  - The broad regex was written after F0's answers had been seen, though before any baseline answer existed.
  - The lenient regex also makes a few false refusals (P0 `q3958`).
  - Both audits are listed in full.
- **Long answers were cut off.** P0 and CB answers are long: 30/70 and 45/70 hit the copied 512-token output limit (`done_reason` "length"; upper-median length 467 and 512 tokens, against F0's 45). They were scored on what was generated. `possibly_truncated` only checks the input and is not evidence about this.
- **The gate measures citation support, not truth,** and it gates every uncited answer by rule.
- **Blinding:** up to 30 sheet rows keep `()`, empty backticks or `[]`. Some are code; some are residue of removed inline citations ("the original PR () states"), which hints that a context arm produced them.
- **Question checks:** the 70 questions were checked by Codex and DeepSeek passes plus James on some rows, not by both people as first planned (`HANDOVER.md`, "Question check provenance").
- **Pre-registration:** the rule was written by Claude Code during the unattended run. F0's answers had been seen before (they date from 6 Nov). P0's and CB's had not when the rule was committed.

## Provenance
- **Commits on `exp2-baselines`:**
  - rule `f33ead5`, then the revised rule `da8e9d8`;
  - 10-question check `79688e3`;
  - Task 3 `6a3833b`;
  - P0 `8668f0e`, CB `f0cf8e5`, F0 re-run `0ee8efd`;
  - Task 1 `c62bf07`;
  - sheet `d0630cd`;
  - gate `191c070`.
- **Script:** `exp2_gitlab_baselines.py`.
- **Advisor checks:**
  - Check 1 found one problem (the regex missing refusals), fixed with the broad sensitivity before generation, plus five minor items, all fixed.
  - Check 2 recounted every count, b / c and p value from the raw files with its own script: MATCH.
  - Check 3 reviewed this report and found two problems:
    - `nr3147` is a refusal hidden by bold text, so the broad-regex significance is marginal;
    - the figure overclaimed.
  - It also found seven minor wording and completeness items. All are fixed in this version and listed in `results/RUN_LOG.md`.
- **Figure:** `results/baselines_tradeoff.png`. It shows lenient counts as percentages with n/18 and n/52 labels, in the colours of `steering_tradeoff.svg`, which exists only as an SVG.

## Correctness (secondary)
Secondary, single labeller (Clifton), unadjusted. Clifton labelled all 147 blind answers (final 12 Nov 2026, committed in `e56c1f9` before the key was opened). Out of the 52 answerables per arm; an answer not on the sheet (not answered under strict) counts as not correct. Strict correct = `correct`; lenient correct = `correct` + `partial`. Files: `results/baselines_correctness.csv`, `results/baselines_correctness.md`.

| Arm | Answered (strict) /52 | Strict correct /52 | Lenient correct /52 | Wrong | Not answered |
|---|---|---|---|---|---|
| F0 | 43 | 30 | 42 | 1 | 9 |
| P0 | 52 | 30 | 47 | 5 | 0 |
| CB | 52 | 0 | 3 | 49 | 0 |
| F0_rerun (check) | 43 | 30 | 42 | 1 | 9 |

Exact McNemar, two-sided, unadjusted (b = correct for F0 only, c = correct for the other arm only):

| Comparison | Scoring | b | c | p |
|---|---|---|---|---|
| F0 vs P0 | strict | 4 | 4 | 1.0 |
| F0 vs P0 | lenient | 1 | 6 | 0.125 |
| F0 vs CB | strict | 30 | 0 | 1.9e-09 |
| F0 vs CB | lenient | 40 | 1 | 3.8e-11 |

- F0_rerun has the same label as F0 on all 52 answerables.
- Answered counts equal `results/baselines_counts.csv` for every arm.
- F0's old provisional labels gave strict 33/52 and lenient 40/52; Clifton's give 30/52 and 42/52. Same label on 32 of 43 answers; Cohen's kappa 0.39 (3 labels), 0.59 (strict correct vs not).
- An independent recount (general-purpose agent, its own standard-library script, given only the file paths) matched every per-arm count, every b / c and every p.

**Plain reading.** On the 52 answerable questions, plain RAG (P0) is as often fully correct as the grounded prompt (F0), 30 each, and is correct or partly correct more often (47 against 42), but that difference is small and not significant (6 against 1 discordant questions, p = 0.125). P0 gets there by answering every question, while F0 declines 9. Closed book (CB) almost never gets an answer right (0 strict, 3 lenient), so correct answers here depend on the retrieved context. On these labels the grounded prompt does not give more correct answers on answerable questions; any advantage it has would come from Task 1 (answering fewer unanswerable questions), which is itself marginal once refusals the regex missed are read by hand. These are one person's labels on an exploratory set, and the old and new F0 labels agree only moderately, so the strict counts may shift by a few with a second labeller.
