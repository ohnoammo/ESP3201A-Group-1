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

Commit hash of this file: 12a0314 (the commit that added this file; this line was filled in by the next commit)
