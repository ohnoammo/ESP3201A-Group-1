"""Exp 2 contexts packed by Exp 1's relations.expand_and_pack() (group decision 22 Oct).

    from pack_exp1 import build_context_exp1
    ctx = build_context_exp1(qid, alpha, budget_tokens=2560, exclude_prs=(),
                             chunking="fixed_s512_o77", links="exp2")

Wrapper only: relations.py is imported unedited from the Exp 1 copy outside OneDrive.
  ranked   the saved top-100 candidates (exp1_retriever.py), best first, with chunk texts
  links    "exp2"         Exp 2 explanation links (link_map.py: hunk<->mapped thread, parent,
                          conversation neighbours), converted to expand_and_pack's
                          {chunk_id: [(linked_id, distance)]} with distance 0
           "exp1_context" relations.build_links(kinds=("context",)) = Exp 1's own Exp 2 kind
                          (hunk -> its review threads, file-level fallback; hunk -> description);
                          structural chunks only (it defines no context links for fixed chunks)
  scoring  expand_and_pack's own: retrieved rank r -> 1/r, linked from rank r -> alpha/r
           (RRF_K = 0), greedy pack, skip what doesn't fit; tokens = relations.token_counter()
Linked chunks from exclude_prs are dropped (links never cross PRs, so this is a guard only).
"""
import importlib.util
import os
import sys

from common import read_jsonl, doc
from context_builder import _candidates, _chunk, _links
from link_map import LOCAL, chunks_for

COPY = os.path.join(LOCAL, "exp1_copy")
_spec = importlib.util.spec_from_file_location("exp1_relations", os.path.join(COPY, "relations.py"))
relations = importlib.util.module_from_spec(_spec)
sys.modules["exp1_relations"] = relations
_spec.loader.exec_module(relations)                 # imports chunking (identical in both trees)
NTOK = relations.token_counter()
TOKENIZER = "Exp 1 relations.token_counter() = chunking.count_tokens on chunk text"
_cache = {}


def _exp1_context_links(chunking, prs):
    key = ("ctx", chunking)
    if key not in _cache:
        _cache[key] = {}
    store = _cache[key]
    todo = [p for p in prs if p not in store]
    if todo:
        cs = [c | {"paper_id": str(p)} for p in todo for c in chunks_for(chunking, p)]
        docs = {str(p): doc(p) for p in todo}
        built = relations.build_links(cs, docs, kinds=("context",))
        for p in todo:
            store[p] = True
        _cache[("ctxmap", chunking)] = _cache.get(("ctxmap", chunking), {}) | built
    return _cache.get(("ctxmap", chunking), {})


def build_context_exp1(qid, alpha, budget_tokens=2560, exclude_prs=(), chunking="fixed_s512_o77",
                       links="exp2", cand_suffix=""):
    """cand_suffix "_hybrid" = arm H0 candidates; "" = the frozen dense candidates."""
    if cand_suffix:
        rows = read_jsonl(f"results/candidates_{chunking}_k100{cand_suffix}.jsonl")
        cands, meta = {r["id"]: r for r in rows[1:]}, rows[0]["_meta"]
    else:
        cands, meta = _candidates(chunking)
    cand = cands[qid]
    excl = {int(p) for p in exclude_prs}
    ranked = []
    for cid in cand["chunk_ids"]:
        if int(cid.split("_")[0]) in excl:
            continue
        c = _chunk(chunking, cid)
        ranked.append(c | {"chunk_id": cid})
    prs = sorted({int(c["chunk_id"].split("_")[0]) for c in ranked})
    if links == "exp2":
        raw = _links(chunking)
        lmap = {c["chunk_id"]: [(t, 0) for t, _ in raw.get(c["chunk_id"], [])
                                if int(t.split("_")[0]) not in excl] for c in ranked}
    elif links == "exp1_context":
        built = _exp1_context_links(chunking, prs)
        lmap = {c["chunk_id"]: [(t, d) for t, d in built.get(c["chunk_id"], [])] for c in ranked}
    else:
        raise ValueError(links)
    chunk_by_id = {}
    for p in prs:
        for c in chunks_for(chunking, p):
            chunk_by_id[c["chunk_id"]] = c
    packed = relations.expand_and_pack(ranked, alpha, lmap, chunk_by_id, budget_tokens, NTOK)
    out = [{"chunk_id": c["chunk_id"], "pr_number": int(c["chunk_id"].split("_")[0]),
            "start": c["start"], "end": c["end"], "text": c["text"], "score": c["score"],
            "linked": c["linked"], "tokens": NTOK(c["chunk_id"], c)} for c in packed]
    return {"chunks": out, "tokens": sum(c["tokens"] for c in out), "alpha": alpha,
            "budget": budget_tokens, "chunking": chunking, "links": links,
            "tokenizer": TOKENIZER, "n_linked": sum(c["linked"] for c in out),
            "n_prs": len({c["pr_number"] for c in out}), "retriever_meta": meta}


