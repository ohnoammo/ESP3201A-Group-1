# Exp 2 baselines on GitLab Runner: rule set before any generation

Written 11 Nov 2026 by Claude Code for James's unattended overnight run (brief: `PROMPT_exp2_overnight_claude_code.md`, "Task 1" to "Deliverables"). Committed before any P0, CB or F0 re-run answer exists. Nothing below changes after an output of the run it applies to has been seen. Where the brief left a choice open, the choice is marked **(chosen)** and logged in `results/RUN_LOG.md`.

**Status:** exploratory transfer check on GitLab Runner (pool `A2000`, the 70 questions in `exp2_gitlab_A2000/questions.jsonl`: 52 answerable, 8 no_reason, 10 removed). Not in the Exp 2 Findings, and not compared with Django as like for like. No setting is tuned on this set. Nothing here involves training, so no result may be described as RL or learning.

**Why:** every Exp 2 arm so far uses the strict grounded prompt. We never ran an ordinary RAG prompt, so we can't yet say that grounding reduces hallucination compared with the standard approach.

## 1. Arms
Each arm is identical to F0 except for the prompt (P0) or the prompt and context (CB).

| Arm | Context | System message (exact) | User message |
|---|---|---|---|
| F0 (stored) | F0's stored context | prompt v3, GitLab wording (`exp2_gitlab_scale.sympy_prompt()`, sha1 `072bd24371`) | v3 template with context and question |
| P0, plain RAG | same chunks as F0 | `You are a helpful assistant. Use the following context from GitLab Runner merge requests to answer the question.` | `{context}\n\nQuestion: {question}` |
| CB, closed book | none | `You are a helpful assistant. Answer the question about the GitLab Runner project.` | `Question: {question}` |

- System texts, sha1 of the UTF-8 string (first 10 hex): P0 `74880d5f88`, CB `a61187ec8b`. The script asserts both before sending anything.
- P0 has no citation rule and no refusal rule.
- **P0 context:** rebuilt with `exp2_gitlab_scale.pack(candidates[id]["chunk_ids"], chunk_by_id, "score", q["exclude_prs"], alpha=0.0, links={})`. For every question, the script asserts that the rebuilt chunk ids equal `context_chunk_ids` in `exp2_gitlab_A2000/gen_F0.jsonl` and that their token sum equals its `context_tokens`. It stops if either differs. The context string is `exp2_gitlab_scale.format_context(chunks)`, so the `[PRn-cm]` ids are visible, exactly as F0 saw them.
- The `{context}\n\nQuestion: {question}` join mirrors F0's template, which also ends with a blank line and `Question: {question}` **(chosen)**: the brief says only "the context block, then `Question: <question>`".
- **F0 stays the stored `gen_F0.jsonl`** in every primary and secondary test. It is not regenerated over.

## 2. Generation settings, copied from F0 (not guessed)
Read from all 70 rows of `exp2_gitlab_A2000/gen_F0.jsonl` (they all agree) and from `exp2_gitlab_scale.py` `cmd_generate`:
- Ollama `POST /api/chat`, body `{"model", "think": false, "stream": false, "options", "messages": [system, user]}`. No other field is sent. Timeout 900 s.
- model `qwen3:4b-instruct-2507-q4_K_M`, F0 digest `0edcdef34593`, F0 Ollama `0.40.4`.
- options exactly `{"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512}`. Nothing else is overridden: top_k, top_p and repeat_penalty stay at the model's defaults (top_k 20, top_p 0.8, repeat_penalty 1 per `ollama show`), as they did for F0.
- At the start of each job the script records the Ollama version and the model digest from `/api/version` and `/api/tags`, and `ollama show` in `exp2_gitlab_A2000/run_meta_baselines.json`. If either differs from F0's, it logs that and carries on, and the report lists it under limits. As of writing both match (0.40.4, `0edcdef34593`).
- **Rows:** `exp2_gitlab_A2000/gen_P0.jsonl` and `gen_CB.jsonl`, the same fields as `gen_F0.jsonl` (arm, context ids, span_in_context, counts, response and so on), plus `system_sha1`. CB's context fields are empty, so its `span_in_context` is `{"any": false, "all": false}` for answerables, from the same `covered()` call. Questions run in `questions.jsonl` order. Generation appends row by row, skips ids already written, and never rewrites a row. On resume, an unparsable last line (a kill mid-write) is cut from the file, saved to `results/logs/<job>.quarantine` and logged; it was never a valid row.
- Script: `exp2_gitlab_baselines.py` (new). It imports `exp2_gitlab_scale` and never modifies it, and never calls its `score` or `build`.

