"""Statistics for Experiment 1 (test set): bootstrap CIs and paired significance tests.

    python stats.py results/swe_exp1_test_per_query.csv
    python stats.py results/swe_exp1_test_per_query.csv results/swe_exp1_test_untuned_per_query.csv

- 95% bootstrap CI of each mean (resample queries, 1,000x, fixed seed).
- Paired tests between two conditions on the SAME queries:
    Hit@5 (0/1)  -> exact McNemar test (binomial on the discordant pairs)
    MRR@5        -> paired permutation test (random sign flips of the per-query differences,
                    10,000x) + a paired bootstrap 95% CI of the difference.
Comparisons: retrievers within each chunking, chunkings within each retriever, and (if two
files are given) each condition in file 1 vs the same condition in file 2 (e.g. tuned vs
untuned). Differences with p >= 0.05 are reported as not significant.
"""
import csv
import random
import sys
from collections import defaultdict
from math import comb


def bootstrap_ci(values, n_boot=1000, seed=0, alpha=0.05):
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return means[int(alpha / 2 * n_boot)], means[int((1 - alpha / 2) * n_boot) - 1]


def mcnemar_exact(a, b):
    """Two-sided exact McNemar p-value for paired 0/1 outcomes."""
    n01 = sum(1 for x, y in zip(a, b) if x and not y)
    n10 = sum(1 for x, y in zip(a, b) if y and not x)
    n = n01 + n10
    if n == 0:
        return 1.0, n01, n10
    k = min(n01, n10)
    p = 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, p), n01, n10


def paired_permutation(a, b, n_perm=10000, seed=0):
    """Two-sided p-value for mean(a - b) != 0 by random sign flips of the differences."""
    d = [x - y for x, y in zip(a, b)]
    obs = abs(sum(d))
    if obs == 0:
        return 1.0
    rng = random.Random(seed)
    hits = sum(abs(sum(x if rng.random() < 0.5 else -x for x in d)) >= obs - 1e-12
               for _ in range(n_perm))
    return (hits + 1) / (n_perm + 1)


def paired_bootstrap_diff(a, b, n_boot=1000, seed=0):
    return bootstrap_ci([x - y for x, y in zip(a, b)], n_boot, seed)


# ---------- per-query CSV -> conditions ----------
def load_conditions(path, query_set="full", label=""):
    """{condition name: {instance_id: row}} for one query set."""
    conds = defaultdict(dict)
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("query_set", "full") != query_set:
                continue
            name = f"{label}{r['chunking']}|{r['retriever']}"
            name += f"|alpha={float(r.get('alpha') or 0):g}"      # relation factor
            if r.get("retriever") in ("bm25", "hybrid") and r.get("k1"):
                name += f"|k1={r['k1']},b={r['b']}"
            conds[name][r["instance_id"]] = r
    return conds


def _vals(cond, ids, metric):
    return [float(cond[i][metric]) for i in ids]


def compare(name_a, a, name_b, b):
    ids = sorted(set(a) & set(b))
    ha, hb = _vals(a, ids, "pr_hit"), _vals(b, ids, "pr_hit")
    ma, mb = _vals(a, ids, "pr_mrr"), _vals(b, ids, "pr_mrr")
    p_hit, n01, n10 = mcnemar_exact(ha, hb)
    p_mrr = paired_permutation(ma, mb)
    lo, hi = paired_bootstrap_diff(ma, mb)
    sig = lambda p: "significant" if p < 0.05 else "not significant"
    print(f"  {name_a}  vs  {name_b}  (n={len(ids)})")
    print(f"    Hit@5 {sum(ha)/len(ha):.3f} vs {sum(hb)/len(hb):.3f}: McNemar p={p_hit:.3f} "
          f"({n01} only-A, {n10} only-B) -> {sig(p_hit)}")
    print(f"    MRR@5 {sum(ma)/len(ma):.3f} vs {sum(mb)/len(mb):.3f}: diff 95% CI "
          f"[{lo:+.3f}, {hi:+.3f}], permutation p={p_mrr:.3f} -> {sig(p_mrr)}")
    bids = [i for i in ids if a[i].get("budget_recall") not in (None, "")
            and b[i].get("budget_recall") not in (None, "")]
    if bids:                                     # what the LLM receives (token budget)
        ra, rb = _vals(a, bids, "budget_recall"), _vals(b, bids, "budget_recall")
        p_r = paired_permutation(ra, rb)
        rlo, rhi = paired_bootstrap_diff(ra, rb)
        print(f"    budget line recall {sum(ra)/len(ra):.3f} vs {sum(rb)/len(rb):.3f} "
              f"(n={len(bids)}): diff 95% CI [{rlo:+.3f}, {rhi:+.3f}], permutation "
              f"p={p_r:.3f} -> {sig(p_r)}")


def summarise(conds):
    print(f"{'condition':<50}{'n':>5}{'Hit@5':>8}{'95% CI':>17}{'MRR@5':>8}{'95% CI':>17}")
    for name, c in sorted(conds.items()):
        h = [float(r["pr_hit"]) for r in c.values()]
        m = [float(r["pr_mrr"]) for r in c.values()]
        hl, hh = bootstrap_ci(h)
        ml, mh = bootstrap_ci(m)
        print(f"{name:<50}{len(h):>5}{sum(h)/len(h):>8.3f}  [{hl:.3f}, {hh:.3f}]"
              f"{sum(m)/len(m):>8.3f}  [{ml:.3f}, {mh:.3f}]")


def main(paths, query_set="full"):
    conds = load_conditions(paths[0], query_set)
    print(f"=== {paths[0]} (query set: {query_set}) ===")
    summarise(conds)
    parts = {n: n.split("|") for n in conds}
    print("\n=== Retrievers compared within each chunking (same relation factor) ===")
    for a in conds:
        for b in conds:
            if a < b and parts[a][0] == parts[b][0] and parts[a][2] == parts[b][2]:
                compare(a, conds[a], b, conds[b])
    print("\n=== Relation factor: links (alpha > 0) vs no links (alpha 0), same chunking + "
          "retriever ===")
    for a in conds:
        for b in conds:
            if (parts[a][:2] == parts[b][:2] and parts[a][3:] == parts[b][3:]
                    and parts[b][2] == "alpha=0" and parts[a][2] != "alpha=0"):
                compare(a, conds[a], b, conds[b])
    print("\n=== Chunkings compared within each retriever ===")
    for a in conds:
        for b in conds:
            if a < b and parts[a][1:] == parts[b][1:] and parts[a][0] != parts[b][0]:
                compare(a, conds[a], b, conds[b])
    if len(paths) > 1:
        other = load_conditions(paths[1], query_set)
        print(f"\n=== {paths[0]} vs {paths[1]} (same condition) ===")
        for a in conds:
            if a in other:
                compare(f"[1] {a}", conds[a], f"[2] {a}", other[a])
            else:                                     # tuned settings have other names:
                same_ret = [o for o in other if o.split("|")[1] == parts[a][1]
                            and o.split("|")[0].split("_")[0] == parts[a][0].split("_")[0]
                            and o.split("|")[2] == parts[a][2]]
                for o in same_ret:
                    compare(f"[1] {a}", conds[a], f"[2] {o}", other[o])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    qs = "short" if "--short" in sys.argv else "full"
    if not args:
        sys.exit(__doc__)
    main(args, qs)
