"""Dense retrieval with Qwen3-Embedding + Qdrant (same shape as sparse_retrieval.py),
plus Reciprocal Rank Fusion (RRF) for hybrid BM25 + dense.

Pipeline (mirrors the BM25 one so results are directly comparable):
    chunks -> Qwen3Embedder.embed_documents -> Qdrant collection (cosine) -> search_dense
Chunks carry the same payload as in the BM25 collection (sparse_retrieval.PAYLOAD_KEYS:
chunk_id, paper_id, pr_number, chunk_type, file_path, created_ts, text, start, end), and both
retrievers take the same optional Qdrant filter (pool B date window), so they always search
identical candidate pools.

Qwen3-Embedding is an instruction-aware model: QUERIES get a one-line task instruction
("Instruct: ...\nQuery:"), DOCUMENTS (chunks) are embedded as plain text. This is how the
model was trained (see the Qwen3-Embedding model card).
"""
import hashlib
import os
import time

import numpy as np
from qdrant_client import models

from sparse_retrieval import to_point_id, payload, add_payload_indexes

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"

# One task instruction per dataset (Qwen recommends a task-specific instruction for queries).
TASKS = {
    "swe": "Given a bug report for a software project, retrieve parts of pull requests "
           "(description, code changes, review comments) that fix the bug",
}


