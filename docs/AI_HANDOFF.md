# AI handoff: ESP3201A Group 1 RAG project (Experiment 1: retrieval)

Read this first if you are an AI assistant helping a member of this group. It records what has
been built, why, and the current status. Last updated: 6 Nov 2026 (section 8 = Experiment 2 status as of 6 Nov; section 9 = demo app).
Maintenance: whoever (human or AI) makes progress updates section 5 and the progress log.
Details: `README.md` (run steps + parameters), `CHUNKING_NOTES.md` (PR document, chunking,
BM25), `DENSE_NOTES.md` (dense + hybrid).

## 1. Project
Local, offline RAG assistant over **code review data**: 1 PR = 1 document (title,
description, commit messages, diff, review + conversation comments). Group 1: Alyssa Chua
Sin Ru, Kwek Tze Xuan, Liu Ziheng Clifton.
- **Experiment 1 (retrieval, no LLM):** chunking (fixed vs structural) x retrieval (BM25 /
  dense Qwen3-Embedding / hybrid RRF) on **SWE-bench Verified, django/django (231 tasks)**.
  Query = bug report; correct answer = the fixing PR.
- **Experiment 2 (generation):** no retrieval vs standard RAG vs strict grounded (cite or
  "not found"); "why" questions mined from real Django review threads (separate brief).
- **QASPER / MultiHop-RAG were dropped** (switched to code review); their code and data were
  deleted. Earlier QASPER findings are summarised in section 6 for reference only.

## 2. Who does what
- BM25 / sparse (`sparse_retrieval.py`, code-aware tokenizer) + metrics: Alyssa.
- Dense + hybrid (`dense_retrieval.py`): Liu Ziheng (method unchanged from QASPER).
- Experiment 2 (generation, faithfulness): James (Kwek Tze Xuan), on his machine (RTX 5070 12 GB,
  Ollama). Code + its own `HANDOVER.md` in `ESP3201A_Exp2/` (git); status summarised in section 8.
  Exp 1 owners (Ziheng, Alyssa) are asked about retrieval-side questions (PR-level baseline).

## 3. Decisions (do not silently change)
- Data: SWE-bench Verified only (non-Verified bug reports are often underspecified). Split
  **dev 50 / test 181**, SHA-256 based, fingerprint **b57872f8e804ec6b** (`swe_split_ids.json`).
  Test is run ONCE with the chosen settings, plus once with untuned defaults.
- Pool: **A chosen** (fixing PRs + 2,000 distractors from 2016-11..2023-07). B (per-bug date
  windows) needed ~10 h download + ~14 h GPU embedding per chunk setting: too slow to tune.
  Pool A size filter: PRs > 100 files or > 50,000 tokens excluded (28 before top-up), pool
  topped back up to 2,000; no fixing PR near the limits (max 20 files / 9,977 tokens).
  Pools are not filtered on merged state (Django closes many fixing PRs without merging).
- No content stripping; only a **copied-text check** (>= 10 consecutive words shared with the
  bug report), results reported with and without flagged PRs.
- Chunk size unit = words + symbols (`\w+|[^\w\s]`). Structural replaces semantic chunking.
  **No +-10% size rule** for structural; chunk-size stats for every condition plus a
  size-matched fixed baseline (`--size-matched`).
- No 1-file vs multi-file breakdown (22/181 test tasks multi-file); reported descriptively
  (159/181 = 88% single source file). Breakdown kept: copied vs not copied.
- Main metric **PR-level Hit@5 / MRR@5** (MRR counts only inside the top 5). Secondary: top-5
  chunks, chunk-level Hit/MRR and line-level Recall/Precision/F1 vs the fixing PR's changed
  lines (all files; `src_*` = files in SWE-bench `patch`).
- **BM25 k1/b are not tuned** (decided 13 Oct): fixed at 1.2 / 0.75; with 50 dev tasks their
  effect is below the noise. Only chunk settings are tuned.
- Tuning on dev only (`select_chunking.py`, rule written in its docstring). Untuned defaults:
  fixed 256 tokens / no overlap, structural cap 512, BM25 k1 1.2 / b 0.75, RRF k 60.
- Stats: bootstrap CIs, McNemar (Hit@5), paired permutation + bootstrap (MRR@5).
- Same pool, chunks, queries, filter and k for every retriever.

## 4. Files
See the table in `README.md`. Generated folders: `prs/` (GitHub cache, one JSON per PR),
`chunks/`, `emb_cache/`, `qdrant_exp1/`, `results/`.

## 5. Status (14 Oct 2026) and next steps
Done:
- Code adapted to SWE-bench (all files in README). `sparse_retrieval.py --selftest` passes
  (Qdrant BM25 = reference formula to ~1e-7; same top result as rank_bm25).
