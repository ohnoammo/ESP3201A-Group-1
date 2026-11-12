"""Pre-declared tests for the scaled Exp 1 on gitlab-runner, alpha 1 vs alpha 0 (rule: tuning_rule_exp1_scale.md).

  python exp1_gitlab_stats.py --pool A2000 --exclude-pilot A270     primary: tasks not seen in the pilot
  python exp1_gitlab_stats.py --pool A2000                          sensitivity: all tasks
"""
import argparse
import csv
import json
import os
import random
from math import comb

METRICS = ("budget_recall", "budget_precision", "budget_f1")


def mcnemar(b, c):
    n = b + c
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n) if n else 1.0


def permutation(diffs, n=10000, seed=0):
    rng, obs = random.Random(seed), abs(sum(diffs))
    hits = sum(abs(sum(d if rng.random() < .5 else -d for d in diffs)) >= obs - 1e-12 for _ in range(n))
    return (hits + 1) / (n + 1)


def holm(ps):
    order, out, top = sorted(range(len(ps)), key=lambda i: ps[i]), [0] * len(ps), 0
    for rank, i in enumerate(order):
        top = max(top, min(1, ps[i] * (len(ps) - rank)))
        out[i] = top
    return out


def main(a):
    rows = list(csv.DictReader(open(os.path.join("results", f"exp1_gitlab_{a.pool}_per_query.csv"), encoding="utf-8")))
    out = set()
    if a.exclude_pilot:
        path = os.path.join("exp1_gitlab", f"tasks_{a.exclude_pilot}.json")
        out = {str(t["pr_number"]) for t in json.load(open(path, encoding="utf-8"))["tasks"]}
    x = {r["pr"]: r for r in rows if r["alpha"] == "0.0" and r["pr"] not in out}
    y = {r["pr"]: r for r in rows if r["alpha"] == "1.0" and r["pr"] not in out}
    gold = lambda r: r["gold_in_budget"] == "True"
    lost = sum(gold(x[k]) and not gold(y[k]) for k in x)
    won = sum(gold(y[k]) and not gold(x[k]) for k in x)
    res = [("gold_in_budget", f"{sum(map(gold, x.values()))} -> {sum(map(gold, y.values()))} of {len(x)}; "
            f"lost {lost}, gained {won}", mcnemar(lost, won))]
    for m in METRICS:
        v = lambda r: float(r[m] or 0)              # no chunk scored = 0, as in the mean below
        d = [v(y[k]) - v(x[k]) for k in x]
        res.append((m, f"{sum(map(v, x.values())) / len(x):.3f} -> {sum(map(v, y.values())) / len(x):.3f}; "
                    f"up {sum(i > 0 for i in d)}, down {sum(i < 0 for i in d)}", permutation(d)))
    for (name, text, p), h in zip(res, holm([r[2] for r in res])):
        print(f"{name:<18}{text:<44} p {p:.4f}  Holm {h:.4f}")
    # Sensitivity: Wilcoxon signed-rank (zero differences dropped), its own Holm family; McNemar kept
    from scipy.stats import wilcoxon
    ps = [res[0][2]]
    for m in METRICS:
        nz = [float(y[k][m] or 0) - float(x[k][m] or 0) for k in x]
        nz = [d for d in nz if d]
        ps.append(wilcoxon(nz).pvalue if nz else 1.0)
    print("Wilcoxon sensitivity:")
    for (name, _, _), p, h in zip(res, ps, holm(ps)):
        print(f"{name:<18}p {p:.4f}  Holm {h:.4f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="A2000")
    ap.add_argument("--exclude-pilot")
    main(ap.parse_args())
