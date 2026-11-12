"""Relation factor: build an LLM context from retrieved chunks plus explanation-linked chunks.

    from context_builder import build_context
    ctx = build_context(question_id_or_text, alpha=0.5, budget_tokens=2560, label_links=False,
                        exclude_prs=[...], chunking="fixed_s512_o77")

Scoring (one hop): every retrieved candidate (top CANDIDATE_K from the group's retriever) keeps
its score; every chunk linked FROM a candidate gets alpha x that candidate's score; a chunk
reached more than once keeps its maximum. alpha = 0 adds no linked chunks, i.e. plain
retrieval at the same budget. Chunks from exclude_prs are never added (retrieved or linked).

Budget: chunks in score order (ties: candidate rank, then chunk id); a chunk that would
overflow the budget is skipped and filling continues. Tokens = Exp 1's unit (chunking.count_tokens,
\\w+|[^\\w\\s]) of the rendered chunk text; TOKENIZER below records this.

Retrieval-only use reads saved candidates (results/candidates_<chunking>_k100.jsonl from
exp1_retriever.py), so contexts are exact and reproducible. Context ORDER for the LLM is an open
decision (James, 21 Oct); this module returns chunks in score order and records it.
"""
import json
import os

from chunking import count_tokens
from common import read_jsonl
from link_map import LOCAL, chunks_for

TOKENIZER = "Exp 1 chunking.count_tokens (regex \\w+|[^\\w\\s]) on rendered chunk text"
CANDIDATE_K = 100
_cache = {}


def _links(chunking):
    if ("links", chunking) not in _cache:
        with open(os.path.join(LOCAL, f"links_{chunking}.json"), encoding="utf-8") as f:
            _cache[("links", chunking)] = json.load(f)
    return _cache[("links", chunking)]


def _candidates(chunking):
    if ("cand", chunking) not in _cache:
        merged, meta = {}, None
        for suffix in ("", "_dev2"):               # test/dev1 questions, then dev set 2
            path = f"results/candidates_{chunking}_k{CANDIDATE_K}{suffix}.jsonl"
            if not os.path.exists(path):
                continue
            rows = read_jsonl(path)
            assert rows[0]["_meta"]["chunking"] == chunking
            meta = meta or rows[0]["_meta"]
            for r in rows[1:]:
                assert r["id"] not in merged, r["id"]
                merged[r["id"]] = r
        _cache[("cand", chunking)] = (merged, meta)
    return _cache[("cand", chunking)]


def _chunk(chunking, chunk_id):
    key = ("chunk", chunking, chunk_id)
    if key not in _cache:
        pr = int(chunk_id.split("_")[0])
        for c in chunks_for(chunking, pr):
            _cache[("chunk", chunking, c["chunk_id"])] = c
    return _cache[key]


def short_id(chunk_id):
    pr, *_, i = chunk_id.split("_")
    return f"PR{pr}-c{i}"


def build_context(qid, alpha, budget_tokens=2560, label_links=False, exclude_prs=(),
                  chunking="fixed_s512_o77"):
    cands, meta = _candidates(chunking)
    cand = cands[qid]
    excl = {int(p) for p in exclude_prs}
    links = _links(chunking)
    best = {}                          # chunk_id -> (score, rank_key, via)
    for rank, (cid, sc) in enumerate(zip(cand["chunk_ids"], cand["scores"])):
        if int(cid.split("_")[0]) in excl:
            continue
        if cid not in best or sc > best[cid][0]:
            best[cid] = (sc, rank, None)
    if alpha > 0:
        for rank, (cid, sc) in enumerate(zip(cand["chunk_ids"], cand["scores"])):
            if int(cid.split("_")[0]) in excl:
                continue
            for tgt, typ in links.get(cid, []):
                if int(tgt.split("_")[0]) in excl:
                    continue
                s = alpha * sc
                if tgt not in best or s > best[tgt][0]:
                    best[tgt] = (s, rank, (cid, typ))
    order = sorted(best, key=lambda c: (-best[c][0], best[c][1], c))
    picked, used = [], 0
    for cid in order:
        c = _chunk(chunking, cid)
        via = best[cid][2]
        text = c["text"]
        if label_links and via:
            text = f"({via[1].replace('->', ' -> ')} of [{short_id(via[0])}])\n" + text
        n = count_tokens(text)
        if used + n > budget_tokens:
            continue
        used += n
        picked.append({"chunk_id": cid, "pr_number": int(cid.split("_")[0]), "start": c["start"],
                       "end": c["end"], "text": text, "score": best[cid][0],
                       "linked_via": via, "tokens": n})
    return {"chunks": picked, "tokens": used, "alpha": alpha, "budget": budget_tokens,
            "chunking": chunking, "label_links": label_links, "tokenizer": TOKENIZER,
            "n_linked": sum(1 for p in picked if p["linked_via"]),
            "n_prs": len({p["pr_number"] for p in picked}), "retriever_meta": meta}
