# exp1_retrieval: Experiment 1, retrieval only (Django, SWE-bench Verified, pools A and H)

> **Submission notes.** This block was added for the submission. The original README follows below it, unchanged.
>
> - **Source.** `ESP3201A_SWE_exp1_app` at `4a77349`, without `app/`, which is now `../app`. This is the final v3 Exp 1 code (with `relations.py`, pools A and H, test runs from 23 Oct). Its code and results are byte-identical to `ESP3201A_SWE_exp1_2510` and `ESP3201A_SWE_exp1_0111/…_v3`.
> - **Research question.** RQ1: which chunking (fixed vs structural) and retriever (BM25 / dense / hybrid RRF) best finds the fixing PR for a bug report? Tuned on dev (50 tasks) and run once on test (181 tasks).
> - **Run.** `pip install -r ../requirements.txt`, then follow "Run steps" below. Quick check: `python sparse_retrieval.py --selftest`.
> - **Caches to regenerate.** None of `prs/`, `chunks/`, `emb_cache/` or `qdrant_exp1/` are in the repo. Rebuild them with `github_prs.py index / fixing / download` (GitHub token in your terminal only), then the first `run_retrieval_swe.py` run. The demo app (`../app`) also keeps its own `qdrant_app/`, `prs/` and `emb_cache/` here.
> - **Which file holds which number:**
>   - **Pool A test, tuned:** dense fixed 512/77 has Hit@5 0.978 [0.956, 0.994] and MRR@5 0.937 [0.909, 0.963]. File: `results/stats_test_poolA_full.txt`.
>   - **Pool H (hard distractors):** `results/stats_test_poolH_full.txt`.
>   - **Per-query rows:** `results/swe_exp1_test{,H}_{tuned,untuned}_per_query.csv`.
>   - **Dev tuning:** `results/swe_exp1_dev*.csv` and `results/selection_log.txt`.
> - **Post hoc test** (added after the test results were seen; labelled post hoc in the report). `posthoc_links_test.py` compares budget line recall with relation links: structural vs size-matched fixed, and structural vs fixed 512/77. It runs on dense retrieval over both pools, using each condition's locked alpha and a paired permutation test (10,000 draws, seed 0, unadjusted). It reads only the per-query test CSVs and uses the standard library only. Run it from this folder with `python posthoc_links_test.py > results/posthoc_links_test.txt`.
>   - Pool A: 0.924 vs 0.923 vs 0.763. Structural vs size-matched p 0.0001; structural vs fixed 512 p 0.94.
>   - Pool H: 0.858 vs 0.890 vs 0.698. Structural vs size-matched p 0.0001; structural vs fixed 512 p 0.078.

---

# Experiment 1: retrieval over Django pull requests (SWE-bench Verified)

Local, offline RAG assistant over **code review data**: 1 PR = 1 document (title, description,
commit messages, diff, review + conversation comments). Experiment 1 tests retrieval only (no
LLM): **chunking (fixed vs structural) x retrieval (BM25 / dense / hybrid)** = 6 combinations.

- **Query** = a SWE-bench Verified bug report (`problem_statement`); optional second query set
  = its first line only (`--query-sets full short`, reported separately).
- **Correct answer** = the PR that fixed the bug (number at the end of `instance_id`).
- **Data**: `django/django`, 231 tasks, split **dev 50** (tuning only) / **test 181** (final, run
  once). `--repo` is a setting so sympy / sphinx can be added later.

## Files
| File | What it does |
|---|---|
| `swebench_loader.py` | Loads SWE-bench Verified (Hugging Face) for one repo |
| `make_swe_split.py` | Reproducible dev/test split (SHA-256, no RNG) -> `swe_split_ids.json` + fingerprint |
| `github_prs.py` | GitHub download + cache (`prs/<repo>/<n>.json`): `index`, `fixing`, `size-check`, `download` |
| `pr_document.py` | One PR -> one text with character spans for every part; bots removed; changed-line evidence; copied-text check |
| `chunking.py` | `fixed_size_chunks` (tokens) and `structural_chunks` (one chunk per PR part, size cap) |
| `sparse_retrieval.py` | BM25: code-aware tokenizer + own TF vectors -> Qdrant `Modifier.IDF`; `--selftest` |
| `dense_retrieval.py` | Qwen3-Embedding-0.6B + Qdrant (cosine), on-disk cache; RRF hybrid |
| `metrics.py` | PR-level Hit@5 / MRR@5 (main); chunk-level Hit/MRR + line-level Recall/Precision/F1 |
| `exp1_common.py` | Chunk configs + chunk cache, builds the 3 retrievers, saves results |
| `run_retrieval_swe.py` | The experiment (all combinations, both query sets, breakdowns, per-query CSV) |
| `select_chunking.py` | Applies the pre-registered tuning rule to the dev results |
| `stats.py` | Bootstrap 95% CIs, McNemar (Hit@5), paired permutation + bootstrap (MRR@5, budget recall) |
| `relations.py` | Relation factor: links between chunks of one PR + packing into the token budget |