- `swebench_loader.py`: 231 Django tasks confirmed (PR #7530-#17087, 2016-11 .. 2023-07).
- Split made: dev 50 / test 181, fingerprint b57872f8e804ec6b.
- End-to-end test (BM25 only) on 45 FAKE PRs built from SWE-bench patches: chunking, metrics,
  breakdowns, size-matched run, k1/b grid, selection and stats all run. Scores meaningless.
Update 14 Oct 2026 (Ziheng's laptop, RTX 3050 Ti):
- Environment `esp3201a` updated with `pip install -r requirements.txt` (adds datasets, rank-bm25;
  CUDA torch 2.14.1+cu130 kept). `sparse_retrieval.py --selftest` passes (max diff 2.8e-07, 4/4).
- **Dense pilot done** (`results/swe_exp1_pilot_dense.*`): 5 dev tasks, pool A2000 (2,231 PRs),
  fixed 256 / overlap 0 (14,837 chunks, avg 237 tokens), full + short queries.
  Embedding 14,830 chunks took ~55 min (~4.6 chunks/s, ~3.7 s per batch of 16, fp16).
  Truncation at Qwen3's 1,024-token limit: 3/14,830 chunks (0.02%), 1/5 queries (2,665 tokens).
  BM25 numbers reproduce the earlier BM25-only pilot exactly (full Hit 0.60 / MRR 0.467).
  PR-level (full / short): BM25 Hit 0.60/0.80, MRR 0.47/0.53; dense Hit 1.00/1.00, MRR 0.90/0.77;
  hybrid Hit 1.00/1.00, MRR 0.63/0.80. n=5: not interpretable beyond "pipeline works".
- Workload estimate for the dev tuning grid (computed from the PR cache): 8 chunk settings =
  136,164 unique chunks, ~107M characters; minus the pilot's fixed-256 chunks (cached) ->
  ~92M characters, ~5.5-6 h of embedding at the pilot speed + search time. Chunks over ~3,500
  characters (possible Qwen3 truncation): 0-1 per setting, so truncation is negligible.
- Dev tuning run started 14 Oct 01:41. Windows Update force-restarted the laptop at 06:59
  (Event Id 1074, MoUsoCoreWorker, "Service pack (Planned)"). Completed before the restart:
  embeddings for struct_c256, struct_c512, fixed_s128_o0 and ~90% of fixed_s128_o19 (~108k
  chunk embeddings in `emb_cache/`). Results JSON is only written at the end, so the run is
  restarted with the same command (cached embeddings are reused; searches are redone).
- Index reuse added (14 Oct, Ziheng's AI): `exp1_common.build_retrievers` now reuses a Qdrant
  collection if it already holds exactly one point per chunk (name includes the chunk-set hash,
  point ids are uuid5(chunk_id), so it is identical to a rebuild); partial/stale collections are
  rebuilt as before; `--rebuild-indexes` forces a rebuild. Reason: in local mode re-writing a
  ~30k-point dense collection takes ~30 min, and the restarted run was rebuilding every finished
  setting. Results are unchanged; saves ~2 h on resumed runs and on the test runs (same pool).
- 14 Oct ~13:14: run crashed while saving the embedding cache: `os.replace(tmp, cache)` ->
  PermissionError WinError 5 (cache file locked by another program, most likely OneDrive sync
  or an antivirus scan of the ~520 MB file). Embeddings for fixed_s256_o38 were complete in
  `...npz.tmp.npz`. Fix in `dense_retrieval.py` (Ziheng's AI): the cache save retries the
  replace (15 x 2 s) and never crashes (keeps tmp + memory, retries at the next save); loading
  uses the newest readable of the main/tmp files and promotes tmp. Results unaffected.
- **Dev tuning run finished 14 Oct ~18:00** (`results/swe_exp1_dev.*`; 50 dev tasks, 17 flagged
  as copied text at n=10; 16 chunks and 1 query truncated by Qwen3; 6,238 s of new embedding
  in the final session). Mean PR MRR@5 over BM25/dense/hybrid (full queries) and mean Hit@5:
  | setting | avg tokens | BM25 | dense | hybrid | mean MRR | mean Hit |
  |---|---|---|---|---|---|---|
  | fixed 128 / 0 | 123 | 0.713 | 0.944 | 0.880 | 0.846 | 0.907 |
  | fixed 128 / 19 | 124 | 0.751 | 0.932 | 0.883 | 0.855 | 0.933 |
  | fixed 256 / 0 | 237 | 0.728 | 0.955 | 0.863 | 0.849 | 0.913 |
  | fixed 256 / 38 | 242 | 0.747 | 0.940 | 0.892 | 0.859 | 0.913 |
  | fixed 512 / 0 | 442 | 0.761 | 0.975 | 0.933 | 0.890 | 0.940 |
  | fixed 512 / 77 | 455 | 0.767 | 0.977 | 0.925 | 0.889 | 0.947 |
  | struct cap 256 | 110 | 0.749 | 0.939 | 0.904 | 0.864 | 0.933 |
  | struct cap 512 | 119 | 0.745 | 0.935 | 0.902 | 0.861 | 0.920 |
  Observations: dense > hybrid > BM25 in every setting; chunk settings differ by <= ~0.04 MRR
  (1-2 tasks out of 50); the best fixed setting has ~4x larger chunks than structural (455 vs
  110 tokens), so the size-matched baseline in the test runs is essential; BM25 does much
  better on copied-text tasks (e.g. struct_c256 MRR 0.853 copied vs 0.695 not copied).
- **CHOSEN SETTINGS (locked 14 Oct 18:15, before any test run), by `select_chunking.py`:**
  fixed 512 tokens / overlap 77 (15%) (tie with overlap 0 within 0.005 -> higher Hit@5);
  structural cap 256 (tie with 512 -> higher Hit@5); BM25 k1 1.2 / b 0.75 (not tuned).
- NOTE: the test commands printed by `select_chunking.py` omit the pool options; add
  `--pool A --n-distractors 2000` (otherwise the default pool B is used, which was never
  downloaded).
- **Relation factor + token budget added (19 Oct, before any test run):** `relations.py`.
  What an LLM receives is now measured as a fixed 2,560-token budget (same for every
  method) instead of "top 5 chunks". After the unchanged search, retrieved chunks can pull in
  linked CODE chunks of the same PR (description -> hunks, review thread -> its hunk,
  hunk -> other hunks; fixed: neighbour chunks), scored alpha x the rank-based score of the
  chunk that brought them in. One alpha per chunking method, tuned on dev from
  {0, 0.25, 0.5, 1} by budget line recall (mean over retrievers; ties -> smaller alpha).
  alpha = 0 = old behaviour. Explanation links (hunk -> review thread / description) exist
  (`kinds=("context",)`) but are for Exp 2 only. PR-level metrics are unaffected.
  Also added: `top5_distinct_prs` per query, and `select_chunking.py` now prints the pool
  options in the test commands (they were missing).
  Scoring is 1/rank (linked: alpha/rank). A first version used 1/(60+rank) (the RRF
  formula); a BM25-only dev check showed it is too flat (alpha 0.25 and 0.5 never got a link
  into the budget), so it was changed on dev, before any test run.
  BM25-only dev check (50 tasks, 2,560-token budget), budget recall alpha 0/0.25/0.5/1:
  structural cap256 0.479/0.711/0.707/0.705; fixed 512/15% 0.714/0.736/0.764/0.765.
  Precision rises too. BUT gold_in_budget falls (struct 0.86 -> 0.76-0.78, fixed 0.86 ->
  0.82): when a WRONG PR ranks first, its links can push the fixing PR out of the budget.
Next: dev alpha run with all 3 retrievers (GPU; ~minutes, embeddings cached):
  `python run_retrieval_swe.py --split dev --pool A --n-distractors 2000 --fixed-sizes 512
  --overlap-fracs 0.1504 --struct-caps 256 --alphas 0 0.25 0.5 1 --batch-size 16 --tag _dev_alpha`
  then `python select_chunking.py results/swe_exp1_dev.json results/swe_exp1_dev_alpha.json`,
  then the tuned + untuned test runs it prints, then `stats.py`.

**Update 20-23 Oct 2026 (Ziheng's laptop, v3 folder `Latest/ESP3201A_SWE_exp1_v3`): dev retuning
on pools A and H, settings locked, ALL FOUR TEST RUNS DONE. Experiment 1 is complete.**
- Setup: the v3 zip has no `emb_cache/`; the old 580 MB cache was copied in from the previous
  folder (PR text and embedding code unchanged, so all 136,164 cached embeddings were reused).
  `qdrant_exp1/` and `chunks/` were NOT copied (names depend on the pool, which changed).
- Pool A (2,231 PRs, after the same-ticket filter swapped 16 distractors), dev chunk grid
  (`results/swe_exp1_dev_v2.*`, done 20 Oct 23:20, ~4 h, mostly re-indexing). Mean PR MRR@5 over
  BM25/dense/hybrid (full queries), mean Hit@5:
  | setting | fixed 128/0 | 128/19 | 256/0 | 256/38 | 512/0 | **512/77** | **struct 256** | struct 512 |
  |---|---|---|---|---|---|---|---|---|
  | mean MRR | 0.847 | 0.855 | 0.854 | 0.861 | 0.894 | 0.894 | 0.872 | 0.867 |
  | mean Hit | 0.907 | 0.933 | 0.913 | 0.913 | 0.940 | 0.947 | 0.933 | 0.920 |
  Chosen: fixed 512/77 (tie with 512/0 -> higher Hit), structural cap 256 (tie -> higher Hit).
  Same as before the filter.
- Pool A alpha grid (`swe_exp1_dev_v2_alpha.*`, 21 Oct 00:08). Budget line recall (alpha 0 ->
  chosen) / gold_in_budget: fixed.bm25 0 (every alpha > 0 drops gold 0.86 -> 0.82);
  fixed.dense 1 (0.853 -> 0.936, gold 1.00); fixed.hybrid 0.5 (0.824 -> 0.867, gold 0.96 -> 0.94);
  structural.bm25 0 (gold 0.86 -> <= 0.78); structural.dense 0.5 (0.669 -> 0.945, gold 1.00 -> 0.98;
  ties with 1.0 -> smaller); structural.hybrid 0 (gold 1.00 -> <= 0.96, forgoing 0.63 -> 0.87).
- Pool H (2,231 PRs; 1,476 not in pool A) dev chunk grid (`swe_exp1_devH.*`, 21 Oct 14:07, ~13 h:
  ~150k new chunk embeddings, pool H PRs give ~1.5x more chunks than pool A, e.g. struct 256
  51,028 vs 33,298). Mean PR MRR@5 / Hit@5: fixed 128/0 0.784/0.887, 128/19 0.779/0.900,
  256/0 0.825/0.907, 256/38 0.817/0.900, 512/0 0.827/0.907, **512/77 0.847/0.927**,
  **struct 256 0.770/0.887**, struct 512 0.771/0.867. Chosen: fixed 512/77 (clear), structural
  cap 256 (tie -> higher Hit). Pool H is harder, BM25 most (struct 256 BM25 MRR 0.75 -> 0.63).
- Pool H alpha grid (`swe_exp1_devH_alpha.*`, 21 Oct 17:08): fixed.bm25 0.5 (0.639 -> 0.711,
  gold 0.82 kept; 1.0 drops it); fixed.dense 0.5 (0.812 -> 0.888; ties with 1.0 -> smaller);
  fixed.hybrid 0 (all alpha > 0 drop gold 0.96 -> <= 0.92); structural.bm25 0; structural.dense
  0.25 (0.573 -> 0.880, gold 1.00 -> 0.98; 0.5/1 drop it to 0.94); structural.hybrid 0.
  NOTE: alpha choices differ between pools (fixed.bm25 0 vs 0.5, fixed.dense 1 vs 0.5,
  fixed.hybrid 0.5 vs 0, structural.dense 0.5 vs 0.25); several were decided by 1 dev task
  (the 0.02 safety margin = 1 of 50) -> alpha is fragile with 50 dev tasks (report it).
- **LOCKED SETTINGS (agreed by the group 22 Oct, before any test run):** chunks fixed 512/15% (77)
  and structural cap 256 in both pools; BM25 k1 1.2 / b 0.75; alpha per pool:
  A `fixed.bm25=0 fixed.dense=1 fixed.hybrid=0.5 structural.bm25=0 structural.dense=0.5 structural.hybrid=0`;
  H `fixed.bm25=0.5 fixed.dense=0.5 fixed.hybrid=0 structural.bm25=0 structural.dense=0.25 structural.hybrid=0`.
- **Test runs (181 test tasks, each run once, 22-23 Oct, ~11.5 h in total):** commands as printed
  by `select_chunking.py` + `--batch-size 16`; pool H tags changed to `_testH_tuned` /
  `_testH_untuned` (the printed ones would have overwritten pool A). Files:
  `results/swe_exp1_test_tuned.*` (pool A, 23 Oct 01:47), `_test_untuned.*` (04:03),
  `_testH_tuned.*` (07:29), `_testH_untuned.*` (10:51); stats saved as
  `results/stats_test_poolA_full.txt`, `stats_test_poolH_full.txt` (+ `_short` if run).
  Size-matched fixed baselines (no overlap): pool A fixed_s110_o0 (tuned) / fixed_s119_o0
  (untuned); pool H fixed_s111_o0 / fixed_s120_o0. Copied-text tasks on test: 45/181 (n=10).
  10 test queries exceed Qwen3's 1,024 tokens (truncated).
- **Test results, full queries** (PR Hit@5 / PR MRR@5 / budget line recall at alpha 0;
  "+links" = budget recall at the locked alpha, gold_in_budget alpha 0 -> locked alpha):
  | pool | chunking | BM25 | dense | hybrid |
  |---|---|---|---|---|
  | A | fixed 512/77 | 0.829 / 0.738 / 0.650 | 0.978 / 0.937 / 0.856; +links (a=1) 0.923, gold 0.978 -> 0.978 | 0.961 / 0.876 / 0.800; +links (a=0.5) 0.841, gold 0.934 -> 0.901 |
  | A | struct 256 | 0.762 / 0.633 / 0.439 | 0.972 / 0.909 / 0.666; +links (a=0.5) 0.924, gold 0.989 -> 0.950 | 0.934 / 0.815 / 0.635 |
  | A | fixed 110 (size-matched) | 0.790 / 0.661 / 0.396 | 0.972 / 0.910 / 0.605; +links (a=1) 0.763 | 0.934 / 0.839 / 0.575; +links (a=0.5) 0.687 |
  | H | fixed 512/77 | 0.807 / 0.669 / 0.594; +links (a=0.5) 0.641, gold 0.762 -> 0.724 | 0.972 / 0.913 / 0.820; +links (a=0.5) 0.890, gold 0.961 -> 0.950 | 0.956 / 0.858 / 0.738 |
  | H | struct 256 | 0.724 / 0.584 / 0.377 | 0.945 / 0.858 / 0.559; +links (a=0.25) 0.858, gold 0.978 -> 0.950 | 0.939 / 0.762 / 0.533 |
  | H | fixed 111 (size-matched) | 0.729 / 0.621 / 0.366; +links 0.460 | 0.961 / 0.877 / 0.525; +links 0.698 | 0.934 / 0.795 / 0.512 |
  Untuned (alpha 0), pool A PR MRR@5 BM25/dense/hybrid: fixed 256/0 0.703/0.916/0.877,
  struct 512 0.624/0.908/0.798, fixed 119 0.658/0.922/0.845. Pool H: fixed 256/0
  0.662/0.895/0.842, struct 512 0.586/0.860/0.748, fixed 120 0.614/0.878/0.787.
- **Significance (stats.py, full queries; p < 0.05):**
  * Retrievers: dense > hybrid > BM25 on MRR@5 in every chunking and both pools (all
    significant); dense vs hybrid Hit@5 mostly NOT significant (only pool A fixed 110, p=0.039).
  * Fixed 512/77 vs struct 256: MRR@5 higher for fixed with every retriever (dense pool A
    p=0.039, pool H p<0.001); budget recall (alpha 0) much higher for fixed (bigger chunks).
  * Structure at EQUAL size (fixed ~110 vs struct 256): MRR@5 not significant anywhere. Pool A:
    struct has significantly higher budget recall for all three retrievers (dense 0.666 vs 0.605,
    p=0.001; BM25 p=0.003; hybrid p=0.001). Pool H: no significant difference (dense p=0.091).
  * Links: budget recall rises significantly in every tested combination (e.g. pool A
    struct+dense 0.666 -> 0.924, pool H 0.559 -> 0.858); PR-level metrics unchanged (by design).
    Not tested by stats.py: struct+links vs fixed 512+links (pool A 0.924 vs 0.923).
  * Tuned vs untuned: struct 256 vs 512 never significant; fixed 512/77 vs 256/0: MRR@5
    significant on pool A for BM25 (p=0.029) and dense (p=0.042), not on pool H; budget recall
    significant in both (bigger chunks).
- **Caveats for the report:** (1) links lose the fixing PR from the budget more often on test
  than the dev safety rule allowed (e.g. pool A struct+dense 0.989 -> 0.950 = ~7/181; pool H
  fixed+BM25 0.762 -> 0.724); (2) alpha choices are pool-dependent and fragile (above);
  (3) dev and test numbers are from one laptop run each; nothing was re-run after seeing test
  results.
- Not in the v3 folder: `retrieve.py` (frozen Exp 2 retriever with `exclude_prs` /
  `get_chunks`), `check_leakage.py`, `hard_pool.py` (superseded by pool H). They are still in the
  old folder (`RAG Project/ESP3201A_SWE_exp1/ESP3201A_SWE_exp1`). Open question for Exp 2: use the
  token budget + links (pool A fixed.dense alpha 1) or plain top-5 chunks.
- Review of the summary above by a teammate (24 Oct, checked against both zips): mostly right.
  Corrections: (1) `stats.py`'s tuned-vs-untuned section also compares MISMATCHED chunk sizes
  (e.g. fixed 512 vs 119, 110 vs 256) - those rows are meaningless and should be dropped from the
  script/report; valid pairs: structural cap 256 vs 512 never differs, fixed 512/77 vs 256/0
  raises budget recall by ~0.1 for every retriever in both pools. (2) "BM25 drops most on pool H"
  holds only for fixed 512; for structural all three retrievers lose ~0.05 MRR and dense loses
  more budget recall than BM25. (3) Structural vs same-size fixed (alpha 0) and "struct+links level
  with fixed 512+links" hold on pool A only (pool H 0.858 vs 0.890, p=0.08, teammate's test).
  (4) Strongest result, both pools: structural + links beats same-size fixed + links by ~0.16
  budget recall, p < 0.001 (paired permutation run by the teammate; not in stats.py). (5) Report
  gold eviction by links as a table over all linked conditions (pool A fixed+hybrid 0.934 -> 0.901,
  struct+dense 0.989 -> 0.950; pool H struct+dense 0.978 -> 0.950; fixed+dense pool A 0 lost); the
  2% dev rule = 1 of 50 bugs, so ~4% on test is within sampling noise.
Next: write up Experiment 1 (Alyssa: results/analysis). Possible Exp 1 follow-up raised by the
prof (24 Oct, section 8): a "no chunking" / whole-PR baseline.

Earlier plan (12 Oct):
1. `github_prs.py index`, `fixing` (needs GITHUB_TOKEN), then `size-check` -> group picks pool.
2. Pilot: 5 dev tasks, ~200-PR pool A, all 6 combinations (dense needs torch +
   sentence-transformers on the machine that runs it).
3. Dev tuning -> `select_chunking.py` -> test runs (tuned + untuned) -> `stats.py`.

## 6. History: QASPER results (retired dataset, for reference only)
BM25 on QASPER dev (k=5): fixed 200 words Recall 0.659 / semantic p95 0.690. Tuning on a 20%
QASPER split chose fixed overlap 25 and semantic percentile 92.5; hybrid was best in every
configuration; semantic recall rose almost linearly with chunk size (the size confound that
motivated the size-matched baseline here).

## 7. Environment notes (Ziheng's Windows laptop)
Windows 11, Anaconda, PowerShell, RTX 3050 Ti (4 GB): `--batch-size 16` (8 if out of
memory). Smart App Control blocked some unsigned DLLs (turned off). `conda activate` did not
switch envs in PowerShell; workaround: call the env's python.exe directly. Folder in OneDrive:
pause sync if Qdrant/cache files hit PermissionError. Interrupted runs resume from caches.
A new code folder needs `emb_cache/` copied in (otherwise everything is re-embedded); measured
speed ~7-8 chunks/s for ~110-128-token chunks, ~2.3 chunks/s for 512-token chunks (batch 16).
Two runs can't share `qdrant_exp1/` at once; queue them (PowerShell `;`, or wait for the
previous results file with `while (!(Test-Path ...)) { Start-Sleep 60 }`). The laptop is
close to unusable during GPU runs.
**Before any long run: Settings -> Windows Update -> Pause updates (1 week)**; Windows Update
restarts the machine on its own (happened 14 Oct 06:59 during the dev run). Also keep the
charger in, sleep = Never, OneDrive sync paused.

## 8. Experiment 2 status (as of 6 Nov 2026; read from `ESP3201A_Exp2`, branch `master`)
A summary for Exp 1 people. If it disagrees with a source, the source wins. Sources:
`ESP3201A_Exp2/HANDOVER.md`, `ESP3201A_Exp2/results/exp2_results_tables.md` (final tables, Findings
list, Limitations), and `C:/Users/kwekt/ESP3201A_local/gitlab_runner_copy/HANDOVER.md` (GitLab Runner).
- **Question:** does a strict grounded prompt make a small local LLM answer "why was this changed?"
  faithfully, and say "Not found in the provided PRs" when the PR gives no reason?
- **Setup (frozen 22 Oct, unchanged):** pool A with the same-ticket filter (2,231 PRs), Exp 1 dense
  retriever (Qwen3-Embedding-0.6B, Exp 2 "why" instruction), Exp 1 `relations.expand_and_pack`,
  2,560-token budget, Exp 2 explanation links. Arms: F0 = fixed 512/77, alpha 0; S0 = structural
  cap 256, alpha 0; S0-G = structural, grouped by PR; S-0.25 = structural, alpha 0.25, grouped.
  Prompts v2 and v3 ("a WHAT is not a WHY"). Models qwen3:4b-instruct-2507-q4_K_M (4B) and qwen3:8b
  (8B), Ollama 0.40.4, temperature 0, seed 42, num_ctx 8192.
- **Questions:** 50 answerable test questions and 17 unanswerable: 5 no-reason test, 5 no-reason
  dev, 5 whole PR excluded, and rk16129 and rk9789 (answer removed, PR kept; case studies).
  rk11459 and rk12342 are dropped from every analysis. 15 unanswerables (without nr9172 and nr13883,
  which have contextual clues) is a sensitivity.
- **Correctness labels:** blind Codex labels, with Alyssa as the independent human reference rater on
  80 rows (1 Nov). Replaces the 24 Oct "correctness not yet measured" status; the human tasks listed
  then are done. Rules: no arm is called best unless it wins a test with Holm p < 0.05 in its family.

**The final Findings (9; signed off by the owner 1 Nov, Finding 9 on 5 Nov):**
1. No arm or prompt difference survives Holm in its family (smallest Holm p: primary 60 0.7635,
   contain 20 0.3125, correctness 40 1.0). Differences between arms are counts only.
2. 8B answers more unanswerable questions than 4B in every arm and prompt: 11-14 of 17 vs 2-7
   (15-question sensitivity: 9-12 vs 2-5). Counts only, no test.
3. Prompt v3 lowers 4B's unanswerable answers in every arm (F0 7->3, S0 7->4, S0-G 6->2, S-0.25
   7->5); 8B changes by 0-2. Unadjusted p 0.125-0.5; no single test reaches p < 0.05.
4. Correctness (Codex): strict 19-30 of 50 (4B) and 21-27 (8B); lenient 29-38 and 34-40. Codex vs
   Alyssa (n = 80): kappa 0.675 [0.511, 0.816]. Codex is stricter on correct vs partial (9 of 13
   disagreements), so strict rates may run low.
5. Sentence-level support (MiniCheck cited min, mean per stratum) is 0.36-0.68, highest for F0 in
   every model x prompt. A support proxy, not the right reason, and not comparable across chunkings
   (mean context chunk 396 vs 92 Exp 1 units).
6. Gate at 0.5 keeps 301/659 answered answerables, 229/453 overlap-cited answers and 59/141
   unanswerable answers. Threshold set in planning, rule file committed after the faithfulness
   results (P1).
7. Discrimination (AUROC, unanswerable answers as positives) vs all answered answerables: MiniCheck
   0.538 [0.437, 0.656] (4B), 0.572 [0.468, 0.673] (8B); HHEM 0.669 [0.563, 0.784], 0.732 [0.622,
   0.824]. HHEM above MiniCheck is a point-estimate difference with overlapping CIs; the gate keeps
   MiniCheck.
8. Arm W-F (whole-PR packing; exploratory): answer span in context on 10 fewer questions than F0
   (32 vs 42 of 50). No pre-declared W-F vs F0 test reaches p < 0.05.
9. Arm H0 (hybrid; proposed after the frozen results): gold PR in the top 5 PRs 47 vs 43 of 50, with
   no sign of the Exp 1 drop. No evidence of a reduction in hallucination (unanswerable answered
   7->8, 3->2, 13->12, 13->11). Strict correct rises in all four cells (21->32, 23->27, 23->31,
   21->29), but no test survives Holm in the hybrid 16 family (smallest Holm p 0.118). H0 labels
   come from a later Codex session and have no human validation.

**Transfer checks (exploratory, not in the Findings, never like for like with Django):**
- **SymPy (Clifton; section 8 of the results tables), 4B v3, 22 questions, counts only.** Django vs
  SymPy: F0 answered 35/50 vs 10/15, strict 23/50 vs 9/15, unanswerable answered 3/17 vs 4/7; S0-G
  answered 34/50 vs 14/15, strict 25/50 vs 8/15 (12/15 on upper labels), unanswerable answered 2/17
  vs 5/7. All 4 rater disagreements are on S0-G. Exp 1 fixed dense vs hybrid MRR@5: Django 0.937 vs
  0.876, SymPy 0.886 vs 0.802 (p = 0.007).
  H0 on SymPy, F0 rerun -> H0: span in context 12 -> 15, answered 9 -> 12 of 15, unanswerable
  answered 4 -> 4 of 7, strict 8 -> 11 of 15. Only 13 of 22 F0 answers are identical across GPUs with
  the same contexts, so small differences can be hardware noise. If SymPy PRs ever train LoRA, they
  cannot also be the test set.
- **GitLab Runner (James), pool A2000.** Labels are closing references, not SWE-bench. Scaled Exp 1,
  201 primary tasks, alpha 0 -> 1 (permutation primary): correct MR in budget 167 -> 155 (lost 12,
  gained 0; Holm 0.0020), precision 0.072 -> 0.088 (Holm 0.0216), F1 0.089 -> 0.110 (Holm 0.0036),
  recall 0.453 -> 0.480 (Holm 0.1653; Wilcoxon Holm 0.0218). Scaled Exp 2, F0 vs C1 (fixed 512/77,
  links alpha 1), 4B v3, 52 answerable + 8 no_reason + 10 removed, **provisional labels**: strict
  correct 33 vs 32 of 52 (primary, Holm 1.0), answered 43 vs 44, unanswerable answered 5 vs 3 of 18,
  lenient 40 vs 41. After the MiniCheck gate, answered 42 vs 37 and correct 32 vs 27 (counts only).
  The signed rule said Alyssa labels every row; the 87 labels are instead James's on 20 rows plus
  Codex's on 67. Raters are mixed within 12 of the 43 question pairs, and James and Codex agree poorly
  (kappa 0.177).

**Add-ons and context:**
- **LoRA fine-tune:** stopped at Step 0 and framed as future work unless the owner says otherwise.
  The 8B now fits in memory at 4096 tokens (peak 9.78 GiB; synthetic text, 3 steps, not a real training
  run). Training data, GGUF export and the base-pipeline control are undone, and Django pool A has
  0 of 103 eligible PRs left.
- **PR length (`pr_length.py`, Exp 1 units):** pool A median 729, p90 3,344, max 46,989; 325 PRs >
  2,560. Gold PRs (60 rows): median 1,370, p90 3,271, max 3,784; 17 of 60 > 2,560.
- **Prof consultation (24 Oct):** show how hallucination is reduced, not just measured; asked "is
  chunking worth it?"; wants a demo. Arm W-F and the app respond to the last two. The stretch ideas
  from then (per-PR rationale card, long-PR question set) have no recorded run in these sources.

**Still open:**
1. Alyssa's full review of the 87 scaled GitLab Runner rows; re-run `stats` on her labels if they
   differ meaningfully. Everything from that run is provisional until then. Don't re-run
   `exp2_gitlab_scale.py score`: it renumbers the blind ids.
2. Stronger hallucination test, H0 vs F0 on new questions (`tuning_rule_hallucination_test.md`): a
   draft, uncommitted, nothing run. Target, raters and deadline fit are undecided.
3. Demo gate toggle (queue d): waits on the group confirming the plan.
4. SymPy `nr17375`: dropped before generation by Alyssa's check, but
   `outputs/2026-11-05_question_check_review/` marks it correct. Open for the group.

## 9. Demo app (`app/`, built by Alyssa, Nov 2026)
Local chat UI ("PR Explainer") over the Exp 1 retrieval code + Exp 2 prompts. Read
`app/README.md` first. Nothing in `app/` changes experiment code or results.
- **Run:** `python app/server.py` -> http://127.0.0.1:8000, or the desktop window
  `pythonw app/desktop.py` (pywebview; starts Ollama if needed, runs the server in-process).
  Needs Ollama with `qwen3:4b-instruct-2507-q4_K_M`, and for dense `emb_cache/` +
  the Qwen3-Embedding-0.6B model in the Hugging Face cache (the app forces HF offline).
- **Final settings** (`app/final_settings.json`, `finalized: true`): dense, fixed 512/77,
  Exp 1 **code** links (alpha 1 pool A / 0.5 pool H, `engine.ALPHAS`), budget 2,560,
  qwen3 4B, strict grounded prompt v3. Wording agreed: retrieval and links are backed by
  significant Exp 1 results; the rest is chosen, not proven best. **Limitation:** this exact
  combination was never evaluated end to end on Django (Exp 2's fixed arm F0 used alpha 0). Arm C1
  ran it on GitLab Runner only, on provisional labels (section 8). Since 6 Nov Django's search uses
  Exp 2's frozen instruction (`engine.why_task`). With links off, the app's contexts equal Exp 2's
  F0/v3 on all 50 answerables (only 13 of 50 with the earlier wording).
  Set `finalized: false` for experiment mode (all toggles, nothing presented as final).
- **"Not found"** uses Exp 2's strict rule (only the refusal sentence counts).
- **Known behaviour:** the 4B over-abstains on some answerable questions (e.g. the
  LiveServerThread port question: right PR retrieved, model says not found) and still answers
  some no-reason questions (collectstatic verbosity, JavaScriptCatalog UTF-8). This matches
  Exp 2; don't change settings to make demo questions look good.
- **Demo questions** were picked by running Exp 2 test questions through the final setup
  AFTER the experiments. That check is for choosing demo examples only, never a result.
  Working examples: AutoField get_prep_value (quotes the commit message), Selenium waits on
  GitHub Actions, DatabaseWrapper thread-sharing lock, CharField empty values, Enum PY311 flag.
- **Ollama version:** Exp 2 ran on 0.40.4; Alyssa's laptop has 0.33.3, so answers can differ
  slightly from Exp 2's.
- **One process at a time:** local Qdrant (`qdrant_app/`) can only be opened by one program.
  Don't run the browser server and the desktop app (or two servers) together.
- **UI pieces:** streamed answers (`/api/ask_stream`), citations open a whole-PR viewer
  (`/api/pr/<n>`, read-only; uncited PRs listed as "read, not cited"), resizable viewer,
  automatic compact layout under 820 px, Aa text size, chats stored per browser/app
  (localStorage). `window.confirm/alert` are not used.
- **Repositories (6 Nov 2026):** the app also answers on `sympy/sympy` and
  `gitlab-org/gitlab-runner`, with Django's settings unchanged (`engine.REPOS`, `app/README.md`).
  Exploratory only: neither was tuned, and neither is in the Exp 2 Findings. Their data is in
  `prs/` and `emb_cache/`. Don't move them onto `pr_document.py`: their embeddings were made
  with `app/pr_document_transfer.py`, so its output must stay the same. Experiment code in this
  folder's root is unchanged.

## Progress log
- 11-12 Oct 2026: QASPER/MultiHop pipeline (BM25, dense, hybrid, tuning) built and tuned.
- 12 Oct 2026: switched to code review. Code adapted to SWE-bench Verified Django PRs;
  QASPER/MultiHop code and data deleted (agreed); split made; BM25 self-test and fake-data
  end-to-end test passed.
- 12-13 Oct 2026: all 231 fixing PRs downloaded (all merged on GitHub). Pool A chosen; 2,231
  PRs downloaded. BM25 pilot (5 dev tasks) ran; found 1% of PRs = 78% of text (accidental
  branch merges) -> pool size filter added (28 excluded, top-up pending). Dropped the
  1-file/multi-file breakdown. Next: download the replacements, rerun the pilot.
- 13 Oct 2026: replacements downloaded (28 excluded, 2,000/2,000 eligible). Found a local-mode
  Qdrant bug: delete + re-create of a collection under the SAME name (in a new session) keeps
  the old points, so searches returned PRs from the unfiltered pool. Fix: every collection name
  now includes the chunk-set hash, plus a point-count check after indexing. If you ever see
  "has N points but there are M chunks", delete the `qdrant_exp1` folder and re-run.
  Filtered pool, structural cap 512: 30,336 chunks (29,818 unique) -> ~2.1 h dense on GPU.
- 14 Oct 2026, 01:40: Ziheng ran the dense pilot (5 dev tasks, fixed 256): pipeline works with all
  three retrievers; numbers in section 5. Dev tuning run started next.
- 14 Oct 2026, 06:59: dev tuning run interrupted by a Windows Update restart after ~5 h (4 of 8
  chunk settings embedded). Updates paused for 1 week; run restarted ~10:45 from the cache.

- 14 Oct 2026, 11:15: added reuse of complete Qdrant indexes (results unchanged, ~2 h faster on
  resume); dev run restarted with it.

- 14 Oct 2026, 13:14: crash on a locked cache file (Windows) after fixed_s256_o38 was embedded;
  cache save/load made robust (retry + tmp recovery); run restarted ~15:20.
- 14 Oct 2026, 18:00: dev tuning run complete; chosen fixed 512/77 and structural cap 256
  (BM25 defaults). Settings recorded before any test run. Waiting for group agreement.
- 19 Oct 2026: relation factor (code links, alpha) + fixed 2,560-token budget added before
  the test run (group request); dev chunk settings unchanged. Waiting for the dev alpha run
  with all three retrievers.
- 19 Oct 2026 (later): decided with the group:
  * Option B safety rule for alpha (select_chunking.py --gold-tol 0.02): alpha > 0 only if the
    fixing PR stays in the token budget at most 2 points (1 task in 50) less often than with
    no links. BM25-only dev check: no alpha passes for BM25.
  * Alpha is chosen PER chunking x retriever (it is applied after the search, so chunks stay
    identical); runner option --alpha-map fixed.dense=0.5 ... (each run next to alpha 0).
  * Same-ticket filter (pool A and H): distractors whose title names the same Trac ticket as
    a fixing PR are excluded (16 in pool A) and replaced. Needs a download run (16 PRs).
    NOTE: dev chunk tuning was done on the pool before this filter (16 of 2,231 PRs differ).
  * Pool H (hard, second test condition, RETUNED on dev): fixing PRs + 2,000 distractors that
    look like fixes (merged, touch tests/, title "Fixed #N"/"Refs #N") from the same area of
    code (module = first 3 path parts, e.g. django/db/models). ~9 per fixing PR. Fallback
    order fixed in advance: 1 same module + look-alike, 2 neighbouring module (parent folder)
    + look-alike, 3 same module any PR (tier 3 only once candidates run out). Size and
    same-ticket filters apply. Tier counts are saved in the pool file and results meta.
    Build: `python github_prs.py download --pool H --n-distractors 2000` (token; up to ~4 h,
    resumable). Then dev tuning with --pool H (chunk grid + alpha grid), select, test.
- 20 Oct 2026: v3 code (same-ticket filter, pool H, token budget + links) set up on Ziheng's
  laptop; emb_cache copied from the old folder. Pool A dev chunk grid re-run (23:20) -> same
  choices (fixed 512/77, struct 256).
- 21 Oct 2026: pool A alpha grid (00:08); pool H dev chunk grid (14:07, ~13 h) -> fixed 512/77,
  struct 256; pool H alpha grid (17:08). Alphas differ between pools (fragile with 50 tasks).
- 22 Oct 2026: group locked the settings (chunks + alpha per pool) before any test run.
- 23 Oct 2026: all four test runs done (pool A tuned 01:47 / untuned 04:03; pool H tuned 07:29 /
  untuned 10:51) + stats.py for both pools. Experiment 1 complete; results summarised in
  section 5.
- 24-25 Oct 2026: prof consultation (reduce hallucination, LLM-wiki idea, "is chunking worth it",
  demo). Teammate review of the Exp 1 test summary (corrections in section 5). Exp 2 state read
  from `ESP3201A_Exp2_2410` and summarised in section 8; Ziheng given the blind validation labels
  (80 rows) and gate-pass tags (10 rows).
- 2-5 Nov 2026 (Alyssa): demo app `app/` finished (see section 9): final settings filled in,
  chat UI, streaming, PR viewer, desktop window. No experiment code or results changed.
- 6 Nov 2026: app extended to SymPy and GitLab Runner (section 9), Django embeddings added to
  `emb_cache/`, and this file merged with the fuller copy in `ESP3201A_SWE_exp1_2510`.
- 6 Nov 2026: section 8 rewritten with the final Exp 2 Findings, the SymPy and GitLab Runner checks,
  and what is still open.
