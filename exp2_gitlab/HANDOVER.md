# HANDOVER: GitLab Runner validation (updated 6 Nov 2026)

Tests the Django-chosen setting on `gitlab-org/gitlab-runner` merge requests. Exploratory; not in the Exp 2 Findings. Owner: James. Follow the reporting and hard rules in `ESP3201A_Exp2/HANDOVER.md`.

## Where things are
- **Work here:** `C:/Users/kwekt/ESP3201A_local/gitlab_runner_copy` (outside OneDrive; git branch `gitlab-runner-pilot`). Has the MR data, chunks, embeddings and answer key.
- **Snapshot only:** `ESP3201A/gitlab_runner_validation` in OneDrive: code, sheets and results, without bulky data or the key. It goes stale, so re-copy after each result. Don't run from it.
- "gitlab runner" means this repo, not a CI runner. The project has no CI config.

## Done
Pool `A2000` downloaded (`STEP 1B DONE`, 22:38 on 5 Nov) and scaled Exp 1 run at `db14bf1`; both stats commands run. Results are in the table below and `results/exp1_gitlab_A2000_stats.txt`. Pilot Exp 2 is reported. Scaled Exp 2 has run through stats, gate and report on provisional labels (see "Scaled Exp 2 results").

## Next
1. **Pilot Exp 2 report:** done. `exp2_gitlab/report.csv` (written 00:31 on 6 Nov) is in the pilot table below. Answered sheets are in `gitlab_runner_validation/exp2_gitlab/Answered_csvs` in OneDrive, reconciled in `exp2_gitlab/correctness_sheet_reconciled.csv` (see "Correctness sheet reconciliation") and copied into `exp2_gitlab/correctness_sheet.csv`. Don't open `exp2_gitlab/keys/`.
2. **Scaling Exp 2:** `tuning_rule_exp2_scale.md` signed off by James, 6 Nov. Follow its order. Task brief: `PROMPT_EXP2_SCALE.md`. Code is `make_exp2_gitlab_scale.py` -> `exp2_gitlab_scale.py`, stats `exp2_scale_stats.py`, output folder `exp2_gitlab_A2000/`. Done on 6 Nov: retrieve (3fe9b45), generate (64ee8c8) and score for F0 and C1. The set then moved to 52 answerable, 8 no_reason, 10 removed (6a838db). Hit@5 51/52 (miss: `q3137`), MRR@5 0.896, computed from the candidates file; the script itself prints only the top-5 count. `summary.csv` holds the automatic counts. **Next: Alyssa's full review; see "Labelling state". Everything from this run is provisional until then.** Still without a recorded person's read: `q3137`, `q589`.

## Labelling state (6 Nov): provisional
- **The signed rule didn't happen.** "Alyssa labels every row, hers are final" was not done (85 rows in the rule's estimate, 87 now with `q5853`). Today's labels are James's on the fixed 20 rows, resolved after a Codex disagreement check, plus Codex's on the other 67.
- **The 20 rows:** James and Codex agreed on 10 and disagreed on 10 (`correctness_disagreements_james_codex.csv`). The resolutions changed James's label on 5 (S060, S047, S070, S082, S013) and kept it on 5 (S048, S022, S038, S030, S049).
- **The 67 rows:** `correctness_sheet_codex_67.csv`. Codex got only these rows and `LABELLING.txt`, pasted into its prompt with no tools used, because its file commands were blocked by policy. It saw no arm information, and it couldn't see the MR beyond the gold quotes. So unlike its earlier run on the 20 rows, it can't catch extra detail that contradicts the rest of the MR, which is what made S013 wrong.
- **Alyssa's review is still the correct step** and should happen when she's free. If her labels differ meaningfully from these, re-run `stats` on her labels before anything from this run is treated as final. Give her `correctness_sheet_blank.csv` and `LABELLING.txt` only: `correctness_sheet.csv`, `correctness_sheet_james.csv`, `correctness_sheet_codex.csv` and `correctness_sheet_codex_67.csv` show others' labels, and `gen_F0.jsonl` and `gen_C1.jsonl` name the arm beside each answer.
- **Code:** `exp2_scale_stats.py` now reads `correctness_sheet.csv` as `FINAL`, and its agreement line compares James's and Codex's original sheets on the 20 rows, since `FINAL` holds James's labels there. For her labels, point `FINAL` at her file.

