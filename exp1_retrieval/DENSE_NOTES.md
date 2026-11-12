# Dense retrieval + hybrid notes (Experiment 1, SWE-bench / Django PRs)

Run steps and parameters: `README.md`. The dense METHOD is unchanged from the QASPER work.

## Dense (`dense_retrieval.py`)
- Model `Qwen/Qwen3-Embedding-0.6B` via sentence-transformers, L2-normalised, Qdrant cosine,
  named vector `"dense"`, fp16 on GPU.
- Queries get a task instruction, chunks don't (how Qwen3-Embedding is trained):
  `Instruct: Given a bug report for a software project, retrieve parts of pull requests
  (description, code changes, review comments) that fix the bug\nQuery:<bug report>`.
- Same payload as BM25 (`sparse_retrieval.PAYLOAD_KEYS`) and the same optional Qdrant filter
  (pool B date window), so both retrievers see identical candidate pools.
- `max_seq_length` 1024: truncated **chunks and queries** are counted and saved in the results
  `meta` (`truncated_chunks`, `truncated_queries`). Bug reports can be long, so check these.
- Separate embedding cache: `emb_cache/qwen3-embedding-0.6b_swe.npz` (resumable).
- Changed vs QASPER: new instruction, full payload, generic filter (`qfilter`) instead of the
  per-paper filter, query truncation count. `dense_retrieval_pr.py` (an earlier draft) was
  merged in and deleted.

## Hybrid
Python RRF (`rrf_fuse`, Cormack et al. 2009): score = sum over {BM25, dense} of 1/(60 + rank),
over each retriever's top 100 (deeper than before, because chunks are collapsed to PRs for the
PR-level metrics). Ranks only, so BM25 and cosine scores never need rescaling.

## Running dense on a laptop
Embedding cost ~ number of chunks in the pool (pool B 1-year windows could be tens of
thousands of chunks): the cache makes it a one-off. Use `--batch-size 16` (8 if CUDA runs out
of memory) and `--device cpu` to force CPU. `--retrievers bm25` runs without torch at all.
