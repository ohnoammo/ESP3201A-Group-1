"""Post hoc Exp 1 comparison of relation links (dense retrieval, test set, both pools).

Labelled POST HOC in the report (Section 4.2): it was added after the test results were seen.
  1. Structural + links vs size-matched fixed + links (budget line recall).
  2. Structural + links vs fixed 512/77 + links (budget line recall).
Also prints gold-in-budget (alpha 0 -> locked alpha) for the size-matched baseline (Table 5).

Each condition uses its locked alpha from the dev set (Table 2; size-matched uses the fixed-size alpha).
Test: paired permutation (random sign flips of the per-query differences, 10,000 draws, seed 0), two-sided,
the same kind of test as stats.py. Unadjusted.

Run from exp1_retrieval/:   python posthoc_links_test.py > results/posthoc_links_test.txt
Reads only results/swe_exp1_test{,H}_tuned_per_query.csv (standard library only).
"""
import csv
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
POOLS = {
    # pool: (file, size-matched chunking, alpha fixed 512, alpha structural, alpha size-matched)
    "A": ("swe_exp1_test_tuned_per_query.csv", "fixed_s110_o0", "1.0", "0.5", "1.0"),
    "H": ("swe_exp1_testH_tuned_per_query.csv", "fixed_s111_o0", "0.5", "0.25", "0.5"),
}
N_PERM = 10000


def load(path, chunking, alpha):
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r["chunking"] == chunking and r["retriever"] == "dense" and r["alpha"] == alpha
                    and r["query_set"] == "full"):
                out[r["instance_id"]] = (float(r["budget_recall"]), float(r["gold_in_budget"]))
    return out


def perm_p(x, y, n=N_PERM, seed=0):
    d = [a - b for a, b in zip(x, y)]
    obs = abs(sum(d))
    rng = random.Random(seed)
    hits = sum(abs(sum(v if rng.random() < 0.5 else -v for v in d)) >= obs - 1e-12 for _ in range(n))
    return (hits + 1) / (n + 1)


def main():
    print("Post hoc: relation links, dense, test set (n = 181 per pool). Paired permutation, two-sided, unadjusted.\n")
    for pool, (fn, sm, a_fix, a_str, a_sm) in POOLS.items():
        path = os.path.join(HERE, "results", fn)
        S = load(path, "struct_c256", a_str)
        F = load(path, "fixed_s512_o77", a_fix)
        M = load(path, sm, a_sm)
        M0 = load(path, sm, "0.0")
        ids = sorted(S)
        assert len(ids) == 181 and set(ids) == set(F) == set(M) == set(M0), "conditions cover different queries"
        mean = lambda d, i=0: sum(d[k][i] for k in ids) / len(ids)
        rs, rf, rm = ([d[k][0] for k in ids] for d in (S, F, M))
        print(f"Pool {pool} ({fn})")
        print(f"  budget recall with links: structural (a={a_str}) {mean(S):.3f} | fixed 512/77 (a={a_fix}) "
              f"{mean(F):.3f} | size-matched {sm} (a={a_sm}) {mean(M):.3f}")
        print(f"  structural+links vs size-matched+links: diff {mean(S) - mean(M):+.3f}, p = {perm_p(rs, rm):.4f}")
        print(f"  structural+links vs fixed 512+links:    diff {mean(S) - mean(F):+.3f}, p = {perm_p(rs, rf):.4f}")
        print(f"  size-matched gold-in-budget: {mean(M0, 1):.3f} -> {mean(M, 1):.3f} (alpha 0 -> {a_sm})\n")


if __name__ == "__main__":
    main()
