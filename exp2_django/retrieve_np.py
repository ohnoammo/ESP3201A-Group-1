"""Read-only dense retriever over Exp 1's frozen fixed 512/77 chunks (stand-in for Clifton's
wrapper; same interface, so his can drop in).

    from retrieve_np import retrieve, get_chunks
    retrieve("why ...?", k=5, exclude_prs=[14349, 14359])
      -> [{rank, score, pr_number, chunk_id, chunk_type, file_path, start, end, text}, ...]
    get_chunks(14349) -> all fixed 512/77 chunks of PR 14349, in order

    python retrieve_np.py --build      # build/verify the local index (outside OneDrive)
    python retrieve_np.py --check      # re-embed a chunk sample and compare with the Exp 1 cache

Settings are in retrieval_config.json. Document vectors come from Exp 1's embedding cache (a
COPY outside OneDrive; the Exp 1 folder and qdrant_exp1/ are never opened for writing). The
search is exact: cosine = dot product of L2-normalised vectors over all 8,846 chunks, so the
ranking equals an exact (non-HNSW) Qdrant cosine search. start/end are character offsets into
pr_document.build_document(pr)["text"].
"""
import hashlib
import json
import os
import sys

import numpy as np

from common import HERE, EXP1_CHUNK_CACHE, chunks, pool_numbers

with open(os.path.join(HERE, "retrieval_config.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)
INDEX = os.path.join(CONFIG["index_dir"], f"index_{CONFIG['chunking']}.npz")

_state = {}


def _key(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def build():
    """Collect the pool's chunks, check them against Exp 1's chunk cache, look up every
    chunk's Exp 1 embedding, and save matrix + metadata locally."""
    meta = [c for n in pool_numbers() for c in chunks(n)]
    with open(EXP1_CHUNK_CACHE, encoding="utf-8") as f:
        exp1 = json.load(f)["chunks"]
    mine = [(c["chunk_id"], c["start"], c["end"], c["text"]) for c in meta]
    theirs = [(c["chunk_id"], c["start"], c["end"], c["text"]) for c in exp1]
    if sorted(mine) != sorted(theirs):
        raise RuntimeError("chunks differ from Exp 1's chunk cache")
    print(f"{len(meta)} chunks, identical to Exp 1's cache")
    with np.load(CONFIG["emb_cache_copy"]) as d:
        lookup = dict(zip(d["keys"].tolist(), range(len(d["keys"]))))
        missing = [c["chunk_id"] for c in meta if _key(c["text"]) not in lookup]
        if missing:
            raise RuntimeError(f"{len(missing)} chunks have no cached embedding, e.g. {missing[:3]}")
        emb = d["emb"][[lookup[_key(c["text"])] for c in meta]].astype(np.float32)
    norms = np.linalg.norm(emb, axis=1)
    print(f"embeddings {emb.shape}, norm min {norms.min():.4f} max {norms.max():.4f}")
    emb /= norms[:, None]
    keep = ("chunk_id", "pr_number", "chunk_type", "file_path", "start", "end")
    os.makedirs(CONFIG["index_dir"], exist_ok=True)
    np.savez(INDEX, emb=emb, meta=np.array(json.dumps([{k: c[k] for k in keep} for c in meta])))
    print(f"saved {INDEX}")


def _load():
    if "emb" not in _state:
        if not os.path.exists(INDEX):
            build()
        with np.load(INDEX) as d:
            _state["emb"] = d["emb"]
            _state["meta"] = json.loads(str(d["meta"]))
        _state["pr"] = np.array([m["pr_number"] for m in _state["meta"]])
        _state["texts"] = {}
    return _state


def _model():
    if "model" not in _state:
        import torch
        from sentence_transformers import SentenceTransformer
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        m = SentenceTransformer(CONFIG["embedding_model"], device=dev,
                                revision=CONFIG["embedding_model_revision"],
                                processor_kwargs={"padding_side": "left"})
        if dev == "cuda":
            m.half()
        m.max_seq_length = CONFIG["max_seq_length"]
        _state["model"] = m
    return _state["model"]


def embed_queries(texts):
    prompt = f"Instruct: {CONFIG['query_instruction']}\nQuery:"
    return np.asarray(_model().encode(list(texts), prompt=prompt, normalize_embeddings=True,
                                      convert_to_numpy=True), dtype=np.float32)


def _text(pr, chunk_id):
    s = _load()
    if chunk_id not in s["texts"]:
        for c in chunks(pr):
            s["texts"][c["chunk_id"]] = c["text"]
    return s["texts"][chunk_id]


def retrieve(query, k=5, exclude_prs=(), chunking="fixed_s512_o77", retriever="dense",
             query_vec=None):
    if chunking != CONFIG["chunking"] or retriever != "dense":
        raise NotImplementedError("stand-in supports dense + fixed_s512_o77 only")
    s = _load()
    q = embed_queries([query])[0] if query_vec is None else query_vec
    scores = s["emb"] @ q
    if exclude_prs:
        scores = np.where(np.isin(s["pr"], list(exclude_prs)), -np.inf, scores)
    top = np.argsort(-scores, kind="stable")[:k]
    out = []
    for rank, i in enumerate(top, 1):
        m = s["meta"][i]
        out.append(m | {"rank": rank, "score": float(scores[i]),
                        "text": _text(m["pr_number"], m["chunk_id"])})
    return out


def get_chunks(pr_number):
    return chunks(pr_number)


def check(n=64, seed=0):
    """Re-embed a random sample of chunks here and compare with Exp 1's cached vectors."""
    s = _load()
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(s["meta"]), size=n, replace=False)
    texts = [_text(s["meta"][i]["pr_number"], s["meta"][i]["chunk_id"]) for i in idx]
    mine = np.asarray(_model().encode(texts, normalize_embeddings=True, batch_size=8,
                                      convert_to_numpy=True), dtype=np.float32)
    cos = (mine * s["emb"][idx]).sum(1)
    print(f"re-embedded {n} chunks: cosine to Exp 1 vectors min {cos.min():.5f}, "
          f"mean {cos.mean():.5f}")
    return cos


if __name__ == "__main__":
    if "--build" in sys.argv:
        build()
    if "--check" in sys.argv:
        check()
