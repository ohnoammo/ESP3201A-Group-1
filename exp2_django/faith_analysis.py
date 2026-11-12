"""Faithfulness checks on the answered test answerables (results/faithfulness_test_arms.jsonl).

    python faith_analysis.py      # -> results/faith_premise_length.csv, results/faith_paired.csv

(1) Premise length: cited-premise word count (whole cited chunks, as faithfulness.py builds the
    premise) per model x arm x prompt (mean, median); within each model x prompt, Spearman
    correlation between that word count and MiniCheck cited min. Rows with no cited premise are
    left out.
(2) Paired (EXPLORATORY, no multiple-test correction): for each stats_arms.py pair, MiniCheck
    cited min on questions answered in both arms with a cited score in both; n, mean difference
    (B - A), Wilcoxon signed-rank p (scipy default: zero differences dropped).
(3) Unanswerable rows (results/faithfulness_unanswerable.jsonl, 141): cited-premise median words
    per model x arm; Spearman words vs MiniCheck cited min per model and pooled. Rows with no
    cited premise left out. -> results/faith_premise_length_unanswerable.csv
"""
import csv
import statistics as st

from scipy.stats import spearmanr, wilcoxon

from common import read_jsonl
from faithfulness import CITE
from run_generation import pack_context, short_id
from stats_arms import ARM

MODEL = {"qwen3:4b-instruct-2507-q4_K_M": "4b-instruct", "qwen3:8b": "8b"}
PROMPT = {"c": "v2", "c3": "v3"}
ORDER = ["F0", "S0", "S0-G", "S-0.25"]
PAIRS = [(("F0", p), ("S0", p)) for p in ("v2", "v3")] + \
        [(("S0", p), ("S0-G", p)) for p in ("v2", "v3")] + \
        [(("S0-G", p), ("S-0.25", p)) for p in ("v2", "v3")] + \
        [((arm, "v2"), (arm, "v3")) for arm in ORDER]


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    gen = {}
    for p in ("results/gen_test_arms_4b-instruct.jsonl", "results/gen_test_arms_8b.jsonl"):
        for r in read_jsonl(p):
            gen[(p, r["id"], r["condition"])] = r
    def premise_records(path):
        out = []
        for f in read_jsonl(path):
            if f["minicheck_cited_min"] is None:
                continue
            r = gen[(f["file"], f["id"], f["condition"])]
            cks, _ = pack_context(qs[f["id"]], r["condition"].split(":")[0])
            cited = set(CITE.findall(r["response"]))
            words = sum(len(c["text"].split()) for c in cks if short_id(c["chunk_id"]) in cited)
            ctx, pk = r["condition"].split(":")
            out.append({"model": MODEL[f["model"]], "arm": ARM[ctx], "prompt": PROMPT[pk], "id": f["id"],
                        "words": words, "mc": f["minicheck_cited_min"]})
        return out
    recs = premise_records("results/faithfulness_test_arms.jsonl")

    rows = []
    for m in ("4b-instruct", "8b"):
        for p in ("v2", "v3"):
            sub = [x for x in recs if x["model"] == m and x["prompt"] == p]
            rho, pv = spearmanr([x["words"] for x in sub], [x["mc"] for x in sub])
            for arm in ORDER:
                w = [x["words"] for x in sub if x["arm"] == arm]
                rows.append({"model": m, "prompt": p, "arm": arm, "n": len(w),
                             "words_mean": round(st.mean(w), 1), "words_median": st.median(w),
                             "spearman_model_prompt": round(rho, 3), "spearman_p": round(pv, 4)})
    write("results/faith_premise_length.csv", rows)
    print("model        pr  arm     n  mean  median | Spearman (model x prompt)")
    for r in rows:
        print(f"{r['model']:12} {r['prompt']:3} {r['arm']:6} {r['n']:>3} {r['words_mean']:>6} "
              f"{r['words_median']:>6} | rho={r['spearman_model_prompt']} p={r['spearman_p']}")

    by = {(x["model"], x["arm"], x["prompt"], x["id"]): x["mc"] for x in recs}
    prow = []
    for m in ("4b-instruct", "8b"):
        for (a1, p1), (a2, p2) in PAIRS:
            ids = sorted({x["id"] for x in recs if (m, a1, p1, x["id"]) in by and (m, a2, p2, x["id"]) in by})
            d = [by[(m, a2, p2, i)] - by[(m, a1, p1, i)] for i in ids]
            nz = [x for x in d if x != 0]
            p = wilcoxon(nz).pvalue if len(nz) >= 1 else 1.0
            prow.append({"model": m, "A": f"{a1}/{p1}", "B": f"{a2}/{p2}", "n": len(ids),
                         "mean_diff_B_minus_A": round(st.mean(d), 3) if d else None,
                         "wilcoxon_p": round(p, 4), "label": "exploratory"})
    write("results/faith_paired.csv", prow)
    print("\nPaired MiniCheck cited min (exploratory)")
    for r in prow:
        print(f"{r['model']:12} {r['A']:10} vs {r['B']:10} n={r['n']:>2} diff={r['mean_diff_B_minus_A']:>7} "
              f"p={r['wilcoxon_p']}")

    un = premise_records("results/faithfulness_unanswerable.jsonl")
    urows = []
    for m in ("4b-instruct", "8b", "pooled"):
        sub = [x for x in un if m == "pooled" or x["model"] == m]
        rho, pv = spearmanr([x["words"] for x in sub], [x["mc"] for x in sub])
        for arm in ORDER + ["all"]:
            w = [x["words"] for x in sub if arm == "all" or x["arm"] == arm]
            urows.append({"model": m, "arm": arm, "n": len(w), "words_median": st.median(w) if w else None,
                          "words_mean": round(st.mean(w), 1) if w else None,
                          "spearman": round(rho, 3), "spearman_p": round(pv, 4), "n_spearman": len(sub)})
    write("results/faith_premise_length_unanswerable.csv", urows)
    print("\nUnanswerable rows: cited-premise words")
    for r in urows:
        print(f"{r['model']:12} {r['arm']:6} n={r['n']:>3} median={r['words_median']} mean={r['words_mean']} | "
              f"rho={r['spearman']} p={r['spearman_p']} (n={r['n_spearman']})")


if __name__ == "__main__":
    main()
