"""Arm H0 on SymPy, 4B v3 (tuning_rule_sympy_h0.md; exploratory, counts only).

    python sympy_h0.py retrieve    # hybrid candidates, checked dense regression
    python sympy_h0.py generate    # F0 rerun (hardware control, contexts must equal Clifton's), then H0
    python sympy_h0.py score       # -> results/sympy_h0/summary.csv, blind sheet, key

Runs inside a local unpacked copy of Clifton's zip (COPY) and reuses his exp2_sympy.py functions, which are not
edited. Needs nltk 3.10.3 from pylib_h0 on PYTHONPATH.
"""
import argparse
import csv
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COPY = "C:/Users/kwekt/ESP3201A_local/sympy_copy_h0"
OUT = os.path.join(HERE, "results", "sympy_h0")
CLIF = os.path.join(HERE, "results", "sympy")
CAND = os.path.join(OUT, "candidates_hybrid.jsonl")
CHUNKING = {"name": "fixed_s512_o77", "method": "fixed", "size": 512, "overlap": 77}
CHUNK_SET = "394f364b"


def setup():
    os.makedirs(OUT, exist_ok=True)
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE]
    sys.path.insert(0, COPY)
    os.chdir(COPY)
    import exp2_sympy as X
    assert os.path.abspath(X.__file__).startswith(os.path.abspath(COPY)), X.__file__
    X.ARMS["H0"] = X.ARMS["F0"]
    X.ARMS["F0-rerun"] = X.ARMS["F0"]
    return X


