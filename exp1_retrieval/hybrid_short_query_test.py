"""Dense vs hybrid on full and first-line bug-report queries (report Section 4.6, Table 6, bug-report rows).

    python exp1_retrieval/hybrid_short_query_test.py    # -> exp1_retrieval/results/hybrid_short_query_test.txt

Status: secondary. The first-line ("short") runs were part of the planned Exp 1 test runs (23 Oct); these
dense-vs-hybrid tests on them were computed on 12-13 Nov, after the main results were seen. Uncorrected.

Reads only the committed per-query test files (pools A and H, tuned settings, alpha = 0 rows), so no
retrieval is re-run. Tests, paired by bug report (n = 181):
  - MRR@5 and budget line recall: two-sided paired sign-flip permutation test, 10,000 flips, seed 0;
  - Hit@5: exact two-sided McNemar.
Also reports the short-minus-full MRR@5 change per retriever (fixed 512/77), same permutation test.
"""
import collections
import csv
import os
import random
from math import comb

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
FILES = {"A": "swe_exp1_test_tuned_per_query.csv", "H": "swe_exp1_testH_tuned_per_query.csv"}
CHUNKINGS = ["fixed_s512_o77", "struct_c256"]


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def perm(d, flips=10000, seed=0):
    rnd = random.Random(seed)
    obs = abs(sum(d))
    hits = 0
    for _ in range(flips):
        s = abs(sum(x if rnd.random() < 0.5 else -x for x in d))
        if s >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (flips + 1)


def load(path):
    g = collections.defaultdict(dict)
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["alpha"] in ("0", "0.0"):
                g[(r["chunking"], r["query_set"], r["retriever"])][r["instance_id"]] = r
    return g


def mean(xs):
    return sum(xs) / len(xs)


def main():
    out = ["Dense vs hybrid on full and first-line bug-report queries (alpha = 0, test set, n = 181)",
           "Secondary analysis, uncorrected. Permutation: 10,000 sign flips, seed 0.", ""]
    for pool, fn in FILES.items():
        g = load(os.path.join(RES, fn))
        out.append(f"Pool {pool}")
        for ch in CHUNKINGS:
            for qs in ("full", "short"):
                D, H = g[(ch, qs, "dense")], g[(ch, qs, "hybrid")]
                ids = sorted(D)
                assert len(ids) == 181 and sorted(H) == ids, (pool, ch, qs)
                mrr_d = [float(D[i]["pr_mrr"]) for i in ids]
                mrr_h = [float(H[i]["pr_mrr"]) for i in ids]
                dm = [a - b for a, b in zip(mrr_d, mrr_h)]
                b = sum(float(D[i]["pr_hit"]) == 1 and float(H[i]["pr_hit"]) == 0 for i in ids)
                c = sum(float(D[i]["pr_hit"]) == 0 and float(H[i]["pr_hit"]) == 1 for i in ids)
                db = [float(D[i]["budget_recall"]) - float(H[i]["budget_recall"]) for i in ids]
                out.append(f"  {ch:15s} {qs:5s}  MRR@5 dense {mean(mrr_d):.3f} hybrid {mean(mrr_h):.3f} "
                           f"diff {mean(dm):.3f} p={perm(dm):.4f} | Hit@5 b/c {b}/{c} p={mcnemar(b, c):.3f} "
                           f"| budget recall diff {mean(db):.3f} p={perm(db):.4f}")
        for ret in ("bm25", "dense", "hybrid"):
            F, S = g[("fixed_s512_o77", "full", ret)], g[("fixed_s512_o77", "short", ret)]
            d = [float(S[i]["pr_mrr"]) - float(F[i]["pr_mrr"]) for i in sorted(F)]
            out.append(f"  fixed_s512_o77 short - full, {ret:6s}: MRR@5 {mean(d):+.3f} p={perm(d):.4f}")
        out.append("")
    text = "\n".join(out)
    print(text)
    with open(os.path.join(RES, "hybrid_short_query_test.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