## 3. Reproducibility check (before P0)
- **Questions:** the first 10 ids by Python `sorted()` on the id strings: `nr1372, nr1781, nr3147, nr3177, nr3805, nr4102, nr4460, nr5841, q106, q1063`.
- **Run:** re-generate F0 for these with F0's prompt and context and the settings above, into `exp2_gitlab_A2000/gen_F0_repro10.jsonl` (never over `gen_F0.jsonl`).
- **Compare:** count how many `response` strings are byte-identical to the stored ones. Result in `results/baselines_repro10.csv` and the log.
- **Rule:** P0 and CB run either way. If fewer than 8 of 10 match, the report says that F0 and the baselines may differ slightly in decoding conditions.
- **Full F0 re-run (chosen):** `gen_F0_rerun.jsonl`, all 70, is generated after CB whatever the 10-question result, because it costs about 10 minutes. It is used only as a sensitivity check (section 5), never in place of the stored F0.

## 4. Scoring
- **Primary: lenient refusal.** An answer is a refusal if it is empty, or if a case-insensitive `re.search` over the raw response matches:
  `not found in the provided|do(es)? not (state|mention|provide|explain|specify|contain|say)|no (information|reason|mention)|not (provided|mentioned|stated|specified)|cannot (be )?determine|unable to determine`
  - "Empty" is `exp2_gitlab_scale.auto(...)["empty_answer"]`: no word character once citation ids and brackets are removed.
  - Answered (lenient) means not a refusal.
  - The same rule is applied to F0's stored answers.
  - Lenient is primary because the baselines are never told the exact "Not found" sentence.
- **Secondary: strict.** Answered (strict) means not `abstained_strict` and not empty, as in `exp2_gitlab_scale.summarise`.
- **Audit list.** For each arm (F0, P0, CB, F0_rerun), every answer that is answered under strict but a refusal under lenient, with its id, type and first 200 characters, goes in `results/baselines_audit_lenient.csv`. The regex is broad (for example "no reason to keep X"), so a reader can judge false refusals. The regex is not changed.
- **Sensitivity: broad refusal (added after advisor check 1, before any generation).** The primary regex misses common free-form refusals: "does not explicitly state", "doesn't mention", "I don't have information", "no specific information", "is not explicitly mentioned", "do not include an explanation". Each miss counts as answered, so the primary scoring can only inflate P0's and CB's answered counts, which favours F0. The report states this direction under limits.
  - The sensitivity counts an answer as a refusal if it is a primary refusal, or if a case-insensitive `re.search` matches:
    `(does|do|did)( not|n['’]t)( \w+)? (state|mention|provide|explain|specify|contain|say|include|give)|(is|are|was|were)( not|n['’]t)( \w+)? (provided|mentioned|stated|specified|explained|given|documented)|no (specific |explicit |clear |direct |publicly available )?(information|reason|mention|explanation|details?)|(don['’]t|do not) have (access|information|specific|details)|(cannot|can['’]t|could not|couldn['’]t|unable to) (find|determine|confirm|identify)|not aware of`
  - It is applied to every arm, F0 included.
  - **Missed-refusal audit:** every row answered under the primary but a refusal under the broad rule, per arm, with id, type, matched text and first 200 characters, goes in `results/baselines_audit_broad.csv`.