def rd(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def cmd_retrieve(a):
    X = setup()
    from qdrant_client import QdrantClient, models
    from dense_retrieval import Qwen3Embedder, DEFAULT_MODEL
    from exp1_common import build_retrievers
    qs = X.read_jsonl(X.QUESTIONS)
    chunks, info = X.chunk_set("fixed_s512_o77")
    assert info["chunk_set"] == CHUNK_SET, info
    emb = Qwen3Embedder(DEFAULT_MODEL, task=None, batch_size=16, cache_path=X.EMB_CACHE)
    emb.query_prompt = f"Instruct: {X.INSTRUCTION}\nQuery:"
    emb._query_cache = {}
    client = QdrantClient(path="qdrant_exp1")
    fns = build_retrievers(client, "swe", CHUNKING["name"], chunks, ["dense", "hybrid"], emb, k1=1.2, b=0.75,
                           bm25_kind="code", rrf_depth=100, rrf_k=60, chunk_set=CHUNK_SET)
    clif = {r["id"]: r for r in X.read_jsonl(os.path.join(X.OUT, "candidates_fixed_s512_o77.jsonl"))[1:]}
    rows, same = [], []
    for q in qs:
        flt = None
        if q["exclude_prs"]:
            flt = models.Filter(must_not=[models.FieldCondition(
                key="pr_number", match=models.MatchAny(any=[int(n) for n in q["exclude_prs"]]))])
        dense = [c["chunk_id"] for c in fns["dense"](q["question"], 100, flt)]
        ref = clif[q["id"]]["chunk_ids"]
        same.append({"id": q["id"], "first_diff_rank": next((i + 1 for i, (x, y) in enumerate(zip(dense, ref)) if x != y), None),
                     "overlap100": len(set(dense) & set(ref))})
        hits = fns["hybrid"](q["question"], 100, flt)
        rows.append({"id": q["id"], "chunk_ids": [c["chunk_id"] for c in hits], "scores": [c["score"] for c in hits]})
    print("dense vs Clifton's: min overlap", min(r["overlap100"] for r in same), "earliest first difference",
          min(r["first_diff_rank"] or 101 for r in same))
    X.write_jsonl(CAND, [{"_meta": {"retriever": "hybrid RRF k=60 depth 100, code BM25 k1 1.2 b 0.75", "chunk_set": CHUNK_SET,
                                    "query_prompt": emb.query_prompt, "dense_vs_clifton": same}}] + rows)
    print(f"{len(rows)} questions -> {CAND}")


def cmd_generate(a):
    X = setup()
    orig = X._candidates
    hybrid = {r["id"]: r for r in X.read_jsonl(CAND)[1:]}
    meta = X.read_jsonl(CAND)[0]["_meta"]

    def cands(ch):
        return (orig(ch)[0] | {"retriever": meta["retriever"]}, hybrid) if a_arm["now"] == "H0" else orig(ch)
    X._candidates = cands
    a_arm = {}
    chunks, _ = X.chunk_set("fixed_s512_o77")
    by_id = {c["chunk_id"]: c for c in chunks}
    clif_ctx = {r["id"]: r["context_chunk_ids"] for r in rd(os.path.join(CLIF, "gen_F0.jsonl"))}
    bad = [q["id"] for q in X.read_jsonl(X.QUESTIONS)
           if [c["chunk_id"] for c in X.pack(orig("fixed_s512_o77")[1][q["id"]]["chunk_ids"], by_id, "score", q["exclude_prs"])]
           != clif_ctx[q["id"]]]
    print(f"F0 context regression: {len(bad)} questions differ {bad}")
    assert not bad, "F0 contexts differ from Clifton's"
    X.OUT_ORIG = X.OUT
    for arm in ("F0-rerun", "H0"):
        a_arm["now"] = arm
        ns = argparse.Namespace(arms=[arm], model=X.MODEL)
        # gen_<arm>.jsonl goes to results/sympy_h0: X.OUT is only joined for this path once candidates are read
        real_join = os.path.join

        def join(*p):
            return real_join(OUT, p[1]) if p[0] == X.OUT and p[1].startswith("gen_") else real_join(*p)
        os.path.join = join
        try:
            X.cmd_generate(ns)
        finally:
            os.path.join = real_join


def cmd_score(a):
    X = setup()
    qs = {q["id"]: q for q in X.read_jsonl(X.QUESTIONS)}
    gens = {arm: rd(os.path.join(OUT, f"gen_{arm}.jsonl")) for arm in ("F0-rerun", "H0")}
    gens["F0"] = rd(os.path.join(CLIF, "gen_F0.jsonl"))
    for arm, g in gens.items():
        assert len(g) == 22, (arm, len(g))
    rows = X.summarise({k: gens[k] for k in ("F0", "F0-rerun", "H0")}, qs)
    hyb = {r["id"]: r for r in rd(CAND)[1:]}
    dense = {r["id"]: r for r in X.read_jsonl(os.path.join(X.OUT, "candidates_fixed_s512_o77.jsonl"))[1:]}
    ans = [i for i, q in qs.items() if q["type"] == "answerable"]

    def top5(c, i):
        return qs[i]["pr_number"] in list(dict.fromkeys(int(x.split("_")[0]) for x in c[i]["chunk_ids"]))[:5]
    for r in rows:
        r["gold_pr_top5"] = sum(top5(hyb if r["arm"] == "H0" else dense, i) for i in ans)
        ua = []
        for g in gens[r["arm"]]:
            x = X.auto(g, qs[g["id"]], "fixed_s512_o77")
            if g["type"] != "answerable" and not x["abstained"] and not x["empty_answer"]:
                ua.append(g["id"])
        r["unanswerable_ids"] = " ".join(ua)
    with open(os.path.join(OUT, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    clif = {r["id"]: r for r in gens["F0"]}
    same = [r["id"] for r in gens["F0-rerun"] if r["response"] == clif[r["id"]]["response"]]
    with open(os.path.join(OUT, "hardware_control.json"), "w", encoding="utf-8") as f:
        json.dump({"n": 22, "identical_answers": len(same), "different": sorted(set(clif) - set(same))}, f, indent=1)
    items = []
    for arm in ("H0", "F0", "F0-rerun"):
        for r in gens[arm]:
            x = X.auto(r, qs[r["id"]], "fixed_s512_o77")
            if r["type"] != "answerable" or x["abstained"] or x["empty_answer"]:
                continue
            if arm == "F0-rerun" and r["response"] == clif[r["id"]]["response"]:
                continue
            items.append((hashlib.sha256(f"sympy-h0:{arm}:{r['id']}".encode()).hexdigest(), arm, r))
    items.sort(key=lambda t: t[0])
    key, sheet = {}, []
    for n, (_, arm, r) in enumerate(items, 1):
        b, q = f"H{n:03d}", qs[r["id"]]
        key[b] = {"arm": arm, "id": r["id"]}
        sheet.append([b, q["question"], q["answer"], " || ".join(q["quotes"]), X.strip_citations(r["response"]), "", ""])
    os.makedirs(os.path.join(OUT, "keys"), exist_ok=True)
    with open(os.path.join(OUT, "keys", "sheet_key.json"), "w", encoding="utf-8") as f:
        json.dump(key, f, indent=1)
    with open(os.path.join(OUT, "correctness_sheet.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["blind_id", "question", "gold_answer", "gold_quotes", "model_answer", "label", "reason"])
        w.writerows(sheet)
    for r in rows:
        print({k: r[k] for k in ("arm", "gold_pr_top5", "span_in_context", "answered", "abstained_with_span", "overlap_cited",
                                 "unanswerable_answered", "unanswerable_ids")})
    print(f"hardware control: {len(same)}/22 identical; sheet {len(sheet)} rows")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["retrieve", "generate", "score"])
    args = ap.parse_args()
    {"retrieve": cmd_retrieve, "generate": cmd_generate, "score": cmd_score}[args.cmd](args)
