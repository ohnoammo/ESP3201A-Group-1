"""Tier 2, step 10: retrieve top-k for every question and score retrieval.

    python exp1_retriever.py --out results/retrieved_top5_exp1.jsonl   # group's retrieve.py (copy)
    python eval_retrieval.py --source exp1   # -> results/retrieved_top5.jsonl, retrieval_eval.json
    python eval_retrieval.py --source numpy  # stand-in (retrieve_np.py), used before 15 Oct

The saved top-k lists are what run_generation.py feeds the LLM for the "retrieved" condition,
so retrieval scores and generation inputs are the same chunks.

Answerable questions:
  chunk_hit@k   a retrieved chunk fully contains the answer quote (gold_chunks)
  overlap_hit@k a retrieved chunk overlaps the quote span (overlap_chunks)
  pr_hit@k      any chunk of the question's PR is retrieved
  chunk_mrr@k   1/rank of the first gold chunk (0 if none in the top k)
Removed: excluded PRs must not appear; quote_in_context must be False.
No-reason: pr_hit@k reported for information.
"""
import argparse
import hashlib
import json
import os

from common import read_jsonl, write_jsonl, git_commit, chunks

with open("retrieval_config.json", encoding="utf-8") as _f:
    CONFIG = json.load(_f)
K = CONFIG["k"]
EXP1_FILE = f"results/retrieved_top{K}_exp1.jsonl"


def exp1_hits(q, saved):
    """Hits from the group's retrieve.py run (exp1_retriever.py), in the stand-in's format."""
    r = saved[q["id"]]
    out = []
    for rank, (cid, sc) in enumerate(zip(r["chunk_ids"], r["scores"]), 1):
        pr = int(cid.split("_")[0])
        c = next(c for c in chunks(pr) if c["chunk_id"] == cid)
        out.append({"rank": rank, "score": sc, "pr_number": pr, "chunk_id": cid,
                    "text": c["text"]})
    return out


def main(source):
    qs = read_jsonl("questions.jsonl")
    if source == "exp1":
        rows_in = read_jsonl(EXP1_FILE)
        exp1_meta = rows_in[0]["_meta"]
        saved = {r["id"]: r for r in rows_in[1:]}
        assert exp1_meta["query_prompt"] == "Instruct: " + CONFIG["query_instruction"] + "\nQuery:"
        get = lambda q, v: exp1_hits(q, saved)
        vecs = [None] * len(qs)
    else:
        from retrieve_np import embed_queries, retrieve
        exp1_meta = None
        vecs = embed_queries([q["question"] for q in qs])
        get = lambda q, v: retrieve(q["question"], k=K, exclude_prs=q["exclude_prs"], query_vec=v)
    rows = []
    for q, v in zip(qs, vecs):
        hits = get(q, v)
        ids = [h["chunk_id"] for h in hits]
        gold, over = set(q["gold_chunks"]), set(q["overlap_chunks"])
        first = next((i for i, c in enumerate(ids, 1) if c in gold), None)
        r = {"id": q["id"], "type": q["type"], "split": q["split"],
             "pr_number": q["pr_number"], "chunk_ids": ids,
             "scores": [round(h["score"], 5) for h in hits],
             "retrieved_prs": [h["pr_number"] for h in hits],
             "pr_hit": q["pr_number"] in [h["pr_number"] for h in hits], "source": source}
        if q["type"] == "answerable":
            r |= {"chunk_hit": first is not None, "chunk_mrr": 1 / first if first else 0.0,
                  "overlap_hit": any(c in over for c in ids)}
        if q["type"] == "removed":
            r |= {"excluded_leak": [p for p in r["retrieved_prs"] if p in q["exclude_prs"]],
                  "quote_in_context": any(q["quote"] in h["text"] for h in hits)}
        rows.append(r)
    write_jsonl(f"results/retrieved_top{K}.jsonl", rows)

    summary = {"git_commit": git_commit(), "k": K, "source": source,
               "exp1_retriever": exp1_meta,
               "config_sha1": hashlib.sha1(json.dumps(CONFIG, sort_keys=True).encode()
                                           ).hexdigest()[:10],
               "query_instruction": CONFIG["query_instruction"]}
    for split in ("dev", "test", "all"):
        a = [r for r in rows if r["type"] == "answerable" and split in (r["split"], "all")]
        if a:
            summary[f"answerable_{split}"] = {
                "n": len(a), "chunk_hit@5": sum(r["chunk_hit"] for r in a) / len(a),
                "overlap_hit@5": sum(r["overlap_hit"] for r in a) / len(a),
                "pr_hit@5": sum(r["pr_hit"] for r in a) / len(a),
                "chunk_mrr@5": sum(r["chunk_mrr"] for r in a) / len(a)}
    nr = [r for r in rows if r["type"] == "no_reason"]
    rm = [r for r in rows if r["type"] == "removed"]
    summary["no_reason_pr_hit@5"] = f"{sum(r['pr_hit'] for r in nr)}/{len(nr)}"
    summary["removed"] = {r["id"]: {"excluded_leak": r["excluded_leak"],
                                    "quote_in_context": r["quote_in_context"]} for r in rm}
    summary["answerable_misses"] = {r["id"]: {"pr_hit": r["pr_hit"],
                                              "retrieved_prs": r["retrieved_prs"]}
                                    for r in rows if r["type"] == "answerable"
                                    and not r["chunk_hit"]}
    with open("results/retrieval_eval.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["exp1", "numpy"], default="exp1")
    main(ap.parse_args().source)
