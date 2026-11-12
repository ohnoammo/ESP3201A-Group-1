"""Summary of results/faithfulness_test_arms.jsonl per model x arm x prompt.

    python summarise_faithfulness.py      # -> results/summary_faithfulness.csv
    python summarise_faithfulness.py --in results/faithfulness_W.jsonl --out results/summary_faithfulness_W.csv
                                          # arm W-F (condition wpr-fixed); the same for arm H0 (packh-fixed-0-score)

For each judge (MiniCheck, HHEM) and premise (cited chunks, full context): mean of the row-level
min and of the row-level mean over sentences, and the share of rows whose min is >= 0.5 (every
sentence supported). Rows with no valid cited chunk have no "cited" score (n_cited_scored).
Cited chunks is the primary premise, full context secondary (HANDOVER, 23 Oct).
gap_<judge> = rows where cited min minus full min > 0.1.
"""
import argparse
import csv
import statistics as st

from common import read_jsonl
from stats_arms import ARM

MODEL = {"qwen3:4b-instruct-2507-q4_K_M": "4b-instruct", "qwen3:8b": "8b"}
ORDER = ["F0", "S0", "S0-G", "S-0.25", "W-F", "H0"]
ARMS = ARM | {"wpr-fixed": "W-F", "packh-fixed-0-score": "H0"}


def main(a):
    recs = read_jsonl(a.inp)
    groups = {}
    for r in recs:
        ctx, pk = r["condition"].split(":")
        groups.setdefault((MODEL.get(r["model"], r["model"]), ARMS[ctx], {"c": "v2", "c3": "v3"}[pk]), []).append(r)
    rows = []
    for (m, arm, p), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][2], ORDER.index(kv[0][1]))):
        row = {"model": m, "arm": arm, "prompt": p, "n": len(rs)}
        for prem in ("cited", "full"):
            for j in ("minicheck", "hhem"):
                mins = [x[f"{j}_{prem}_min"] for x in rs if x[f"{j}_{prem}_min"] is not None]
                means = [x[f"{j}_{prem}_mean"] for x in rs if x[f"{j}_{prem}_mean"] is not None]
                row[f"{j}_{prem}_min"] = round(st.mean(mins), 3) if mins else None
                row[f"{j}_{prem}_mean"] = round(st.mean(means), 3) if means else None
                row[f"{j}_{prem}_all_supported"] = round(sum(v >= 0.5 for v in mins) / len(mins), 3) if mins else None
            row[f"n_{prem}_scored"] = sum(x[f"minicheck_{prem}_min"] is not None for x in rs)
        for j in ("minicheck", "hhem"):
            row[f"gap_{j}"] = sum(x[f"{j}_cited_min"] is not None and
                                  x[f"{j}_cited_min"] - x[f"{j}_full_min"] > 0.1 for x in rs)
        rows.append(row)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(recs)} rows")
    print("model        arm    pr   n  | PRIMARY cited: MiniCheck min/mean all-sup | HHEM min/mean all-sup "
          "| secondary full: MiniCheck min/mean | HHEM min/mean | gap MC/HHEM")
    for r in rows:
        print(f"{r['model']:12} {r['arm']:6} {r['prompt']:3} {r['n']:>3} | "
              f"{r['minicheck_cited_min']} / {r['minicheck_cited_mean']} {r['minicheck_cited_all_supported']} | "
              f"{r['hhem_cited_min']} / {r['hhem_cited_mean']} {r['hhem_cited_all_supported']} | "
              f"{r['minicheck_full_min']} / {r['minicheck_full_mean']} | "
              f"{r['hhem_full_min']} / {r['hhem_full_mean']} | {r['gap_minicheck']}/{r['gap_hhem']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="results/faithfulness_test_arms.jsonl")
    ap.add_argument("--out", default="results/summary_faithfulness.csv")
    main(ap.parse_args())
