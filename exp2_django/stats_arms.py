"""Paired exact McNemar tests on the 50 test answerables (per model).

    python stats_arms.py      # -> results/stats_test_arms.csv
    python stats_arms.py --hedged-as-abstained   # sensitivity -> results/stats_test_arms_hedged_abstained.csv
    python stats_arms.py --contain    # P2 sensitivity: contain-cited only, 49 questions (q14748 out)
                                      # -> results/stats_test_arms_contain.csv (20 tests, own Holm)

Comparisons (James, 23 Oct): F0 vs S0, S0 vs S0-G, S0-G vs S-0.25 (within each prompt), and
v2 vs v3 within each arm. Outcomes per question: answered, abstained-with-span (abstained while an
answer span was in context), overlap-cited (was "right-chunk-cited"). Exact two-sided McNemar on discordant pairs.
60 tests = 2 models x 10 pairs x 3 outcomes, Holm-adjusted as one family. min_p is the smallest
exact p attainable with b+c discordant pairs (2^(1-(b+c))); tests with b+c < 5 cannot reach 0.05.
"""
import argparse
import csv
from math import comb

from common import read_jsonl
from score import auto

FILES = {"4b-instruct": "results/gen_test_arms_4b-instruct.jsonl", "8b": "results/gen_test_arms_8b.jsonl"}
ARM = {"pack-fixed-0-score": "F0", "pack-struct-0-score": "S0", "pack-struct-0-grouped": "S0-G",
       "pack-struct-0.25-grouped": "S-0.25"}


def mcnemar(a, b):
    n01 = sum(1 for x, y in zip(a, b) if x and not y)
    n10 = sum(1 for x, y in zip(a, b) if y and not x)
    n = n01 + n10
    if n == 0:
        return 1.0, n01, n10
    p = 2 * sum(comb(n, i) for i in range(min(n01, n10) + 1)) / 2 ** n
    return min(1.0, p), n01, n10


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - k) * ps[i]))
        adj[i] = run
    return adj


def outcomes(path, qs, hedged_as_abstained=False):
    out = {}
    for r in read_jsonl(path):
        q = qs[r["id"]]
        if r["type"] != "answerable" or q["split"] != "test":
            continue
        ctx, pk = r["condition"].split(":")
        a = auto(r, q)
        abst = a["abstained"] or (hedged_as_abstained and a["hedged"])
        out[(ARM[ctx], {"c": "v2", "c3": "v3"}[pk], r["id"])] = {
            "answered": not abst and not a["empty_answer"],
            "abstained_with_span": abst and r["span_in_context"]["any"],
            "overlap_cited": a["overlap_cited"], "contain_cited": a["contain_cited"]}
    return out


def main(args):
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    ids = sorted(q["id"] for q in qs.values() if q["type"] == "answerable" and q["split"] == "test")
    if args.contain:                     # q14748 has no fully containing structural chunk
        ids = [i for i in ids if i != "q14748"]
    metrics = ("contain_cited",) if args.contain else ("answered", "abstained_with_span", "overlap_cited")
    pairs = [(("F0", p), ("S0", p)) for p in ("v2", "v3")] + \
            [(("S0", p), ("S0-G", p)) for p in ("v2", "v3")] + \
            [(("S0-G", p), ("S-0.25", p)) for p in ("v2", "v3")] + \
            [((arm, "v2"), (arm, "v3")) for arm in ("F0", "S0", "S0-G", "S-0.25")]
    rows = []
    for model, path in FILES.items():
        o = outcomes(path, qs, args.hedged_as_abstained)
        for (a1, p1), (a2, p2) in pairs:
            for m in metrics:
                x = [o[(a1, p1, i)][m] for i in ids]
                y = [o[(a2, p2, i)][m] for i in ids]
                p, n01, n10 = mcnemar(x, y)
                rows.append({"model": model, "A": f"{a1}/{p1}", "B": f"{a2}/{p2}", "outcome": m,
                             "A_count": sum(x), "B_count": sum(y), "only_A": n01, "only_B": n10,
                             "p": p, "min_p": min(1.0, 2.0 ** (1 - n01 - n10))})
    for r, h in zip(rows, holm([r["p"] for r in rows])):
        r["p_holm"] = h
    for r in rows:
        for k in ("p", "min_p", "p_holm"):
            r[k] = round(r[k], 4)
    out = "results/stats_test_arms_contain.csv" if args.contain else \
        "results/stats_test_arms_hedged_abstained.csv" if args.hedged_as_abstained else \
        "results/stats_test_arms.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{'model':12} {'A':10} {'B':10} {'outcome':20} {'b':>3} {'c':>3} {'p':>7} {'Holm p':>7}")
    for r in rows:
        if r["only_A"] + r["only_B"] >= 5:
            print(f"{r['model']:12} {r['A']:10} {r['B']:10} {r['outcome']:20} {r['only_A']:>3} "
                  f"{r['only_B']:>3} {r['p']:>7.4f} {r['p_holm']:>7.4f}")
    print(f"{len(rows)} tests; {sum(r['only_A'] + r['only_B'] >= 5 for r in rows)} with b+c >= 5; "
          f"{sum(r['p'] < 0.05 for r in rows)} with p < 0.05; {sum(r['p_holm'] < 0.05 for r in rows)} "
          f"with Holm p < 0.05")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hedged-as-abstained", action="store_true")
    ap.add_argument("--contain", action="store_true")
    main(ap.parse_args())