Generated: `prs/` (PR cache), `chunks/`, `emb_cache/`, `qdrant_exp1/`, `results/`.

## Setup
```
pip install -r requirements.txt          # or: conda env create -f environment.yml
python sparse_retrieval.py --selftest    # BM25 check: Qdrant scores = reference BM25
```
GitHub token (needed only for downloading): create a fine-grained or classic token with
public-repo read access, then set it **in your own terminal** (never in a file or a chat):
```
$env:GITHUB_TOKEN = "<token>"            # PowerShell
export GITHUB_TOKEN=<token>              # bash
```

## Run steps
```
python make_swe_split.py                              # fingerprint b57872f8e804ec6b
python github_prs.py index                            # list all Django PRs (~200 requests)
python github_prs.py fixing                           # download the 231 fixing PRs + their state
python github_prs.py size-check                       # pool B (1y / 6m / 3m) vs pool A sizes, time
python github_prs.py download --pool A --n-distractors 2000   # chosen pool (B was too slow)
python github_prs.py pool-check --n-distractors 2000          # size filter status, no token

# pilot: 5 dev tasks, small pool A, end to end, all 6 combinations
python github_prs.py download --pool A --n-distractors 200
python run_retrieval_swe.py --split dev --max-tasks 5 --pool A --n-distractors 200 --tag _pilot

# tuning on dev (50 tasks)
python run_retrieval_swe.py --split dev --pool A --n-distractors 2000 --fixed-sizes 128 256 512 \
    --overlap-fracs 0 0.15 --struct-caps 256 512 --query-sets full short --tag _dev
python select_chunking.py results/swe_exp1_dev.json   # chunk settings + prints the alpha run

# relation factor on dev (chosen chunk settings only; re-ranking only, no new embeddings)
python run_retrieval_swe.py --split dev --pool A --n-distractors 2000 --fixed-sizes 512 \
    --overlap-fracs 0.1504 --struct-caps 256 --alphas 0 0.25 0.5 1 --tag _dev_alpha
python select_chunking.py results/swe_exp1_dev.json results/swe_exp1_dev_alpha.json
                                                      # prints the two final test commands

# final test runs (each ONCE): tuned (printed above) and untuned defaults
python run_retrieval_swe.py --split test --size-matched --query-sets full short --tag _test_untuned
python stats.py results/swe_exp1_test_tuned_per_query.csv results/swe_exp1_test_untuned_per_query.csv
```
Add the pool options (`--pool A --n-distractors N` or `--pool B --window-days W`) to every
`run_retrieval_swe.py` command if you don't use the default pool B / 365 days.

## Parameters
| Setting | Default (untuned) | Tuned on dev |
|---|---|---|
| Fixed chunks | 256 tokens, no overlap | size 128 / 256 / 512 x overlap 0 / 15% |
| Structural chunks | size cap 512 tokens | cap 256 / 512 |
| BM25 | k1 = 1.2, b = 0.75, code-aware tokenizer | not tuned (decided: standard defaults; with 50 dev tasks the effect of k1/b is below the noise) |
| Dense | Qwen3-Embedding-0.6B, task instruction for queries, max 1024 tokens | not tuned |
| Hybrid | RRF, k = 60, top 100 from each retriever | not tuned |
| k | 5 (depth 100 chunks, collapsed to PRs) | not tuned |
| Copied-text check | n = 10 consecutive words (counts at 8 / 10 / 12 in `meta`) | - |
| Token budget (what an LLM receives) | 2,560 tokens (= 5 x fixed-512 chunks), same for every method | not tuned |
| Relation factor alpha | 0 (no links) | 0 / 0.25 / 0.5 / 1, per chunking method |
| Pool A size filter | > 100 files or > 50,000 tokens excluded (`--max-files`, `--max-tokens`) | - |

