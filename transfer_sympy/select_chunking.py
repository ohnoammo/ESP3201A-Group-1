"""Pick the tuned settings from the dev-set (50 tasks) results. Run this BEFORE any test run.

    python select_chunking.py results/swe_exp1_dev.json                          # stages 1-2
    python select_chunking.py results/swe_exp1_dev.json results/swe_exp1_dev_alpha.json
                                                                                 # + stage 3

Selection rule (fixed in advance; all on the full-query set, group "all", k=5):
  Stage 1 - chunking (one setting per chunking method, used for all three retrievers):
    score(config) = PR-level MRR@5 averaged over BM25, dense and hybrid, with BM25 at the
    default k1=1.2, b=0.75 and no links (alpha 0). Fixed: best (size, overlap). Structural:
    best size cap.
  Stage 2 - BM25 k1/b (only if a k1/b grid was run; we decided NOT to tune it, so the
    defaults are kept).
  Stage 3 - relation factor alpha, separately for EACH chunking method x retriever (alpha
    is applied after the search, so it doesn't break "same chunks for every retriever"):
    score(alpha) = budget line recall (share of the fixing PR's changed lines inside the
    token budget). Recall because the budget is fixed
    (recall and precision rank methods almost identically, and recall weights each task
    equally regardless of fix size).
    Safety rule (option B, agreed before the alpha run): an alpha > 0 is only eligible if
    the fixing PR is still in the budget (gold_in_budget, for that retriever) at least as
    often as with no links minus --gold-tol (default 0.02 = 1 task in 50). Links can fill
    the budget with a wrong top PR's code and push the fixing PR out; this stops alpha
    from trading that away for recall. alpha 0 is always eligible.
  Ties (scores within --tie, default 0.005) go to the higher PR-level Hit@5 (stage 1), or
  to the SMALLER setting / default k1, b / smaller alpha.
No size-eligibility rule for structural chunks (agreed): chunk-size stats are reported for
every condition, plus a size-matched fixed baseline (--size-matched in the test runs).
Every dev result is printed, so the full tuning log can go in the report.
"""
import argparse
import json
from collections import defaultdict

DEFAULT_K1B = (1.2, 0.75)


def load_rows(paths, k=5):
    """Rows (full queries, group 'all', not size-matched) from all files; a later file wins
    for the same (chunking, retriever, k1, b, alpha). Also returns the pool of the runs."""
    rows, pool = {}, None
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        pool = pool or data.get("meta", {}).get("pool")
        for r in data["results"]:
            if (r["k"] == k and r["group"] == "all" and r["query_set"] == "full"
                    and not r.get("size_matched_to")):
                r = r | {"alpha": r.get("alpha") or 0.0}     # runs before links: alpha 0
                rows[(r["chunking"], r["retriever"], r["k1"], r["b"], r["alpha"])] = r
    return list(rows.values()), pool


def pool_args(pool):
    """'A2000' -> '--pool A --n-distractors 2000'; 'B365d' -> '--pool B --window-days 365'."""
    if not pool:
        return "--pool A --n-distractors 2000"
    if pool[0] in "AH":
        return f"--pool {pool[0]} --n-distractors {pool[1:]}"
    return f"--pool B --window-days {pool[1:].rstrip('d')}"


def better(a, b, tie):
    if b is None:
        return True
    if abs(a["score"] - b["score"]) > tie:
        return a["score"] > b["score"]
    return a["hit"] > b["hit"]


def _k1b(r):
    return (r["k1"], r["b"])


