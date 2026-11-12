"""Shared pieces of Experiment 1 (used by run_retrieval_swe.py).

- Chunk configurations: "fixed_s{size}_o{overlap}" (fixed-size tokens, token overlap) and
  "struct_c{cap}" (structural chunks, size cap in tokens). Chunks are cached to chunks/*.json,
  so every retriever, every re-run and Experiment 2 see byte-identical chunks.
- build_retrievers(): builds the BM25 and/or dense collection for one chunk configuration and
  returns {retriever name: search_fn(query, k, qfilter)}. Hybrid = RRF of BM25 + dense.
"""
import csv
import hashlib
import json
import os
import statistics
import time

from chunking import fixed_size_chunks, structural_chunks, count_tokens
from sparse_retrieval import build_index, search_sparse, make_encoder
from dense_retrieval import build_dense_index, search_dense, make_hybrid_search

RETRIEVERS = ("bm25", "dense", "hybrid")


def chunk_configs(fixed_sizes=(256,), overlap_fracs=(0.0,), struct_caps=(512,),
                  chunkers=("fixed", "structural"), extra_fixed=()):
    """List of chunk configurations. overlap_fracs are fractions of the size (0.15 = 15%).
    extra_fixed: extra (size, overlap_tokens) pairs, e.g. the size-matched baseline."""
    cfgs, seen = [], set()

    def add_fixed(size, ov):
        size, ov = int(size), int(ov)
        if not 0 <= ov < size:
            raise ValueError(f"overlap {ov} must be >= 0 and < chunk size {size}")
        name = f"fixed_s{size}_o{ov}"
        if name not in seen:
            seen.add(name)
            cfgs.append({"name": name, "method": "fixed", "size": size, "overlap": ov})

    if "fixed" in chunkers:
        for size in fixed_sizes:
            for frac in overlap_fracs:
                add_fixed(size, round(size * float(frac)))
    for size, ov in extra_fixed:
        add_fixed(size, ov)
    if "structural" in chunkers:
        for cap in struct_caps:
            cfgs.append({"name": f"struct_c{int(cap)}", "method": "structural", "cap": int(cap)})
    return cfgs


def cfg_fields(cfg):
    """The configuration's parameters as flat result columns (blank where not applicable)."""
    return {"method": cfg["method"], "size": cfg.get("size"), "overlap": cfg.get("overlap"),
            "cap": cfg.get("cap")}


def size_stats(chunks):
    n = [count_tokens(c["text"]) for c in chunks] or [0]
    q = statistics.quantiles(n, n=10) if len(n) > 1 else [n[0]] * 9
    return {"n_chunks": len(chunks), "avg_tokens": sum(n) / len(n),
            "median_tokens": statistics.median(n), "p10_tokens": q[0], "p90_tokens": q[-1],
            "max_tokens": max(n),
            "avg_words": sum(len(c["text"].split()) for c in chunks) / max(1, len(chunks))}


def make_chunks(docs, cfg, dataset, cache_dir="chunks"):
    """Chunk every PR document with one configuration. Returns (chunks, info).
    Cached on disk; the cache name includes a hash of the PR ids + settings."""
    ids = "|".join(d["paper_id"] for d in docs)
    params = json.dumps({k: v for k, v in cfg.items() if k != "name"}, sort_keys=True)
    tag = hashlib.sha1((ids + params).encode()).hexdigest()[:8]
    path = os.path.join(cache_dir, f"{dataset}_{cfg['name']}_{len(docs)}docs_{tag}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"[{cfg['name']}] loaded {len(data['chunks'])} chunks from {path}")
        return data["chunks"], data["info"] | {"chunk_set": tag}

    t0, stats, chunks = time.time(), {}, []
    for d in docs:
        if cfg["method"] == "fixed":
            pcs = fixed_size_chunks(d["text"], size=cfg["size"], overlap=cfg["overlap"])
        else:
            pcs = structural_chunks(d, cap=cfg["cap"], stats=stats)
        for i, c in enumerate(pcs):
            chunks.append(c | {"chunk_id": f"{d['paper_id']}_{cfg['name']}_{i}",
                               "paper_id": d["paper_id"], "pr_number": d["pr_number"],
                               "created_ts": d["created_ts"]})
    info = size_stats(chunks) | {"chunk_seconds": time.time() - t0, "chunk_set": tag}
    if cfg["method"] == "structural":
        info["split_parts"] = stats.get("split_parts", 0)
        types = {}
        for c in chunks:
            types[c["chunk_type"]] = types.get(c["chunk_type"], 0) + 1
        info["chunk_types"] = types
    os.makedirs(cache_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"config": cfg, "info": info, "chunks": chunks}, f)
    print(f"[{cfg['name']}] {len(chunks)} chunks, avg {info['avg_tokens']:.0f} tokens "
          f"(median {info['median_tokens']:.0f}, p90 {info['p90_tokens']:.0f}), "
          f"{info['chunk_seconds']:.1f}s -> {path}")
    return chunks, info