## Scaled Exp 2 results (6 Nov, at cc0bd30): provisional, pool A2000, 4B, prompt v3
Exploratory, on the labels above. Exact McNemar, F0 vs C1, two-sided. Holm is over the first three; lenient is a sensitivity, unadjusted. These tests can't show the arms are equal.

| Outcome | n | F0 | C1 | Only F0 / only C1 | p | Holm |
|---|---|---|---|---|---|---|
| Strict correct (primary) | 52 | 33 | 32 | 5 / 4 | 1.0 | 1.0 |
| Answered | 52 | 43 | 44 | 0 / 1 | 1.0 | 1.0 |
| Unanswerable answered | 18 | 5 | 3 | 2 / 0 | 0.5 | 1.0 |
| Lenient correct (correct + partial) | 52 | 40 | 41 | 1 / 2 | 1.0 | n/a |

| Report and gate, counts only | F0 | C1 |
|---|---|---|
| Correct / partial / wrong, of answered | 33 / 7 / 3 of 43 | 32 / 9 / 3 of 44 |
| Answered after the gate | 42 | 37 |
| Correct after the gate | 32 | 27 |
| Unanswerable answered after the gate | 2 | 1 |

Problems with these results:
- **Raters are mixed within pairs.** Both arms answered 43 questions: 27 have both rows labelled by Codex, 4 by James, and 12 have one of each. 6 of the 9 strict discordant questions are in those 12, split 3 / 3 by arm, so they may reflect who labelled rather than the arm. Among the 27 Codex-only questions it is 2 / 1. With Codex's own labels on all 87 rows (a one-off check, not saved; its 20 had MR access, its 67 didn't): strict correct 36 vs 33, 5 / 2, p 0.453; lenient 41 vs 41, 1 / 1, p 1.0.
- **The raters agree poorly.** James vs Codex before resolving: 10 of 20 equal, kappa 0.177. Codex marked 56 of its 67 rows correct, while James marked 6 of the 20 correct, on a different sample.
- **Identical answers, different labels:** S048 (wrong) and S081 (partial) are the same text for the same question. It makes one of the 3 lenient discordant questions; strict is unaffected and lenient's p stays 1.0 if they're aligned. Left as resolved.
- **The gate removes more from C1:** 7 of its answered answerable rows (5 correct, 2 partial) against 1 of F0's (correct). Cause not checked. No answer lacked a score, and every context matched the stored one.

Reading `report.csv`: `gated_answered`, `gated_correct` and `gated_unanswerable_answered` count what is left after the gate, not what it removed. For example, F0 has 5 unanswerable answered, 3 of them gated (`rm3846`, `nr3177`, `nr3805`), so the column says 2. `removed` rows are included. For how the questions were checked, see "Question check provenance".

**What "corrected" meant for the hold:** all 15 questions are resolved: the 13 marked ok count as corrected as written (`nr188` included), `nr7461` stays `no_reason` as written, and `rm5982`'s question is reworded. James said on 6 Nov to start on Exp 2, read as lifting the hold.

## Correctness sheet reconciliation (James, 5 Nov, before any report)
Made by `reconcile_correctness.py`; every action is in `exp2_gitlab/correctness_reconciliation_audit.csv`. The answered sheets are unchanged. Inputs: `correctness_sheet_james.csv` (edited 23:17 on 5 Nov, SHA-256 671aef35...1fef5) and `correctness_sheet_alyssa (2).csv` (SHA-256 82932565...f7d41). Result: 17 of 17 rows counted: correct 14, partial 2, wrong 1. Rows are keyed by question id + blind id, because 7 questions have two rows. Question ids come from `questions.jsonl` by exact question text.

| Action | Row | Change | Why |
|---|---|---|---|
| Filled | S005 (q4085) | `-` -> correct | James gave no label; Alyssa's is used. Same text as S004, but kept: S004 and S005 are q4085's two arms giving the same answer, and `report` looks labels up by arm |
| Overwritten | S010 (q5089) | wrong -> partial | The two labels disagree; Alyssa is the reference rater |
| Filled | S009 (q6045) | `-` -> correct | James gave no label; Alyssa's is used |
| Filled | S011 (q5089) | `-` -> partial | James gave no label; Alyssa's is used |
| Filled | S015 (q5540) | `-` -> correct | James gave no label; Alyssa's is used |
| Resolved | nr188 | Record row with no label, status `resolved-no-reason`; both people's `ok` left as is | Stays `no_reason` after the full MR was read (see "Open items on the questions") |