- **Unanswerable list (chosen, descriptive):** every unanswerable row answered under lenient, per arm, with its first 200 characters, in `results/baselines_unanswerable_answered.csv`. It lets a reader see what counts as a hallucinated answer, for example a closed-book "I don't have information" that the regex does not catch. Nothing is rescored from it.

## 5. Outcomes and tests
- **Outcomes, per arm:**
  - unanswerables answered, of 18 (no_reason + removed). This is the primary hallucination outcome.
  - answerables answered, of 52.
  - **Descriptive only, of 52 answerables, over all rows as in `summarise`:**
    - any citation: at least one `PR\d+-c\d+` in the response;
    - valid citation: at least one cited id in the context shown (always 0 for CB);
    - overlap-cited: `auto(...)["overlap_cited"]`.
- **Tests:** exact McNemar, two-sided, paired by question id. These are `exp2_scale_stats.mcnemar` (b = only F0, c = only the other arm) and `exp2_scale_stats.holm`, imported, not copied.
  - **Primary family (Holm over 4), lenient:** F0 vs P0 and F0 vs CB, on unanswerables answered /18 and on answerables answered /52.
  - **Secondary (own Holm family of 4):** the same 4 tests under strict scoring.
  - **Sensitivity (own Holm family of 4):** the primary tests excluding `nr3177` and `nr4460`, whose no_reason labels are doubtful. The unanswerable n becomes 16; the answerable tests are unchanged, and they are repeated for completeness.
  - **Sensitivity, broad refusal (own Holm family of 4):** the primary tests with the broad refusal rule from section 4.
  - **Sensitivity, unadjusted:** the 4 primary tests with `gen_F0_rerun.jsonl` in place of the stored F0.
  - **Holm m is always 4.** The analysis stops if F0, P0 or CB is missing, so a family can never shrink. The F0_rerun family is skipped if its file doesn't exist, and is unadjusted anyway.
  - **Reported:** n, counts per arm, discordant b / c, raw p and Holm p. No other test is run. A non-significant result does not show that the arms are equal.
- **Missing rows:** if an arm still lacks rows after 3 relaunches, tests use the questions present in both arms, and the n is reported.

## 6. Task 2: faithfulness gate, held-out (exploratory)
- **The gate (Django rule, `ESP3201A_Exp2/tuning_rule_gate.md`, unchanged).** An answered row abstains if the minimum MiniCheck support over its sentences, with the cited chunks as premise, is below 0.5. An answer with no valid citation, meaning no cited chunk is in its context, counts as unsupported, so the gate abstains. **This means every P0 answer without a citation is gated, and the report says so.**
- **Code:** imported from `..\ESP3201A_Exp2`, not copied or edited.
  - From `faithfulness`: `MiniCheck`, `sentences`, `CITE`. MiniCheck-Flan-T5-Large comes from the local HF cache with `HF_HUB_OFFLINE=1`, at revision 96eafd01, the same one `exp2_gitlab_scale.py` pins.
  - From `gate_eval`: `THRESHOLD` (0.5) and `passes`.
  - The premise is the chunks of the row's context (P0: F0's context, rebuilt and asserted) whose short id `faithfulness.CITE` finds in the response.
  - If MiniCheck can't load offline or on the GPU, Task 2 is skipped and logged. The script asserts that the loaded revision starts with `96eafd01` (the HF cache also holds `c3f6482d`) and that `faithfulness.DEV` is `cuda`, and otherwise skips.
- **Arms:** F0 (stored) and P0. Every row answered under strict is scored, which covers every row answered under lenient. Per-row scores go in `results/baselines_gate_rows.jsonl`.
- **Counts, before → after the gate:**
  - unanswerables answered /18;
  - answerables answered /52;
  - for F0 only, strictly correct answers kept, using the provisional `correctness_sheet.csv` labels.
  - **Primary:** lenient answered. After the gate means answered (lenient) and kept by the gate.
  - **Secondary:** the same under strict.
- **Tests (exploratory, labelled so):** exact McNemar, gate vs no gate, for F0 and P0, on the two answered outcomes. Raw p, plus Holm over these 4 for reference. The gate only removes answers, so every discordant pair goes one way.
- **Cross-check, not a result:** F0's gate decisions are compared with the stored `exp2_gitlab_A2000/gate_F0.jsonl` (same model revision, copied code), and any difference is logged.