def _key(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# ---------- 1. Embedding model (with an on-disk cache) ----------
class Qwen3Embedder:
    """Wraps a sentence-transformers Qwen3-Embedding model.

    embed_documents(texts) -> (n, d) float32, L2-normalised. Results are cached on disk by
        the SHA-1 of each text, so re-runs (and fixed vs structural chunks that happen to
        share text) never re-embed the same chunk. The cache is saved every `save_every`
        texts, so an interrupted run resumes where it stopped.
    embed_query(text) -> (d,) float32, with the task instruction prepended. Memoised in RAM.
    """

    def __init__(self, model_name=DEFAULT_MODEL, task=None, device=None, batch_size=None,
                 max_seq_length=1024, cache_path=None, save_every=1024):
        import torch
        from sentence_transformers import SentenceTransformer

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.model_name = model_name
        print(f"Loading {model_name} on {device} (first run downloads ~1.2 GB) ...")
        self.model = SentenceTransformer(model_name, device=device,
                                         tokenizer_kwargs={"padding_side": "left"})
        if device == "cuda":
            self.model.half()                       # fp16 on GPU: ~2x faster, same ranking
        self.model.max_seq_length = max_seq_length  # longer texts are truncated (counted below)
        self.batch_size = batch_size or (32 if device == "cuda" else 8)
        self.query_prompt = f"Instruct: {task}\nQuery:" if task else None
        self.cache_path = cache_path
        self.save_every = save_every
        self._doc_cache = self._load_cache()
        self._query_cache = {}
        self.n_truncated = 0                        # chunks longer than max_seq_length tokens
        self.n_truncated_queries = 0                # queries (incl. instruction) likewise
        self.embed_seconds = 0.0                    # time spent on NEW document embeddings

    # --- cache ---
    def _load_cache(self):
        """Load the newest readable cache file. The '.tmp.npz' file is normally swapped into
        the main file right after it is written, but if Windows refused the swap (file locked
        by OneDrive / antivirus), the tmp file holds the newest embeddings."""
        if not self.cache_path:
            return {}
        tmp = self.cache_path + ".tmp.npz"
        cands = sorted((p for p in (tmp, self.cache_path) if os.path.exists(p)),
                       key=os.path.getmtime, reverse=True)
        for path in cands:
            try:
                with np.load(path) as data:     # closes the file (Windows can't replace
                    cache = dict(zip(data["keys"].tolist(), data["emb"]))   # an open file)
            except Exception as e:              # e.g. a half-written tmp file
                print(f"WARNING: could not read {path} ({type(e).__name__}: {e}); "
                      f"trying the other cache file")
                continue
            print(f"Loaded {len(cache)} cached chunk embeddings from {path}")
            if path == tmp:                     # promote the newer tmp file
                self._replace_with_retry(tmp)
            return cache
        return {}

    def _replace_with_retry(self, tmp, tries=15, wait=2.0):
        """os.replace(tmp, cache) with retries: on Windows the target can be briefly locked by
        OneDrive sync or an antivirus scan (PermissionError, WinError 5 / 32)."""
        for _ in range(tries):
            try:
                os.replace(tmp, self.cache_path)
                return True
            except PermissionError:
                time.sleep(wait)
        print(f"WARNING: could not replace {self.cache_path} (locked by another program, e.g. "
              f"OneDrive or antivirus). The newest embeddings are kept in {tmp} and in memory; "
              f"the next save tries again, and a re-run loads the tmp file.")
        return False

    def _save_cache(self):
        if not self.cache_path or not self._doc_cache:
            return
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        tmp = self.cache_path + ".tmp.npz"
        keys = list(self._doc_cache)
        try:
            np.savez(tmp, keys=np.array(keys), emb=np.stack([self._doc_cache[k] for k in keys]))
        except PermissionError as e:            # tmp locked too: keep going, retry next save
            print(f"WARNING: could not write {tmp} ({e}); will retry at the next save")
            return
        self._replace_with_retry(tmp)           # atomic: never leaves a half-written cache

    # --- encoding ---
    def _encode(self, texts, query=False):
        kwargs = dict(batch_size=self.batch_size, normalize_embeddings=True,
                      convert_to_numpy=True, show_progress_bar=not query and len(texts) > 32)
        if query:
            if self.query_prompt:
                kwargs["prompt"] = self.query_prompt
            else:
                kwargs["prompt_name"] = "query"     # the model's built-in web-search instruction
        return np.asarray(self.model.encode(texts, **kwargs), dtype=np.float32)

    def embed_documents(self, texts):
        keys = [_key(t) for t in texts]
        todo = list({k: t for k, t in zip(keys, texts) if k not in self._doc_cache}.items())
        if todo:
            print(f"Embedding {len(todo)} new chunks ({len(texts) - len(todo)} cached) ...")
            tok = self.model.tokenizer
            for i in range(0, len(todo), self.save_every):
                part = todo[i:i + self.save_every]
                part_texts = [t for _, t in part]
                self.n_truncated += sum(len(ids) > self.model.max_seq_length
                                        for ids in tok(part_texts)["input_ids"])
                t0 = time.time()
                vecs = self._encode(part_texts)
                self.embed_seconds += time.time() - t0
                for (k, _), v in zip(part, vecs):
                    self._doc_cache[k] = v
                self._save_cache()
                print(f"  {min(i + self.save_every, len(todo))}/{len(todo)} embedded")
            if self.n_truncated:
                print(f"  note: {self.n_truncated} chunks exceeded "
                      f"{self.model.max_seq_length} tokens and were truncated")
        return np.stack([self._doc_cache[k] for k in keys]).astype(np.float32)

    def _count_truncated_queries(self, texts):
        prompt = self.query_prompt or ""
        ids = self.model.tokenizer([prompt + t for t in texts])["input_ids"]
        self.n_truncated_queries += sum(len(x) > self.model.max_seq_length for x in ids)

    def embed_query(self, text):
        if text not in self._query_cache:
            self._count_truncated_queries([text])
            self._query_cache[text] = self._encode([text], query=True)[0]
        return self._query_cache[text]

    def embed_queries(self, texts):
        """Batch-embed many queries up front (much faster than one at a time)."""
        new = list(dict.fromkeys(t for t in texts if t not in self._query_cache))
        if new:
            self._count_truncated_queries(new)
            for t, v in zip(new, self._encode(new, query=True)):
                self._query_cache[t] = v
            if self.n_truncated_queries:
                print(f"  note: {self.n_truncated_queries} queries exceeded "
                      f"{self.model.max_seq_length} tokens and were truncated")


# ---------- 2. Collection + upsert ----------
def build_dense_index(client, collection, chunks, embedder, batch_size=256):
    """chunks: chunk dicts (sparse_retrieval.PAYLOAD_KEYS). Same payload as the BM25
    collection, so results look identical to the evaluation code."""
    vecs = embedder.embed_documents([c["text"] for c in chunks])

    if client.collection_exists(collection):
        client.delete_collection(collection)
    client.create_collection(
        collection_name=collection,
        vectors_config={"dense": models.VectorParams(size=vecs.shape[1],
                                                     distance=models.Distance.COSINE)},
    )
    add_payload_indexes(client, collection)
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        client.upsert(
            collection_name=collection,
            points=[
                models.PointStruct(
                    id=to_point_id(c["chunk_id"]),
                    vector={"dense": v.tolist()},
                    payload=payload(c),
                )
                for c, v in zip(batch, vecs[i:i + batch_size])
            ],
        )
    return embedder


# ---------- 3. Search ----------
def search_dense(client, collection, embedder, query, k=5, qfilter=None):
    """Top-k chunks by cosine similarity. qfilter: optional Qdrant filter (the same one the
    BM25 search gets, e.g. sparse_retrieval.date_window_filter for pool B)."""
    hits = client.query_points(
        collection_name=collection,
        query=embedder.embed_query(query).tolist(),
        using="dense",
        query_filter=qfilter,
        limit=k,
        with_payload=True,
    ).points
    return [h.payload | {"score": h.score} for h in hits]


# ---------- 4. Hybrid: Reciprocal Rank Fusion ----------
def rrf_fuse(rankings, k=5, rrf_k=60):
    """Reciprocal Rank Fusion (Cormack et al., 2009): score(chunk) = sum over retrievers of
    1 / (rrf_k + rank). Uses ranks only, so BM25 and cosine scores need no normalising.
    rankings: list of ranked chunk lists (each chunk has a 'chunk_id')."""
    scores, chunk_by_id = {}, {}
    for ranking in rankings:
        for rank, c in enumerate(ranking, start=1):
            cid = c["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
            chunk_by_id.setdefault(cid, c)
    best = sorted(scores, key=lambda cid: (-scores[cid], cid))[:k]
    return [chunk_by_id[cid] | {"score": scores[cid]} for cid in best]


def make_hybrid_search(search_fns, depth=100, rrf_k=60):
    """Combine several search_fn(query, k, qfilter) into one hybrid search_fn.
    Each retriever returns its top-`depth` chunks (same filter), fused with RRF."""
    def hybrid_search(query, k, qfilter=None):
        rankings = [fn(query, max(depth, k), qfilter) for fn in search_fns]
        return rrf_fuse(rankings, k=k, rrf_k=rrf_k)
    return hybrid_search
