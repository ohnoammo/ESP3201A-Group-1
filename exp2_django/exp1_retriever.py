"""Run the group's frozen Exp 1 retriever (retrieve.py, by Clifton) for Exp 2, WITHOUT editing it.

    python exp1_retriever.py --out results/retrieved_top5_exp1.jsonl [--ids q1 q2 ...]

- Runs against a COPY of the Exp 1 folder outside OneDrive (EXP1_COPY below; qdrant_exp1/,
  emb_cache/ and prs/ copied there), never the OneDrive folder: retrieve.py uses relative paths
  and Qdrant local mode locks/writes its folder.
- Their FrozenRetriever hard-codes the bug-report instruction (dense_retrieval.TASKS["swe"]).
  We swap in the Exp 2 "why" instruction from retrieval_config.json by setting
  embedder.query_prompt after construction (same "Instruct: ...\\nQuery:" format their
  Qwen3Embedder builds) and clearing its query cache.
- Must run as its own process: Exp 2 also has a retrieve.py, which would shadow theirs.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXP1_COPY = "C:/Users/kwekt/ESP3201A_local/exp1_copy"
# Chunkings in the copy. Chunk-set hashes are for the NEW pool A (22 Oct, same-ticket filter).
CHUNKINGS = {"fixed_s512_o77": ({"name": "fixed_s512_o77", "method": "fixed", "size": 512,
                                  "overlap": 77}, "311d0480"),
             "struct_c256": ({"name": "struct_c256", "method": "structural", "cap": 256},
                             "0611be80")}   # new pool A (same-ticket filter, 22 Oct); old: 9cb76462 / 7dcefc02


def main(a):
    with open(os.path.join(HERE, "retrieval_config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    with open(os.path.join(HERE, a.questions), encoding="utf-8") as f:
        qs = [json.loads(line) for line in f if line.strip()]
    if a.ids:
        qs = [q for q in qs if q["id"] in set(a.ids)]

    sys.path = [p for p in sys.path if os.path.abspath(p or ".") != HERE]
    copy_dir = a.copy or EXP1_COPY
    sys.path.insert(0, copy_dir)
    os.chdir(copy_dir)
    import retrieve as exp1                       # their file, from the copy
    assert os.path.abspath(exp1.__file__).startswith(os.path.abspath(copy_dir)), exp1.__file__

    # Their FrozenRetriever reads the module-level FROZEN dict at construction; switching the
    # chunking there (in memory) selects another existing collection without editing the file.
    exp1.FROZEN["chunking"], exp1.FROZEN["chunk_set"] = CHUNKINGS[a.chunking]
    r = exp1.FrozenRetriever(a.retriever)
    assert r.chunk_set == CHUNKINGS[a.chunking][1], r.chunk_set
    original = r.embedder.query_prompt
    if not a.keep_bug_instruction:
        r.embedder.query_prompt = f"Instruct: {cfg['query_instruction']}\nQuery:"
        r.embedder._query_cache = {}
    print(f"instruction: {r.embedder.query_prompt!r} (their default: {original!r})")

    out = []
    for q in qs:
        hits = r.retrieve(q["question"], k=a.k, exclude_prs=q.get("exclude_prs") or None)
        out.append({"id": q["id"], "chunk_ids": [h["chunk_id"] for h in hits],
                    "spans": [[h["start"], h["end"]] for h in hits],
                    "scores": [h["score"] for h in hits],
                    "part_types": [h["part_types"] for h in hits],
                    "retrieved_prs": [h["pr_number"] for h in hits]})
    meta = {"retriever": f"Exp 1 retrieve.py FrozenRetriever ({a.retriever})", "copy": copy_dir,
            "chunking": a.chunking,
            "chunk_set": r.chunk_set, "query_prompt": r.embedder.query_prompt,
            "n_truncated_queries": r.embedder.n_truncated_queries}
    with open(os.path.join(HERE, a.out), "w", encoding="utf-8") as f:
        f.write(json.dumps({"_meta": meta}) + "\n")
        for row in out:
            f.write(json.dumps(row) + "\n")
    print(f"{len(out)} queries -> {a.out}; meta {meta}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="questions.jsonl")
    ap.add_argument("--ids", nargs="*", default=None)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--chunking", choices=sorted(CHUNKINGS), default="fixed_s512_o77")
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-bug-instruction", action="store_true")
    ap.add_argument("--retriever", choices=["dense", "hybrid"], default="dense",
                    help="hybrid = arm H0 (tuning_rule_hybrid.md); the instruction swap reaches the dense half only")
    ap.add_argument("--copy", default=None,
                    help="another Exp 1 copy, e.g. exp1_copy_redacted (leakage variant index)")
    main(ap.parse_args())