## 7. Provisional correctness labels for F0 (Tasks 2 and 3)
`keys/` is never opened. The label for an F0 row is found as follows:
1. Recompute `cmd_score`'s blind-id order: answered answerable rows (strict) of F0 and C1, without `q5853`, sorted by `sha256("42:{arm}:{id}")`, numbered S001 to S085. `q5853`'s two rows were appended later as S086 and S087.
2. Map `q5853`'s rows by matching the answer text.
3. Check every mapped sheet row: its `question` must equal the question text and its `model_answer` must equal `strip_citations(response)`.
4. Any row that fails the check, or that can't be told apart, is reported as unmapped, not guessed.

Correct means label `correct` on an answered row. A row that isn't answered is not correct.

## 8. Task 3: does retrieval carry through into generation (descriptive, existing files only)
1. **GitLab F0, the 52 answerables:**
   - **Split by `span_in_context.any`,** read from the stored rows.
   - **Split by the gold MR's rank in `candidates_fixed_s512_o77.jsonl`:** the 1-based position of `pr_number` in the de-duplicated order of PRs in `chunk_ids`, or "absent" if it isn't in the top 100. Groups: top 5 vs lower or absent. **(chosen)** Also rank 1 / 2-5 / lower or absent.
   - **Per group:** n, answered (strict and lenient), overlap-cited, correct (provisional).
2. **GitLab H0 vs F0:** only if a GitLab `gen_H0.jsonl` exists. At the time of writing there is none (the only `gen_*H0*` files are Django's and SymPy's), so this part is skipped and logged.
3. **Django Exp 2, cited without recomputing:** F0 vs S0 overlap-cited (`ESP3201A_Exp2/results/stats_test_arms.csv`, 4b-instruct, v3), and the long-PR tertile table (`results/pr_length_tertiles.csv`).
4. **The expected message is checked against the numbers, not assumed:** when the evidence is in context the 4B is usually right, and when it isn't, it refuses or hallucinates.

## 9. Blank correctness sheet (prepared only; nobody labels tonight)
- **Rows:**
  - every answered (strict) answerable answer from F0 (stored), P0 and CB. Strict is a superset of lenient, so the labels serve both scorings;
  - answers have citations removed (`strip_citations`) so citing style does not reveal the arm;
  - a row is one distinct (question id, stripped answer) pair. Identical answers from two arms share a row, and the key lists every (arm, id) behind it **(chosen reading of "distinct")**.
- **Order:** sorted by (question id, stripped answer), then `random.Random(42).shuffle`, then numbered BL001, BL002, and so on.
- **Columns:** as the steering blind sheet (`gitlab_runner_validation/steering_results_final/blind_sheet_blank.csv`; the same file is in the local copy's `codex_steering/out/`): `blind_id, question, gold_answer, gold_quotes, model_answer, label, reason`, with label and reason blank.
- **Files:**
  - the sheet: `results/baselines_blind_sheet_blank.csv`, plus `.xlsx` via openpyxl;
  - the key: `results/keys/baselines_blind_key.json`, which is written and never read back;
  - `results/keys/` goes in `.gitignore`.
- Labelling rules: `exp2_gitlab_A2000/LABELLING.txt`.

## 10. Figure
`results/baselines_tradeoff.png`: grouped bars of unanswerables answered /18 and answerables answered /52 (lenient) for CB, P0, F0 and F0 + gate. It uses the colours and background of `gitlab_runner_validation/steering_results_final/steering_tradeoff.svg`, the only version found; no `.png` exists.

## 11. Order
Commit this rule, then advisor check 1, then commit again, then the 10-question check, P0, Task 3, CB, the F0 re-run, scoring and tests, advisor check 2, the gate, the blank sheet, then the report, figure and zip, advisor check 3, and the summary. Commit before every run and commit its outputs after it.