def main(paths, k=5, tie=0.005, gold_tol=0.02):
    all_rows, pool = load_rows(paths, k)
    rows = [r for r in all_rows if r["alpha"] == 0]              # stages 1-2: no links

    # ---- stage 1: chunking, mean over retrievers at default k1/b ----
    by_cfg = defaultdict(list)
    for r in rows:
        if r["retriever"] == "dense" or _k1b(r) == DEFAULT_K1B:
            by_cfg[r["chunking"]].append(r)
    cfgs = []
    for name, rs in by_cfg.items():
        cfgs.append({"name": name, "method": rs[0]["method"], "size": rs[0].get("size"),
                     "overlap": rs[0].get("overlap"), "cap": rs[0].get("cap"),
                     "avg_tokens": rs[0]["avg_tokens"], "n_chunks": rs[0]["n_chunks"],
                     "retrievers": sorted(r["retriever"] for r in rs),
                     "score": sum(r["pr_mrr"] for r in rs) / len(rs),
                     "hit": sum(r["pr_hit"] for r in rs) / len(rs),
                     "per": {r["retriever"]: r["pr_mrr"] for r in rs}})
    if len({tuple(c["retrievers"]) for c in cfgs}) > 1:
        print("WARNING: configs were run with different retrievers; scores not comparable")

    best = {}
    for method in ("fixed", "structural"):
        print(f"\n=== {method}: score = mean PR MRR@{k} over retrievers (k1/b {DEFAULT_K1B}) ===")
        for c in sorted((c for c in cfgs if c["method"] == method),
                        key=lambda c: (c["size"] or 0, c["overlap"] or 0, c["cap"] or 0)):
            per = "  ".join(f"{r}={v:.3f}" for r, v in sorted(c["per"].items()))
            print(f"  {c['name']:<18} score {c['score']:.3f}  Hit {c['hit']:.3f}  "
                  f"avg {c['avg_tokens']:.0f} tokens, {c['n_chunks']} chunks  ({per})")
            if better(c, best.get(method), tie):
                best[method] = c
        if method in best:
            print(f"  -> chosen: {best[method]['name']}")

    # ---- stage 2: BM25 k1/b for each chosen config ----
    k1b = {}
    for method, c in best.items():
        cand = [r for r in rows if r["chunking"] == c["name"] and r["retriever"] == "bm25"]
        print(f"\n=== BM25 k1/b for {c['name']}: score = BM25 PR MRR@{k} ===")
        top = None                       # default k1/b checked first, so it wins full ties
        for r in sorted(cand, key=lambda r: (_k1b(r) != DEFAULT_K1B, _k1b(r))):
            r = r | {"score": r["pr_mrr"], "hit": r["pr_hit"]}
            print(f"  k1={r['k1']:<4} b={r['b']:<5} MRR {r['score']:.3f}  Hit {r['hit']:.3f}")
            if better(r, top, tie):
                top = r
        if top:
            k1b[method] = _k1b(top)
            print(f"  -> chosen: k1={top['k1']}, b={top['b']}")

    # ---- stage 3: relation factor alpha for each chosen config ----
    alpha = {}                                   # (method, retriever) -> chosen alpha
    for method, c in best.items():
        kb = k1b.get(method, DEFAULT_K1B)
        cand = [r for r in all_rows if r["chunking"] == c["name"]
                and (r["retriever"] == "dense" or _k1b(r) == kb)
                and r.get("budget_recall") is not None]
        for ret in sorted({r["retriever"] for r in cand}):
            by_a = {r["alpha"]: r for r in cand if r["retriever"] == ret}
            print(f"\n=== Relation factor for {c['name']} + {ret}: score = budget line recall ===")
            if len(by_a) < 2:
                print("  (no alpha grid in these results yet: run the alpha tuning command below)")
                continue
            floor = by_a[0.0]["gold_in_budget"] - gold_tol if 0.0 in by_a else None
            if floor is not None:
                print(f"  eligible only if the fixing PR is in the budget >= {floor:.3f} "
                      f"(no-links rate minus {gold_tol})")
            top = None                               # smallest alpha first: wins full ties
            for a in sorted(by_a):
                x = by_a[a]
                r = {"alpha": a, "score": x["budget_recall"], "hit": 0.0}
                ok = a == 0 or floor is None or x["gold_in_budget"] >= floor - 1e-9
                print(f"  alpha={a:<5} recall {x['budget_recall']:.3f}  precision "
                      f"{x['budget_precision']:.3f}  gold PR in budget {x['gold_in_budget']:.3f}"
                      f"  linked chunks {x['n_linked']:.1f}"
                      f"{'' if ok else '  -> NOT eligible (loses the fixing PR too often)'}")
                if ok and better(r, top, tie):
                    top = r
            alpha[(method, ret)] = top["alpha"]
            print(f"  -> chosen: alpha={top['alpha']}")

    if "fixed" in best and "structural" in best:
        f, s = best["fixed"], best["structural"]
        fk, sk = k1b.get("fixed", DEFAULT_K1B), k1b.get("structural", DEFAULT_K1B)
        frac = round(f["overlap"] / f["size"], 4) if f["size"] else 0
        pa = pool_args(pool)
        amap = " ".join(f"{m}.{r}={a:g}" for (m, r), a in sorted(alpha.items()))
        print("\n=== Chosen settings (write these down before running the test split) ===")
        print(f"  fixed:      size {f['size']}, overlap {f['overlap']} ({frac:.0%}), "
              f"BM25 k1={fk[0]} b={fk[1]}")
        print(f"  structural: cap {s['cap']}, BM25 k1={sk[0]} b={sk[1]}")
        print(f"  relation factor per chunking.retriever: {amap or 'not tuned yet'}")
        if not alpha:
            print("\n  Next: tune the relation factor on dev (only re-ranks; no new embeddings):")
            print(f"    python run_retrieval_swe.py --split dev {pa} --fixed-sizes {f['size']} "
                  f"--overlap-fracs {frac} --struct-caps {s['cap']} --alphas 0 0.25 0.5 1 "
                  f"--tag _dev_alpha")
            print(f"    python select_chunking.py {' '.join(paths)} results/swe_exp1_dev_alpha.json")
            return
        print("\n  Final test runs (each ONCE; alpha 0 is kept next to each tuned alpha):")
        print(f"    python run_retrieval_swe.py --split test {pa} --fixed-sizes {f['size']} "
              f"--overlap-fracs {frac} --struct-caps {s['cap']} --fixed-k1b {fk[0]} {fk[1]} "
              f"--struct-k1b {sk[0]} {sk[1]} --alpha-map {amap} --size-matched "
              f"--query-sets full short --tag _test_tuned")
        print(f"    python run_retrieval_swe.py --split test {pa} --size-matched "
              "--query-sets full short --tag _test_untuned")
        print("    python stats.py results/swe_exp1_test_tuned_per_query.csv "
              "results/swe_exp1_test_untuned_per_query.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+", help="results/*.json from the dev runs")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--tie", type=float, default=0.005)
    ap.add_argument("--gold-tol", type=float, default=0.02,
                    help="alpha > 0 is only eligible if the fixing PR is in the budget at most this much less often than with no links (0.02 = 1 task in 50)")
    a = ap.parse_args()
    main(a.results, a.k, a.tie, a.gold_tol)
