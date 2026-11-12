"""Prompt v2 -> v3 as mitigation (test arms, ungated, strict abstention).

    python v2v3_mitigation.py      # -> results/v2v3_mitigation.csv (+ printed tables)
    python v2v3_mitigation.py --exclude-clued   # P3: 15 unanswerables -> results/v2v3_mitigation_excl15.csv

Per model x arm: answered unanswerables (of 17: 5 no-reason test, 5 no-reason dev, 5 whole PR
excluded, PR kept rk16129 and rk9789) and overlap-cited (of 50 test answerables) under v2 and
v3, with exact McNemar v2 vs v3 on each (b = v2 only, c = v3 only). No multiple-test correction.
Per model: distinct unanswerable questions (of 17) answered in at least one arm, v2 vs v3.
"""
import argparse
import csv

from common import read_jsonl
from faithfulness import PR_KEPT
from score import auto
from stats_arms import ARM, FILES, mcnemar

PROMPT = {"c": "v2", "c3": "v3"}
ORDER = ["F0", "S0", "S0-G", "S-0.25"]


def main(args):
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    un_ids = sorted(i for i, q in qs.items() if q["type"] in ("no_reason", "removed") or i in PR_KEPT)
    ans_ids = sorted(i for i, q in qs.items() if q["type"] == "answerable" and q["split"] == "test")
    if args.exclude_clued:
        un_ids = [i for i in un_ids if i not in ("nr9172", "nr13883")]
    n_un = len(un_ids)
    assert n_un == (15 if args.exclude_clued else 17) and len(ans_ids) == 50
    rows, distinct = [], []
    for model, path in FILES.items():
        o = {}
        for r in read_jsonl(path):
            if r["id"] not in un_ids and r["id"] not in ans_ids:
                continue
            a = auto(r, qs[r["id"]])
            ctx, pk = r["condition"].split(":")
            answered = not a["abstained"] and not a["empty_answer"]
            o[(ARM[ctx], PROMPT[pk], r["id"])] = {"answered": answered, "overlap_cited": answered and a["overlap_cited"]}
        for arm in ORDER:
            row = {"model": model, "arm": arm}
            for name, ids, key in (("unanswerable_answered", un_ids, "answered"), ("overlap_cited", ans_ids, "overlap_cited")):
                x = [o[(arm, "v2", i)][key] for i in ids]
                y = [o[(arm, "v3", i)][key] for i in ids]
                p, b, c = mcnemar(x, y)
                row |= {f"{name}_v2": sum(x), f"{name}_v3": sum(y), f"{name}_b": b, f"{name}_c": c,
                        f"{name}_p": round(p, 4)}
            rows.append(row)
        d = {p: sorted(i for i in un_ids if any(o[(arm, p, i)]["answered"] for arm in ORDER)) for p in ("v2", "v3")}
        distinct.append({"model": model, "v2": len(d["v2"]), "v3": len(d["v3"]),
                         "v2_ids": " ".join(d["v2"]), "v3_ids": " ".join(d["v3"])})
    with open("results/v2v3_mitigation" + ("_excl15" if args.exclude_clued else "") + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"model        arm    | unanswerable answered/{n_un} v2 v3 (b/c, p) | overlap-cited/50 v2 v3 (b/c, p)")
    for r in rows:
        print(f"{r['model']:12} {r['arm']:6} | {r['unanswerable_answered_v2']:>2} {r['unanswerable_answered_v3']:>2} "
              f"({r['unanswerable_answered_b']}/{r['unanswerable_answered_c']}, p={r['unanswerable_answered_p']}) | "
              f"{r['overlap_cited_v2']:>2} {r['overlap_cited_v3']:>2} ({r['overlap_cited_b']}/{r['overlap_cited_c']}, p={r['overlap_cited_p']})")
    print("\nDistinct unanswerable questions answered in >= 1 arm")
    for d in distinct:
        print(f"{d['model']:12} v2 {d['v2']}/{n_un} [{d['v2_ids']}]  v3 {d['v3']}/{n_un} [{d['v3_ids']}]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude-clued", action="store_true")
    main(ap.parse_args())
