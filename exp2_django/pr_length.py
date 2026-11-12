"""Queue 1a (analysis only): whole-PR length in Exp 1 token units and answer rates by gold-PR length.

    python pr_length.py      # -> results/pr_length_pool.json, results/pr_length_tertiles.csv

Length = Exp 1 chunking.count_tokens on the whole pr_document text (the unit of Exp 1's pool size
filter and of the 2,560 packing budget's chunk sizes).
(1) Pool A size filter as recorded by Exp 1's build (`_pool_A2000.json`, read-only).
(2) Pool A (2,231 PRs): median, p90, max, and how many exceed 512, 2,560, 5,000, 10,000.
(3) 50 test answerables split into gold-PR length tertiles by rank (17 / 17 / 16; ties broken by
    question id); per tertile x model x arm x prompt, answered and overlap-cited counts. No tests.
"""
import csv
import json
import os
import statistics as st

from common import PRS, doc, pool_numbers, read_jsonl
from chunking import count_tokens                # Exp 1, on sys.path via common
from score import auto
from stats_arms import ARM, FILES

PROMPT = {"c": "v2", "c3": "v3"}
ORDER = ["F0", "S0", "S0-G", "S-0.25"]
THRESH = (512, 2560, 5000, 10000)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main():
    with open(os.path.join(PRS, "_pool_A2000.json"), encoding="utf-8") as f:
        build = json.load(f)
    ex = build["excluded"]
    filt = {"max_files": build["max_files"], "max_tokens": build["max_tokens"],
            "n_excluded": build["n_excluded"], "files_over": sum(e["files"] > build["max_files"] for e in ex),
            "tokens_over": sum(e["tokens"] > build["max_tokens"] for e in ex),
            "both": sum(e["files"] > build["max_files"] and e["tokens"] > build["max_tokens"] for e in ex),
            "truncated_file_list": sum(bool(e.get("truncated")) for e in ex),
            "n_same_ticket": build.get("n_same_ticket"), "fixing_over_limits": build["fixing_over_limits"]}

    pool = pool_numbers()
    L = {n: count_tokens(doc(n)["text"]) for n in pool}
    v = list(L.values())
    pstats = {"n": len(v), "median": st.median(v), "p90": pct(v, 0.9), "max": max(v)} | \
        {f"over_{t}": sum(x > t for x in v) for t in THRESH}

    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    ans = sorted((q for q in qs.values() if q["type"] == "answerable" and q["split"] == "test"),
                 key=lambda q: (L[q["pr_number"]], q["id"]))
    assert len(ans) == 50
    tert = {q["id"]: (0 if i < 17 else 1 if i < 34 else 2) for i, q in enumerate(ans)}
    bounds = [(L[ans[a]["pr_number"]], L[ans[b]["pr_number"]]) for a, b in ((0, 16), (17, 33), (34, 49))]

    rows = []
    for model, path in FILES.items():
        cnt = {}
        for r in read_jsonl(path):
            if r["id"] not in tert:
                continue
            a = auto(r, qs[r["id"]])
            ctx, pk = r["condition"].split(":")
            k = (ARM[ctx], PROMPT[pk], tert[r["id"]])
            c = cnt.setdefault(k, [0, 0])
            answered = not a["abstained"] and not a["empty_answer"]
            c[0] += answered
            c[1] += answered and a["overlap_cited"]
        for p in ("v2", "v3"):
            for arm in ORDER:
                row = {"model": model, "prompt": p, "arm": arm}
                for t in range(3):
                    row[f"T{t + 1}_answered"], row[f"T{t + 1}_overlap_cited"] = cnt[(arm, p, t)]
                rows.append(row)
    with open("results/pr_length_tertiles.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    out = {"pool_a_size_filter": filt, "pool_a_lengths": pstats,
           "tertiles": [{"tertile": t + 1, "n": [17, 17, 16][t], "tokens_min": b[0], "tokens_max": b[1],
                         "ids": [q["id"] for q in ans if tert[q["id"]] == t]} for t, b in enumerate(bounds)]}
    with open("results/pr_length_pool.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out[k] for k in ("pool_a_size_filter", "pool_a_lengths")}, indent=1))
    for t in out["tertiles"]:
        print(f"T{t['tertile']}: n={t['n']} tokens {t['tokens_min']}-{t['tokens_max']}")
    print("model        pr  arm    | T1 ans oc | T2 ans oc | T3 ans oc")
    for r in rows:
        print(f"{r['model']:12} {r['prompt']:3} {r['arm']:6} | " + " | ".join(
            f"{r[f'T{t}_answered']:>2} {r[f'T{t}_overlap_cited']:>2}" for t in (1, 2, 3)))


if __name__ == "__main__":
    main()
