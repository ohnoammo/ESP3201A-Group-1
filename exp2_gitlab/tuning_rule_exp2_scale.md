# Scaled Exp 2 on gitlab-runner: rule set before any generation

**Signed off by James as drafted, 6 Nov 2026, before any scaled generation; every recommendation below is the decision.** Written after seeing the 15-question pilot's counts, so those counts must not be used to pick a test or a direction.

## Fixed
- **Setting, unchanged:** dense Qwen3-Embedding-0.6B, Exp 2 "why" instruction, top 100, fixed 512/77, 2,560 budget, prompt v3, temperature 0, seed 42, `num_ctx` 8192, Ollama 0.40.4.
- **Files:** the pilot's files stay as they are. The scaled run writes only to its own folder, `exp2_gitlab_A2000/`, including its own `keys/`.
- **Labelling:** people label blind, and Alyssa is the reference rater. Nobody opens `keys/` before labels are final.
- **Status:** exploratory transfer check, not in the Exp 2 Findings. Data and labels differ from Django, so results are not compared with Django as if like for like. No settings are tuned on this set.

## Decisions (James, 6 Nov)

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Pool and number of questions | Pool `A2000` (2,231 MRs). 50 answerable + 10 no_reason + 10 removed | Matches the size of Django's 50 answerable. About 85 answers to label (50 x 2 arms x the pilot's 17/20 answered), close to Alyssa's 80 rows in Exp 2. Smaller option: 30 answerable, about 51 rows, but less chance of a test reaching significance |
| 2 | Who writes and who checks | Claude writes, in a fresh session that has seen no generated answers. James and Alyssa each check every question; James settles differences. All checks finish before retrieval | The pilot's `rm5982` was reworded after generation, which left its answers on the old wording |
| 3 | Arms and models | F0 and C1, 4B, prompt v3 | Same as the pilot. Adding 8B would double the labelling |
| 4 | Pilot's questions | Keep out as question sources all 39 MRs on the pilot's shortlist, not only the 15 used. They stay in the pool as distractors | Their digests were read when the pilot's questions were written. 284 eligible MRs remain |
| 5 | MiniCheck gate | Run it, secondary, counts only | The model is already downloaded. It needs the code fix below first |
| 6 | Tests or counts | Exact McNemar, F0 vs C1, two-sided, one Holm family of 3. **Primary: strict correct /50.** Also in the family: answered /50 and unanswerable answered /20. Lenient correct (correct + partial) is a sensitivity with unadjusted p. Everything else is counts only | Same test as Exp 2's correctness family. With Holm over 3, at least 7 discordant questions all one way are needed for significance (p = 0.0156 before Holm), so a non-significant result won't show the arms are equal |

## Labelling rules, from the pilot
- **One row per arm and question.** Two rows with the same text are two arms giving the same answer, and each gets a label (pilot: S004 and S005). Only `correct`, `partial` or `wrong` are valid; a script rejects anything else before `report`.
- **Second rater.** Alyssa labels every row. James labels a fixed 20 rows chosen by SHA-256 order, for agreement only. Her label is the one used.
- **Judge questions on what the model can see.** Bot notes are not in the documents (pilot: `nr7461`'s flagged comment was a GitLabDuo note). The check sheet's MR link shows them, so the instructions must say this.
- **A reason must date from the change.** A later note reviving the thread doesn't count as the reason, though the model can still see it (pilot: `nr188`).

## Code needed before any run (checked against `exp2_gitlab.py` at f02cad1)
1. **New script.** Add `make_exp2_gitlab_scale.py` to write `exp2_gitlab_scale.py` by listed replacements, leaving the pilot's script unchanged: `POOL` `A270` -> `A2000`, `OUT` -> `exp2_gitlab_A2000`.
2. **Gate fix.** `cmd_gate` calls `pack` without alpha or links, so its context check fails on C1 unless the links change nothing. It must pass both.
3. **Shortlist.** `N_SHORTLIST` is 60, so raise it to 100 for 70 questions, which is a sourcing limit and not a model setting. Skip the pilot's 39 MRs. The funnel gives 320 eligible MRs in `A2000`, 36 of them on the pilot's shortlist (3 of the 39 no longer pass; cause not checked).
4. **Labelling text.** `LABELLING` still has SymPy wording and arm names. Replace it, with the rules above.
5. **Stats and sheet check.** Add a script for the McNemar family above and the label check. `exp2_gitlab.py` has no tests.
6. **Known limit.** `report` has no concept of excluded rows, so any exclusion is audit-only.

## Checked, no change needed
- `chunk_set` asks for dataset name `swe`, so it will build a new cache for `A2000`. The rebuilt 17,636 chunks match Exp 1's `A2000` chunks exactly.
- All 17,636 chunks are in the embedding cache, so only queries need embedding.
- Links stay inside one MR, and a removed question's excluded MRs are taken out before packing, so links can't bring an excluded MR back.
- Ollama is on 0.40.4 with the 4B model present, and MiniCheck is in the Hugging Face cache.
- Time: generation averaged about 3 seconds an answer in the pilot, so about 7 minutes for 70 questions x 2 arms.

## Order
Commit this rule -> code changes, commit -> shortlist and digests -> questions -> people check them -> commit -> retrieve -> generate -> score -> people label -> stats -> gate -> report. Commit before every run.
