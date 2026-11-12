"""Hallucination limit test, H0 vs F0 (tuning_rule_hybrid_limit.md; exploratory, outside every Holm family).

    python limit_hybrid.py      # -> results/limit_hybrid.csv, results/limit_hybrid_coverage.csv

Difference = H0 minus F0 (negative = fewer hallucinations with hybrid). Per model x prompt: Newcombe's paired
score interval (method 10). Pooled per model and over all 4 cells: mean difference per cell, PR-family
percentile bootstrap, 1,000 reps, seed 42. Reads existing rows only.
"""
import csv
import random
from math import comb, sqrt

from common import git_commit, read_jsonl
from stats_arms import FILES
from stats_correctness import load_labels
from stats_hybrid import COND, H0, PK, load, write

Z = 1.959964
BOOT, SEED = 1000, 42
OUTCOMES = {"unanswerable answered /17": ("unq", "answered"), "answered wrong /50": ("ansq", "wrong")}


def wilson(x, n):
    p, d = x / n, 1 + Z * Z / n
    c, h = p + Z * Z / (2 * n), Z * sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def newcombe(a, b, c, d):
    """95% CI for p1 - p2 from a paired table: a = both, b = only 1, c = only 2, d = neither."""
    n = a + b + c + d
    p1, p2 = (a + b) / n, (a + c) / n
    l1, u1 = wilson(a + b, n)
    l2, u2 = wilson(a + c, n)
    den = (a + b) * (c + d) * (a + c) * (b + d)
    phi = (a * d - b * c) / sqrt(den) if den else 0.0
    lo2 = (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2
    hi2 = (p2 - l2) ** 2 - 2 * phi * (p2 - l2) * (u1 - p1) + (u1 - p1) ** 2
    return p1 - p2 - sqrt(max(lo2, 0.0)), p1 - p2 + sqrt(max(hi2, 0.0))


def coverage(n, pa, pb, pc):
    """Exact probability that the interval contains the true difference, enumerating every table."""
    pd = 1 - pa - pb - pc
    true, cov = pb - pc, 0.0
    for a in range(n + 1):
        for b in range(n + 1 - a):
            for c in range(n + 1 - a - b):
                d = n - a - b - c
                prob = (comb(n, a) * comb(n - a, b) * comb(n - a - b, c) * pa ** a * pb ** b * pc ** c * pd ** d)
                lo, hi = newcombe(a, b, c, d)
                if lo <= true <= hi:
                    cov += prob
    return cov


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    labels = load_labels("judging/codex_labels.csv")
    commit = git_commit()
    cov_rows = []
    for n in (17, 50):
        for name, pa, pb, pc in (("low rate, no change", 0.10, 0.05, 0.05), ("mid rate, no change", 0.50, 0.10, 0.10),
                                 ("high rate, no change", 0.70, 0.05, 0.05), ("mid rate, real fall", 0.40, 0.05, 0.20)):
            cov_rows.append({"n": n, "scenario": name, "both": pa, "only_H0": pb, "only_F0": pc,
                             "coverage": round(coverage(n, pa, pb, pc), 4), "nominal": 0.95})
    write("results/limit_hybrid_coverage.csv", cov_rows)

    rows, per_q = [], {}
    for model, f0_path in FILES.items():
        F = load(f0_path, COND["F0"], qs, labels)
        H = load(H0[model], COND["H0"], qs, labels)
        for prompt in PK:
            ids = [i for p, i in H if p == prompt]
            for name, (grp, field) in OUTCOMES.items():
                use = sorted(i for i in ids if H[(prompt, i)][grp])
                x = [H[(prompt, i)][field] for i in use]
                y = [F[(prompt, i)][field] for i in use]
                b = sum(p and not q for p, q in zip(x, y))
                c = sum(q and not p for p, q in zip(x, y))
                a = sum(p and q for p, q in zip(x, y))
                n = len(use)
                lo, hi = newcombe(a, b, c, n - a - b - c)
                rows.append({"scope": "cell", "model": model, "prompt": prompt, "outcome": name, "n": n,
                             "F0": sum(y), "H0": sum(x), "b_only_H0": b, "c_only_F0": c,
                             "diff_questions": round(b - c, 2),
                             "lower_limit_questions": round(lo * n, 2), "upper_limit_questions": round(hi * n, 2),
                             "floor_questions": -sum(y), "method": "Newcombe method 10"})
                for i, p_, q_ in zip(use, x, y):
                    per_q[(name, model, prompt, i)] = int(p_) - int(q_)

    scopes = [("model", m, lambda k, m=m: k[1] == m) for m in FILES] + [("all 4 cells", "all", lambda k: True)]
    for name in OUTCOMES:
        for scope, label, keep in scopes:
            items = [(k, v) for k, v in per_q.items() if k[0] == name and keep(k)]
            ncell = len({k[1:3] for k, _ in items})
            fam = {}
            for k, v in items:
                fam.setdefault(qs[k[3]]["pr_number"], []).append(v)
            keys = sorted(fam)
            est = sum(v for _, v in items) / ncell
            rng, reps = random.Random(SEED), []
            for _ in range(BOOT):
                reps.append(sum(sum(fam[rng.choice(keys)]) for _ in keys) / ncell)
            reps.sort()
            rows.append({"scope": scope, "model": label, "prompt": "pooled", "outcome": name,
                         "n": len({k[3] for k, _ in items}), "F0": "", "H0": "", "b_only_H0": "", "c_only_F0": "",
                         "diff_questions": round(est, 2), "lower_limit_questions": round(reps[24], 2),
                         "upper_limit_questions": round(reps[974], 2), "floor_questions": "",
                         "method": f"mean per cell; PR-family bootstrap, {BOOT} reps, seed {SEED}, {len(keys)} families"})
    for r in rows:
        r["label"], r["git_commit"] = "exploratory; no pass/fail margin", commit
    write("results/limit_hybrid.csv", rows)
    print("--- coverage")
    for r in cov_rows:
        print(r)
    print("--- limits")
    for r in rows:
        print({k: r[k] for k in ("scope", "model", "prompt", "outcome", "n", "F0", "H0", "b_only_H0", "c_only_F0",
                                 "diff_questions", "lower_limit_questions", "upper_limit_questions")})


if __name__ == "__main__":
    main()