- **No rows dropped:** S009, S011 and S015 are the same question as S003, S010 and S002, but with different model answers. S016 and S017 were labelled by James, so they aren't changed.
- **Copied for `report`:** `label` from `correctness_sheet_reconciled.csv` (Alyssa's labels) and Alyssa's `reason` were copied into `exp2_gitlab/correctness_sheet.csv` by `reconcile_correctness.py`. Only those two columns changed, and the nr188 record row was not copied. `report` needs a `blind_id` and `label` per row and maps `blind_id` to `{"arm", "id"}` through `keys/sheet_key.json`; that format was confirmed from the code in `exp2_gitlab.py`, without opening the file.
- **nr188 in `report`:** it has no correctness row (it is a `no_reason` question), so correctness counts are unaffected. It rightly counts in unanswerable answered. That total stays 2/5 in each arm: `nr188` and `nr7461`, both `no_reason`. `report` is not modified.
- **Known limitation:** `report` has no concept of excluded or flagged rows; it only checks whether the model abstained. Any future exclusion would be audit-only and wouldn't change its output.

## Scaled Exp 1 results (pool A2000: 231 tasks + 2,000 distractors)
Rule: `tuning_rule_exp1_scale.md`. Permutation is primary. Labels are closing references, so not like for like with Django. Holm is within each test's family of 4; `gold_in_budget` uses exact McNemar in both.

| Set | Alpha 0 -> 1 | Value | Permutation p / Holm | Wilcoxon p / Holm |
|---|---|---|---|---|
| Primary, 201 tasks not in the pilot | Correct MR in budget | 167 -> 155; lost 12, gained 0 | 0.0005 / 0.0020 | 0.0005 / 0.0020 |
| | Budget recall | 0.453 -> 0.480 | 0.1653 / 0.1653 | 0.0218 / 0.0218 |
| | Budget precision | 0.072 -> 0.088 | 0.0108 / 0.0216 | 0.0011 / 0.0032 |
| | Budget F1 | 0.089 -> 0.110 | 0.0012 / 0.0036 | 0.0011 / 0.0032 |
| Sensitivity, all 231 tasks | Correct MR in budget | 191 -> 177; lost 14, gained 0 | 0.0001 / 0.0005 | 0.0001 / 0.0005 |
| | Budget recall | 0.430 -> 0.463 | 0.0571 / 0.0571 | 0.0028 / 0.0028 |
| | Budget precision | 0.072 -> 0.088 | 0.0067 / 0.0134 | 0.0003 / 0.0006 |
| | Budget F1 | 0.086 -> 0.108 | 0.0004 / 0.0012 | 0.0001 / 0.0005 |

Hit@5 and MRR@5 are the same at both alphas: primary 169/201, 0.722; all 193/231, 0.717. Median differences for recall, precision and F1 are 0. All 14 lost MRs ranked 3 to 5. Issues sharing a 10-word run with their MR: 75 of 201 primary (Hit@5 72/75, against 97/126 without; descriptive only), 85 of 231 overall.

Checks passed: every saved MR has comments, and none with notes on GitLab was saved with none (18 MRs hold fewer notes than GitLab's count, largest 66 of 76; cause not checked). The 12 skipped "issue not public" are the only 404s of the 40 skipped candidates without a token. Pilot chunks rebuilt from today's files match the cache exactly. No pilot task's MRR rose in the bigger pool. Permutation p values hold under two other seeds.

Noted, not changed: at least 514 chunks (of the 14,904 newly embedded; cached ones aren't counted) and 29 of 231 queries were over the embedder's 1,024 tokens and truncated. 3 task MRs (2492, 3005, 6784) name another task's issue, because the same-ticket filter only covers distractors.

## Pilot results (300 MRs: 30 tasks + 270 distractors)
Labels: an MR's closing reference to an earlier public issue, not SWE-bench, so not like for like with Django.

| Exp 1, alpha 0 -> 1 | Value | Permutation p / Holm | Wilcoxon p / Holm |
|---|---|---|---|
| Correct MR in budget (McNemar for both) | 27 -> 26 of 30 | 1.0000 / 1.0000 | 1.0000 / 1.0000 |
| Budget recall | 0.442 -> 0.457 | 0.7649 / 1.0000 | 0.0507 / 0.1013 |
| Budget precision | 0.104 -> 0.143 | 0.0346 / 0.1384 | 0.0073 / 0.0292 |
| Budget F1 | 0.102 -> 0.129 | 0.1468 / 0.4404 | 0.0120 / 0.0359 |

Hit@5 27/30 and MRR@5 0.828 at both alphas (links don't change the ranking). 10 of 30 issues share a 10-word run with their MR. These tests were chosen after seeing the pilot, so they only suggest what to test at scale.

| Exp 2, 4B, prompt v3 | F0 (no links) | C1 (fixed 512/77, links alpha 1) |
|---|---|---|
| Answer quote in context | 10/10 | 8/10 |
| Answered | 9/10 | 8/10 |
| Cited the chunk holding the answer | 7/10 | 6/10 |
| Refused with quote in context | 1 | 1 |
| Unanswerable answered, as scored | 2/5 | 2/5 |
| Correct / partial / wrong, of answered (Alyssa's labels) | 8 / 1 / 0 of 9 | 6 / 1 / 1 of 8 |

Counts only, no tests, 10 answerable questions. MiniCheck gate not run. Questions are Claude's, checked by James and Alyssa on the question sheets; the correct MR was in the top 5 for all 10 answerable ones.

## Open items on the questions
- `nr188` (resolved, James, 6 Nov; full MR read): stays `no_reason` / unanswerable. The 94% comment is dated well after the MR opened and explicitly says "Sorry to revive an old thread" before proposing further optimisations on top of `GIT_DEPTH`, which already existed by then. It explains why the feature is useful in hindsight, not the problem that prompted adding it. The MR's opening description states only the feature, no motivating problem. The model's answer (which uses the 94% figure) is an unsupported answer, not a correct one, because it answers a different question than the one asked. It stays counted in unanswerable answered.
- `nr7461` (resolved, James, 6 Nov; flagged comment read in full): stays `no_reason`. The comment both people flagged is GitLabDuo's review note, a bot note the model never saw because bot notes are left out of the documents. It describes the CODEOWNERS pattern's mechanics and says the description flags the `!` line as an open design question, "a decision for humans, not a code defect". Nothing states why a negated pattern was chosen. That flag is not in the saved or live description (checked 6 Nov); the description's Background says why ownership should change (a template wording change needs approval from the `*` rule owners), not why the pattern is negated. Both arms' answers stay counted in unanswerable answered.
- `rm5982` (resolved, James, 6 Nov): the gold answer is accurate. The MR's "What does this MR do?" section says the hard-coded username made the tests impossible to run locally without a CI job token. The mismatch was the question, which asked about the mechanism. Reworded to "Why did the hard-coded username in the shell integration tests need to change?"; type stays `removed`. Its pilot retrieval and answers (`candidates_fixed_s512_o77.jsonl`, `gen_F0.jsonl`, `gen_C1.jsonl`) come from the old wording and were not regenerated. Both arms refused, so scored counts don't change.
- Question sheets answered 5 Nov. Both people marked `rm5982` and `nr7461` fix (both since resolved, above); the other 13 ok, including `nr188`.
- Correctness sheets: as of James's 23:17 edit, James and Alyssa agree on 12 of 17; they differ on S010 (wrong / partial), and James left 4 as `-` (S005, S009, S011, S015). See "Correctness sheet reconciliation".

## Second automated check (Codex), reconciled 6 Nov
Codex read all 70 MRs, flagged 2 for correction and made 3 other notes. Only the items below were applied, after a cross-check against James's and Alyssa's manual reads. Nothing was retrieved or generated.

| Item | Status | What was done or found |
|---|---|---|
| `q2913` | Done: stays as written; Codex's "drop" rejected | The gold quote exists as given: Jamesits, the MR's author, posted it on 7 Oct 2022 during active review. James read it on the MR, and it is also in the saved MR data. Codex likely can't see GitLab's JS-rendered comment threads. Note added to its sheet row; `check` still blank. |
| `nr6848`, now `q6848` | Settled: `check=ok`; sheet row synced | Reclassified from `no_reason` to `answerable` in `questions_src.json` and `questions.jsonl`. The description states the reason, in the sentence routing the result through `normalizeExitError`, "mirroring the concrete run path". Its sheet row now matches `questions.jsonl` (id, type, question, answer, quote) and its note records the reclassification. |
| `q3239` / `q3408` | Settled, 6 Nov: both kept; see the caveat under this table | Duplicate-rationale pair, found by Codex and independently by a direct MR read. Both give nearly the same reason: a small doc edit to trigger a lint-image CI job and verify the new image works. A judgement call, not a correctness bug: two MRs can share an engineering pattern. **Correction:** the writing session's doubt list called this pair "q3408 and rm3239", but the entry at MR 3239 is typed `answerable` (`q3239`). There is no `rm3239` in the 70. |
| `nr1372` | Settled: stays `no_reason`, `check=ok`; rewording still an option | Not simply wrong. The description does state a reason, but for a different question: why the deprecated clone/fetch fallback was removed (newer GitLab instances send refspec, and 12.0 allows breaking changes). The question asks why `gitlab-runner exec` doesn't send refspec, which is structural to `exec` running without a GitLab server and isn't explained by this MR. Its sheet row's `note` gives the same explanation. |

**Descriptive caveat only, no action taken:** two of the 51 answerable questions (`q3239`, `q3408`) share a similar underlying rationale pattern (a small doc edit to trigger a CI job exercising a new lint image); both are kept because they are independently verified, separate MRs, not a data error, and swapping one out would be an undisciplined post-hoc filter with no principled stopping point.

**The other no_reason rows, James's verdicts, 6 Nov (after generation; all `check=ok`):**

| Row | Verdict | What was found |
|---|---|---|
| `nr3177` | Stays `no_reason` | A maintainer's comment approves deleting the files but doesn't explain why they were left there |
| `nr1781` | Stays `no_reason` | The reason is on Docker's docs page, linked and not quoted, so the model never sees it |
| `nr3805` | Stays `no_reason` | The reason is only a pointer to an external GitLab blueprint, never reproduced in the MR |
| `nr5841` | Stays `no_reason` | "Simplify a mock server" confirms one exists but doesn't say why it was relied on |
| `nr3147` | Stays `no_reason` | The stated motivation covers the broader library upgrade, not the @-prefix design choice |
| `nr4460` | Stays `no_reason` | It points at a function to look up and doesn't state the reason in text |
| `nr4102` | Stays `no_reason` | It explains why the longer backoff was added, not why the 1s-5s cap existed; same shape as `nr1372` |
| `nr5853`, now `q5853` | Reclassified to `answerable` | Quote from the description's Why section; gold answer "To follow GitLab's broader move from asdf to mise for developer tooling." |

**`q5853`, answers reused:** retrieval uses only the question text and `exclude_prs`, and generation adds the context; neither uses the type, and neither input changed. Re-run on 6 Nov: candidates and both arms' contexts are identical. F0's answer came back identical, but C1's came back reworded although the prompt was the same size (3,020 tokens) and it then repeated stably, so the model isn't fully reproducible between runs (cause not checked). The stored answers stand; only `id`, `type` and `span_in_context` were rewritten in `gen_F0.jsonl`, `gen_C1.jsonl` and the candidates file. Both arms answered it, so the F0 vs C1 discordant counts don't move. This reclassification came after the answers were seen, against the rule's order, and the question asks why developers switched while the quote says they moved, close to the shape of `nr4102` and `nr1372`.

**Counts:** the rule's planned 50 / 10 / 10 split is now 52 / 8 / 10 after per-question verification (`nr6848` and `nr5853` moved to answerable). `exp2_scale_stats.py` needed no change, because it has no hardcoded denominators: `test_rows` takes `n` from the questions in `questions.jsonl`, so it gives /52 and /18. The 20 in that script is James's second-rater rows, not a denominator. `tuning_rule_exp2_scale.md` still says 50 / 10 / 10 and /50, /20, as signed off.

**Trap: don't re-run `exp2_gitlab_scale.py score`.** It renumbers every blind id and overwrites `keys/sheet_key.json` even when it leaves the sheet alone, which would silently attach James's and Codex's labels to the wrong answers. `q5853`'s two rows were appended as S086 and S087 instead, and `summary.csv` was recomputed with `summarise` alone. Checked: all 87 rows still map through the key to the right question and answer text.

**Question check provenance (recorded 6 Nov, after scoring):** the rule's check, James and Alyssa each reading every question, was not done as written; `question_check_sheet.csv`'s `check` column is blank for 68 of 70, and neither person has a copy of the scaled sheet. The check was done by two automated passes plus James's reads of a few rows:
- **DeepSeek:** `question_check_sheet_deepseek.csv`, `ok` on all 70. Its notes say comments or the quote weren't visible on `q3137`, `q2913` and `q589`, whose quotes come from discussion or review threads, so its `ok` there doesn't confirm the quote.
- **Codex:** `question_check_sheet_codex.csv`, `ok` on 68, `drop` on `q2913` (rejected, see the table above), blank on `q6848`. It has no notes on its `ok` rows, and it likely can't see GitLab's JS-rendered comment threads.
- **James, in the scaled set:** `q2913`, `q6848` (was `nr6848`), `nr1372`, and the 8 rows in the verdict table above, so every `no_reason` row now has a person's read. His reads of `nr7461`, `nr188` and `rm5982` are pilot questions, not in the 70, so they don't count towards this set.
- **Weakest area:** a quote from comments was confirmed by a person only on `q2913`; `q3137` and `q589` still have no recorded person's read. Their quotes do exist word for word in the saved MR data.

**Trap:** `exp2_gitlab_scale.py build` rewrites `question_check_sheet.csv` with blank `check` and `note`, which would erase these entries. Back up the sheet before any rebuild.

## Decisions
- **Primary test:** permutation (James, 5 Nov, before any scaled result), because Exp 1's `stats.py` uses it for MRR. Wilcoxon is a sensitivity check with its own Holm family. They disagree on the pilot, so report both. Don't switch after seeing results.
- **Scale:** 231 + 2,000 to match Django's shape. Pilot Exp 2 stays on pool `A270` in `exp2_gitlab/`; scaled Exp 2 is on `A2000` in `exp2_gitlab_A2000/`.
- **Git:** this copy commits as `James <yolocon28@gmail.com>` (repo-local). The session account's email is Alyssa's, so don't infer who is talking from it.

## Traps
- GitLab refuses MR discussions without a token (401). The first pilot run lost all 3,648 comments this way; the adapter now stops on 401/403. Its output is kept as `results/INVALID_no_comments_*`.
- GitLab has no user type, so `mark_bots.py` marks bots by account pattern and Danger's text (194 notes in the pilot). `step1b` runs it after downloading. Any new download must run it before chunking.
- Chunk caches are named by MR ids and settings, not content. If documents change, change the dataset name in `make_chunks`, or stale chunks load silently.
- `1,208` is a count of MRs matching the `CLOSING` regex across 5,507 merged MRs, not confirmed closing links. 3 of the pilot's 33 candidates failed the task filters. Word it that way.
- Limit is 100 requests a minute on the token and about 4 requests per MR; `PACE` keeps it under that. No web download gives this data: see the options in the session's last answer if asked (project export needs maintainer access, a clone has no comments, GraphQL would be a new untested adapter).
- `exp2_gitlab.py` is generated from `exp2_sympy.py` by `make_exp2_gitlab.py`, so edit the generator.
- Pilot runs came before the first commit (4db315c) because the copy had no git identity. Commit before every run from now on.
- `exp1_gitlab.py` stops on uncommitted changes, so keep its log outside the repo while it runs. Its result rows now record config, budget, model and commit.
- The pilot's `exp2_gitlab/LABELLING.txt` still has SymPy wording (`exp2_sympy/keys/`, arms F0 / S0-G). The arms here are F0 and C1, and the keys are in `exp2_gitlab/keys/`. The scaled folder's `LABELLING.txt` has the right wording.
- Ollama may not be running: `generate` needs `ollama serve` first. The gate and report don't need it.
- The Codex CLI isn't on PATH. It's at `~/.codex/plugins/.plugin-appserver/codex.exe`, already logged in. Its file commands are blocked by policy, so put the data in the prompt (`codex exec -s read-only --output-schema`, with the prompt on stdin).
