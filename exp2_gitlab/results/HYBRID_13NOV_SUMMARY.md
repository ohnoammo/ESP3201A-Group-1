# Hybrid on "why" questions: summary (run 12 Nov 2026, for the 13 Nov report)

Rule: `tuning_rule_hybrid_13nov.md`, committed `12a0314` before any hybrid retrieval or generation on GitLab Runner. Hybrid = RRF (k 60, depth 100) of code-aware BM25 and dense. Dense = F0. No frozen arm, label or finding was changed.

## Run 1: retrieval (no generation)

Holm family "retrieval-why 6". Hit@5 and span: exact McNemar. MRR@5: sign-flip permutation test (10,000 draws) with a 95% bootstrap CI (1,000 draws). Django is **post hoc**; GitLab is exploratory.

| Repo | Outcome | Dense | Hybrid | Only hybrid / only dense | p | Holm p |
|---|---|---|---|---|---|---|
| Django (n 50, post hoc) | Hit@5 | 43 | 47 | 4 / 0 | 0.125 | 0.625 |
| Django | MRR@5 | 0.758 | 0.839 | 11 / 3 | 0.027 | 0.162 |
| Django | Span in context | 42 | 43 | 3 / 2 | 1.0 | 1.0 |
| GitLab Runner (n 52) | Hit@5 | 51 | 51 | 1 / 1 | 1.0 | 1.0 |
| GitLab Runner | MRR@5 | 0.897 | 0.913 | 7 / 3 | 0.677 | 1.0 |
| GitLab Runner | Span in context | 47 | 50 | 4 / 1 | 0.375 | 1.0 |

- **MRR@5 difference (hybrid − dense), 95% bootstrap CI:**
  - Django: +0.081 (0.013 to 0.162).
  - GitLab Runner: +0.017 (−0.052 to 0.085).
- **No test survives Holm.**
- **Regression check:** dense contexts rebuilt from F0's saved candidates equal `gen_F0.jsonl` for all 70 questions (ids and token sums).
- The Django dense and hybrid counts match the 5 Nov descriptive counts (`retrieval_H0_vs_F0_summary.json`).

**Question ids that changed**

| Repo | Outcome | Better with hybrid | Better with dense |
|---|---|---|---|
| Django | Hit@5 | q10097, q12664, q13507, q9006 | none |
| Django | Span | q12664, q13507, q9725 | q16824, q16982 |
| Django | MRR@5 | q10097, q11377, q11459, q11863, q12342, q12441, q12664, q13507, q15828, q9006, q9789 | q13671, q16824, q16982 |
| GitLab Runner | Hit@5 | q3137 | q5745 |
| GitLab Runner | Span | q2606, q1189, q1583, q6848 | q5745 |
| GitLab Runner | MRR@5 | q2606, q2744, q3137, q1189, q1583, q2223, q6848 | q3408, q3881, q5745 |

## Run 2: H0 vs F0 generation on GitLab Runner

Settings: qwen3:4b-instruct-2507 q4_K_M (digest 0edcdef34593), prompt v3 (sha1 072bd24371), Ollama 0.40.4, temperature 0, seed 42. Primary scoring is the lenient regex; the strict scoring gives identical counts. Holm family "hybrid-gitlab 2", exact McNemar.

| Outcome | F0 | H0 | Only H0 / only F0 | p | Holm p |
|---|---|---|---|---|---|
| Unanswerables answered /18 | 5 | 5 | 0 / 0 | 1.0 | 1.0 |
| Answerables answered /52 | 43 | 46 | 4 / 1 | 0.375 | 0.75 |
| Sensitivity: unanswerables answered without nr3177, nr4460 (/16) | 3 | 3 | 0 / 0 | 1.0 | (unadjusted) |
| Secondary, strict: unanswerables /18 and answerables /52 | 5; 43 | 5; 46 | same as above | same | same |
| Overlap-cited /52 (descriptive) | 40 | 42 | 6 / 4 | (0.754, not claimed) | – |
| Span in context /52 (descriptive) | 47 | 50 | – | – | – |

**MiniCheck gate at 0.5 (counts only):**