# ---------------------------------------------------------------------------------------------
# Leakage variant "answer removed, PR kept" (questions_removed_kept.jsonl, ids rk<pr>):
# the 5 redacted PRs use chunks/links built from their redacted documents; everything else is the
# main pool. Candidates come from the separate index in exp1_copy_redacted.
REDACTED_COPY = os.path.join(LOCAL, "exp1_copy_redacted")
_var = {}


def _redacted_store(chunking):
    if chunking in _var:
        return _var[chunking]
    import json as _json
    from chunking import fixed_size_chunks
    from link_map import chunk_links
    from pr_document import build_document
    prdir = os.path.join(REDACTED_COPY, "prs", "django_django")
    red_prs = [int(f[:-5]) for f in os.listdir(prdir)
               if f[:-5].isdigit() and "redacted_for_exp2" in open(os.path.join(prdir, f), encoding="utf-8").read()]
    if chunking == "struct_c256":
        with open(os.path.join(REDACTED_COPY, "chunks", "swe_struct_c256_2231docs_0611be80.json"),
                  encoding="utf-8") as f:
            allc = _json.load(f)["chunks"]
    store, links = {}, {}
    for n in red_prs:
        with open(os.path.join(prdir, f"{n}.json"), encoding="utf-8") as f:
            pr = _json.load(f)
        d = build_document(pr)
        if chunking == "fixed_s512_o77":
            cks = [c | {"chunk_id": f"{n}_fixed_s512_o77_{i}", "pr_number": n}
                   for i, c in enumerate(fixed_size_chunks(d["text"], 512, 77))]
        else:
            cks = [c for c in allc if int(c["pr_number"]) == n]
        store[n] = cks
        links.update(chunk_links(chunking, n, pr=pr, d=d, cks=cks))
    _var[chunking] = (store, links)
    return _var[chunking]


def build_context_redacted(qid, alpha, budget_tokens=2560, exclude_prs=(), chunking="fixed_s512_o77",
                           cand_suffix=""):
    """Like build_context_exp1 (links="exp2"), on the "answer removed, PR kept" index variant."""
    rows = read_jsonl(f"results/candidates_{chunking}_k100{cand_suffix}_redacted.jsonl")
    meta, cand = rows[0]["_meta"], {r["id"]: r for r in rows[1:]}[qid]
    store, red_links = _redacted_store(chunking)
    excl = {int(p) for p in exclude_prs}
    main_links = _links(chunking)

    def chunk_list(p):
        return store[p] if p in store else chunks_for(chunking, p)
    by_id = {}
    prs = sorted({int(c.split("_")[0]) for c in cand["chunk_ids"]} - excl)
    for p in prs:
        for c in chunk_list(p):
            by_id[c["chunk_id"]] = c
    ranked = [by_id[c] | {"chunk_id": c} for c in cand["chunk_ids"] if int(c.split("_")[0]) not in excl]
    lmap = {}
    for c in ranked:
        p = int(c["chunk_id"].split("_")[0])
        src = red_links if p in store else main_links
        lmap[c["chunk_id"]] = [(t, 0) for t, _ in src.get(c["chunk_id"], [])]
    packed = relations.expand_and_pack(ranked, alpha, lmap, by_id, budget_tokens,
                                       relations.token_counter())
    out = [{"chunk_id": c["chunk_id"], "pr_number": int(c["chunk_id"].split("_")[0]),
            "start": c["start"], "end": c["end"], "text": c["text"], "score": c["score"],
            "linked": c["linked"], "tokens": count(c)} for c in packed for count in [lambda x: NTOK("red:" + x["chunk_id"], x)]]
    return {"chunks": out, "tokens": sum(c["tokens"] for c in out), "alpha": alpha,
            "budget": budget_tokens, "chunking": chunking, "links": "exp2",
            "variant": "answer removed, PR kept", "tokenizer": TOKENIZER,
            "n_linked": sum(c["linked"] for c in out),
            "n_prs": len({c["pr_number"] for c in out}), "retriever_meta": meta}
