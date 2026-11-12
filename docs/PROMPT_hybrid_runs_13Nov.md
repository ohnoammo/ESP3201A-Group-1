# Claude Code prompt: two hybrid runs for the final report (13 Nov 2026)

Paste everything below the line into Claude Code on James's PC. The report is due Fri 13 Nov, 12:00 SGT.

---

You are working in `C:\Users\kwekt\OneDrive - National University of Singapore\Documents\NUS Year 2\Claude code\ESP3201A\`.
Read `EXP2_BASELINES_HANDOFF.md`, `ESP3201A_Exp2\tuning_rule_hybrid.md`, `ESP3201A_Exp2\tuning_rule_sympy_h0.md` and `ESP3201A_Exp2\sympy_h0.py` first. Those files define the existing H0 (hybrid) arm, and they are the template for both runs below.

**Standing rules (unchanged):**
- Never run `exp2_gitlab_scale.py score` or `build`.
- Never edit Exp 1 files, existing results or label files. Write new files only.
- Commit before every run.
- Do not open any `keys/` folder.
- BM25 needs nltk 3.10.3 and rank-bm25. James's system Python lacks them, so use the environment that Django H0 used (`pylib_h0` on PYTHONPATH, or the Exp 1 conda env's python.exe called directly). Check the BM25 imports work **before** committing the rule file.
- GitLab work goes in `gitlab_runner_copy` on branch `exp2-baselines`.

## Step 0: commit the rule file before running anything

Create `gitlab_runner_copy\tuning_rule_hybrid_13nov.md` with exactly the content between the markers, fill in the commit hash line after committing, and commit it. Run nothing before that commit.

<<<RULE
# Hybrid on "why" questions: rule file (13 Nov 2026)

Committed before any hybrid retrieval or generation on GitLab Runner "why" questions. Django H0 results (5 Nov) and the Exp 1 short-query results were already seen. **Status:** Run 1 (Django part) is a test on existing descriptive counts, so it is post hoc. Run 1 (GitLab part) and Run 2 are exploratory, with rules fixed before data. No frozen arm, label, rule or finding changes.

**Question (the course brief's RQ):** on the "why" questions the app actually serves, does hybrid retrieval (dense + BM25, RRF) improve context relevance and reduce hallucination compared with dense alone?

## Retrievers (identical to Django H0)
- Dense = F0's retriever: Qwen3-Embedding-0.6B, GitLab "why" instruction, pool A2000, fixed 512/77, chunk set as in `exp2_gitlab_A2000/gen_F0.jsonl`.
- Hybrid = RRF (k = 60, depth 100) of code-aware BM25 (k1 1.2, b 0.75, query = question text without instruction) and that dense ranking.
- `exclude_prs` reaches both retrievers before fusion.
- Packing: alpha 0, budget 2,560, score order. Nothing is tuned.

## Run 1: retrieval on "why" questions (no generation)
- **Questions:** Django 50 answerable test questions (from the existing F0 and H0 candidate files, no new retrieval); GitLab Runner 52 answerable questions (new hybrid candidates; dense = F0's saved candidates).
- **Outcomes per question, dense vs hybrid:**
  - gold PR/MR in the first 5 distinct ranked PRs (Hit@5);
  - reciprocal rank of the gold PR if ≤ 5, else 0 (MRR@5);
  - answer span in the packed context.
- **Tests:** Hit@5 and span by exact two-sided McNemar; MRR@5 by paired sign-flip permutation (10,000, seed 0) with a 95% paired bootstrap CI (1,000).
- **Holm family "retrieval-why 6":** 2 repos × 3 outcomes. The Django tests are labelled post hoc in the report.
- **Regression check:** rebuilt dense contexts must equal F0's `context_chunk_ids` for all 70 GitLab questions. Any difference stops the run.

## Run 2: H0 generation on GitLab Runner
- **Arm:** H0 = F0 with hybrid ranking. Same 70 questions (52 answerable, 8 no_reason, 10 removed), qwen3:4b-instruct-2507-q4_K_M (digest 0edcdef34593), prompt v3 as in F0 (same sha1), Ollama 0.40.4, temperature 0, seed 42, num_ctx 8192, num_predict 512, think off.
- **Hardware control:** none needed. F0 was re-run 70/70 byte-identical on this machine (12 Nov).
- **Scoring:** the baselines' pre-registered lenient refusal regex (primary), strict rule (secondary), exactly as in `tuning_rule_baselines.md`.
- **Holm family "hybrid-gitlab 2":** H0 vs F0, exact McNemar:
  1. unanswerables answered /18;
  2. answerables answered /52.
- **Sensitivity:** without nr3177 and nr4460 (/16).
- **Descriptive:**
  - overlap-cited /52;
  - identical contexts H0 vs F0 (on those rows any answer change is non-determinism);
  - MiniCheck gate at 0.5 on H0, counts only.
- **Power, stated before data:** F0 answers 5/18 unanswerables, so a fall to 0 gives at best 5/0, p = 0.0625. A significant *reduction* is impossible. Only an increase of 7 or more all one way could survive. The result is reported as counts with this caveat.
- **Wording rule (as the Django amendment):** "hybrid reduces hallucination" is never written from this run. A fall in unanswerables answered alongside a fall in answerables answered or span-in-context is written as "fewer answers overall".
- **Correctness:** if time permits, one blind sheet of H0 answered answerables whose text differs from F0's (citations stripped, SHA-256 shuffle, key in `keys/`). It is labelled by a group member. Otherwise correctness is not reported for H0 on GitLab.

Commit hash of this file: ________
RULE>>>

## Step 1: Run 1 (retrieval only)

1. **Django:** write `ESP3201A_Exp2\h0_retrieval_tests.py`. It reads `results/candidates_fixed_s512_o77_k100.jsonl` (F0) and `results/candidates_fixed_s512_o77_k100_hybrid.jsonl` (H0) and the existing generations for span-in-context, reusing `h0_retrieval.py`'s logic without editing it. It computes Hit@5, MRR@5 and span per question and writes `results/retrieval_why_django.csv`.
2. **GitLab:** write `gitlab_runner_copy\gitlab_h0.py`, modelled on `sympy_h0.py`, with `retrieve`, `generate` and `score` commands. `retrieve` builds the BM25 index for the A2000 chunk set in a **new local copy** (not the OneDrive Exp 1 folders), produces hybrid top-100 candidates for all 70 questions into `exp2_gitlab_A2000/candidates_fixed_s512_o77_k100_hybrid.jsonl`, and runs the dense regression check. Then compute the same three outcomes for the 52 answerables and write `results/retrieval_why_gitlab.csv`.
3. Write `results/retrieval_why_tests.csv` containing all 6 tests, with b, c, exact p, Holm p, MRR differences and CIs.

## Step 2: Run 2 (H0 generation on GitLab)

1. Run `gitlab_h0.py generate` to produce `exp2_gitlab_A2000/gen_H0.jsonl` (70 rows), then `gitlab_h0.py score`. Write:
   - `results/h0_gitlab_counts.csv`
   - `results/h0_gitlab_tests.csv`
   - `results/h0_gitlab_gate.csv`
   - the blind sheet, if one is made.
2. Commit the outputs.

## Step 3: report back

Paste one short markdown summary into `results/HYBRID_13NOV_SUMMARY.md` containing:
- the Run 1 table (repo × dense/hybrid × Hit@5, MRR@5, span), with test p and Holm p;
- the Run 2 table (F0 vs H0: unanswerables answered /18, answerables answered /52, overlap-cited /52, gate counts), with tests;
- the question ids that changed in each direction;
- the commit hashes;
- anything that deviated from the rule file.

Do not interpret beyond the wording rules.