| Arm | Unanswerables answered, before → after /18 | Answerables answered, before → after /52 | Unanswerables kept |
|---|---|---|---|
| F0 (12 Nov gate rows, reference) | 5 → 2 | 43 → 42 | nr1781, nr4460 |
| H0 | 5 → 3 | 46 → 41 | rm3846, nr3177, nr4460 |

- **Identical contexts, H0 vs F0:** 0 of 70. Every H0 context differs from F0's, so no answer change can be put down to non-determinism alone.
- **Unanswerables answered:** the same 5 ids in both arms (nr1781, nr3177, nr3805, nr4460, rm3846).
- **Answerables answered:**
  - only by H0: q2606, q3408, q1583, q6848;
  - only by F0: q5745.
- **Overlap-cited:**
  - only H0: q2606, q3408, q1383, q1189, q1583, q6848;
  - only F0: q7545, q589, q5745, q4218.
- **Power caveat (stated in the rule before the data):** with F0 at 5/18, a significant reduction was impossible (best case 5/0, p 0.0625). The result is reported as counts.
- **Wording (per the rule):** "hybrid reduces hallucination" is not written. Unanswerables answered did not change (5 vs 5), and answerables answered and span-in-context did not fall, so the "fewer answers overall" clause does not apply.
- **Correctness:** a blank blind sheet is at `results/h0_gitlab_blind_sheet_blank.csv`. It has 35 H0 answered answerables whose citation-stripped text differs from F0's, in SHA-256 order, with the key in `results/keys/h0_gitlab_blind_key.json` (git-ignored, not opened). It is not labelled, so correctness for H0 on GitLab is not reported.

## Commits
- **`gitlab_runner_copy`, branch `exp2-baselines`:**

  | Commit | What |
  |---|---|
  | `12a0314` | Rule file |
  | `963fac3` | Rule hash line |
  | `6d96e5c` | `gitlab_h0.py` |
  | `4f47f16` | Hybrid candidates and `retrieval_why_gitlab.csv` |
  | `e13469c` | `retrieval_why_tests.csv` |
  | `daf7988` | `gen_H0.jsonl` and generation log |
  | `170cac3` | Run 2 counts, tests, gate and blank sheet |

  This summary is committed after these.
- **`ESP3201A_Exp2`:**

  | Commit | What |
  |---|---|
  | `c507229` | `h0_retrieval_tests.py` |
  | `fbfe620` | `results/retrieval_why_django.csv` |

## Deviations from the rule file and the prompt
1. **rank-bm25 is not installed.** It is missing from `pylib_h0` and the system Python, and no Exp 1 conda environment exists on this machine. It is only used by `sparse_retrieval.py --selftest`, not by retrieval. Retrieval ran with nltk 3.10.3 from `pylib_h0`, the same setup as Django H0. The selftest was not run.
2. **Dense ranking for the hybrid** = F0's saved top-100 candidates, as the rule's Run 1 bullet says. The dense half was not recomputed. The BM25 index (Qdrant, local mode) was built in the new folder `C:/Users/kwekt/ESP3201A_local/gitlab_h0_bm25`.
3. **Bootstrap seed.** The rule gives no seed for the bootstrap, so seed 0 was used, as for the permutation test. Permutation p = (1 + count) / 10,001, two-sided on the mean difference.
4. **Families the rule did not spell out:**
   - The secondary strict tests are a separate Holm family of 2, as in `tuning_rule_baselines.md`.
   - The /16 sensitivity is unadjusted.
   - Overlap-cited has a McNemar p in `h0_gitlab_tests.csv`, but it is labelled descriptive and not claimed.
5. **F0 gate numbers** are read from the 12 Nov `baselines_gate_rows.jsonl` (same code and revision), not recomputed. The H0 gate used Django's `faithfulness.MiniCheck` at revision 96eafd01 on CUDA, as the baselines gate did.
6. **Blind sheet rows** are H0 strict-answered answerables (strict answered is a superset of lenient answered; here the two sets are equal at 46) whose citation-stripped text differs from F0's.
7. **Not committed (not mine, left as found):** `results/baselines_unanswerable_full.xlsx` (modified), `ADVISOR_NOTES.md`, `codex_steering/`. Also left as found in `ESP3201A_Exp2`: its uncommitted HANDOVER and SymPy label edits.