_built_dense = set()          # dense collections already indexed in this run


def _reusable(client, col, chunks):
    """True if `col` already holds exactly one point per chunk, i.e. a complete index of this
    chunk set from an earlier (possibly interrupted) run. The name contains the chunk-set hash
    and point ids are deterministic (uuid5 of chunk_id), so a complete collection is identical
    to a rebuilt one; rebuilding it would only rewrite the same data (~30 min for a 30k-point
    dense collection in local mode). A partial or stale collection has a different count and
    is rebuilt as before. --rebuild-indexes forces a rebuild."""
    if REBUILD_INDEXES or not client.collection_exists(col):
        return False
    return client.count(col, exact=True).count == len(chunks)


REBUILD_INDEXES = False       # set by run_retrieval_swe.py --rebuild-indexes


def _check_count(client, col, chunks):
    n = client.count(col, exact=True).count
    if n != len(chunks):
        raise RuntimeError(f"Qdrant collection {col} has {n} points but there are {len(chunks)} "
                           f"chunks (stale data?). Delete the qdrant_exp1 folder and re-run.")


def build_retrievers(client, dataset, cfg_name, chunks, retrievers, embedder=None,
                     k1=1.2, b=0.75, bm25_kind="code", rrf_depth=100, rrf_k=60,
                     chunk_set=""):
    """Index one chunk configuration; return {name: search_fn(query, k, qfilter)}.
    One BM25 collection per (chunk set, k1, b); one dense collection per chunk set.
    chunk_set (make_chunks' info["chunk_set"], a hash of the PR ids + chunk settings) is part
    of every collection name: local-mode Qdrant can keep old points when a collection is
    deleted and re-created under the same name, so a changed pool must get a NEW name."""
    fns = {}
    base = f"{dataset}_{cfg_name}" + (f"_{chunk_set}" if chunk_set else "")
    if "bm25" in retrievers or "hybrid" in retrievers:
        col = f"{base}_bm25_k{k1}_b{b}_{bm25_kind}"
        if _reusable(client, col, chunks):     # complete index from an earlier run
            enc = make_encoder(bm25_kind, k1, b).fit([c["text"] for c in chunks])
            print(f"[{cfg_name}] reusing complete BM25 index {col} ({len(chunks)} points)")
        else:
            enc = build_index(client, col, chunks, make_encoder(bm25_kind, k1, b))
            _check_count(client, col, chunks)
        fns["bm25"] = lambda q, k, f=None, col=col, enc=enc: search_sparse(
            client, col, enc, q, k=k, qfilter=f)
    if "dense" in retrievers or "hybrid" in retrievers:
        col = f"{base}_dense"
        if col not in _built_dense:
            if _reusable(client, col, chunks):   # complete index from an earlier run
                print(f"[{cfg_name}] reusing complete dense index {col} ({len(chunks)} points)")
            else:
                build_dense_index(client, col, chunks, embedder)
                _check_count(client, col, chunks)
            _built_dense.add(col)
        fns["dense"] = lambda q, k, f=None, col=col: search_dense(
            client, col, embedder, q, k=k, qfilter=f)
    if "hybrid" in retrievers:
        fns["hybrid"] = make_hybrid_search([fns["bm25"], fns["dense"]],
                                           depth=rrf_depth, rrf_k=rrf_k)
    return {r: fns[r] for r in RETRIEVERS if r in retrievers}


def save_results(rows, path_stem, meta, per_query=None):
    """Write <stem>.json (everything), <stem>.csv (one row per result) and, if given,
    <stem>_per_query.csv (one row per query x configuration x retriever)."""
    os.makedirs(os.path.dirname(path_stem) or ".", exist_ok=True)
    with open(path_stem + ".json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "results": rows}, f, indent=2)
    _write_csv(path_stem + ".csv", rows)
    if per_query:
        _write_csv(path_stem + "_per_query.csv", per_query)
    print(f"\nSaved {path_stem}.json, .csv" + (" and _per_query.csv" if per_query else ""))


def _write_csv(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                        for k, v in r.items()})