"Tokens" = words and single punctuation symbols (`\w+|[^\w\s]`), independent of any retriever.
`--size-matched` adds a fixed-size run whose size = the structural chunks' average.

## Design notes and caveats (for the report)
- **Token budget + relation factor** (`relations.py`). What an LLM would receive is measured
  as a fixed **token budget** (2,560 tokens), not "top 5 chunks": chunk sizes differ ~4x
  between methods, so "top 5" hands big-chunk methods more text. After the (unchanged)
  search, each retrieved chunk can bring in **linked code chunks of the same PR**:
  description/commits -> its hunks; review thread -> the hunk it comments on (line match,
  else same file); hunk -> the PR's other hunks (same file nearest first); fixed chunks ->
  the chunks just before/after. Score: a chunk at rank r = 1/(60+r); a chunk linked from
  rank r = alpha/(60+r); everything is sorted and packed into the budget, so links only get
  in by pushing out lower-scored chunks. alpha = 0 = no links. Experiment 1 uses only links
  that add CODE (comments contain no changed lines, so the metric can't reward them);
  links that add explanations (hunk -> its review thread / description, `kinds=("context",)`)
  are for Experiment 2. PR-level Hit/MRR are computed on the plain ranking (alpha has no
  effect on them); `budget_*` columns are computed on the packed chunks. `gold_in_budget`
  checks that links never push the fixing PR out; `top5_distinct_prs` = how many different
  PRs the top-5 chunks come from.
- **Pools.** B (follows Huang et al., ICSE 2026, issue-commit linking): candidates for each bug
  = PRs created within the window after the bug date (bug date ~ fixing PR's `created_at`),
  via a date filter that every retriever gets. A: one shared pool (fixing PRs + N others from
  the same period). Django often closes fixing PRs without "merging" them (commits land
  directly), so pools are not filtered on merged state; `github_prs.py fixing` reports it.
- **BM25 IDF is computed over the whole collection, not each filtered pool** (Qdrant's IDF
  modifier ignores filters). The same holds for every query, so comparisons stay fair.
- **PR document**: fixed order; bot comments removed (`user.type == "Bot"`, `[bot]` logins,
  a small list of CI bots); nothing else stripped. Every part has a character span, so
  structural chunks and the evidence share one coordinate system.
- **Evidence** for line-level metrics = every changed (`+`/`-`) line in the fixing PR's own
  diff (source + tests + docs); `src_*` columns use only files in SWE-bench's `patch`. A line
  counts as retrieved if >= 50% of it is covered (same rule as the earlier sentence metric).
- **Copied-text check**: fixing PRs sharing >= n consecutive lowercased words with their bug
  report are flagged; every table has `copied` / `not_copied` groups.
- **No 1-file vs multi-file breakdown**: only 22/181 test tasks change more than one source
  file (SWE-bench `patch`), too few for a reliable comparison. Reported descriptively: 159/181
  (88%) change a single source file (`n_single_source_file` in the results meta).
- **Pool A size filter**: PRs with > 100 changed files or > 50,000 tokens are left out of the
  pool (accidental branch merges such as "Stable/3.0.x" with 951 files; before filtering, 1%
  of the pool held 78% of all text). The pool is topped back up to 2,000 with the next PRs in
  the same fixed order. No fixing PR is near the limits (max 20 files, 9,977 tokens). Only
  pool membership changes, never PR content. Counts are in the pool file and results meta.
- **Selection rule** (`select_chunking.py`, fixed before any test run): PR MRR@5 averaged over
  the 3 retrievers (BM25 at k1 1.2 / b 0.75) picks the chunk settings. BM25 k1/b are NOT
  tuned (the script's k1/b step keeps the defaults when no k1/b grid was run).
  Ties -> higher Hit@5 -> smaller setting.
- **Statistics** (`stats.py`): 95% bootstrap CIs (1,000 resamples of queries); McNemar exact
  test for Hit@5; paired permutation test (10,000) + paired bootstrap CI for MRR@5.
  Non-significant differences are reported as such.
