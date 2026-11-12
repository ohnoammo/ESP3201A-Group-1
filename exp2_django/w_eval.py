"""Arm W-F correctness, pre-declared exploratory comparisons and gate (tuning_rule_wholepr.md).

    python w_eval.py      # -> results/w_correctness.csv, results/w_comparisons.csv,
                          #    results/w_subset.csv, results/w_gate.csv,
                          #    results/w_comparisons_lenient_sensitivity.csv

Correctness (Codex labels via stats_correctness.load_labels; unanswered = not correct): per model x
prompt, strict and lenient /50 and correct among answered.
Comparisons (exploratory; exact McNemar on the 50 answerable or 17 unanswerable questions; unadjusted
p; no Holm): W-F vs F0 (same ranking, packing only; primary exploratory) and W-F vs S-0.25 (ranking and
packing differ; descriptive context), per model x prompt, on strict correct /50, answered /50 and
unanswerable answered /17. b = only W-F, c = only the comparison arm.
Subset (counts only): answerable questions with the answer span in context in both arms; strict
correct and answered in each arm on that subset.
Sensitivity (added 1 Nov after the Codex drift check, not pre-declared): lenient correct /50 W-F vs F0
(exact McNemar, unadjusted) -> results/w_comparisons_lenient_sensitivity.csv, and lenient counts in the
subset (W_lenient, other_lenient).
Gate (tuning_rule_gate.md, exploratory): an answered row is kept if MiniCheck cited min >= 0.5 (no
cited premise = gated); HHEM cited min >= 0.5 shown for comparison (descriptive, no rule change).
"""
import csv

from common import git_commit, read_jsonl
from score import auto
from score_w import FILES_W, auto_w, unanswerable
from stats_arms import ARM, FILES, mcnemar
from stats_correctness import load_labels

PROMPT = {"c": "v2", "c3": "v3"}
COMPARE = [("F0", "same ranking, packing only (primary exploratory)"),
           ("S-0.25", "ranking and packing differ (descriptive context)")]
THRESHOLD = 0.5


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def rows_of(path, arm_of, scorer, labels, qs):
    out = {}
    for r in read_jsonl(path):
        q = qs[r["id"]]
        ctx, pk = r["condition"].split(":")
        arm = arm_of(ctx)
        if arm is None:
            continue
        a = scorer(r, q)
        answered = not a["abstained"] and not a["empty_answer"]
        lab = labels.get((path, r["id"], r["condition"]))
        ansq = r["type"] == "answerable" and q["split"] == "test"
        if ansq and answered:
            assert lab is not None, (path, r["id"], r["condition"])
        out[(arm, PROMPT[pk], r["id"])] = {
            "answerable": ansq, "unanswerable": unanswerable(r), "answered": answered, "label": lab,
            "strict": lab == "correct", "lenient": lab in ("correct", "partial"),
            "span": bool((r["span_in_context"] or {}).get("any")), "key": (path, r["id"], r["condition"])}
    return out


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    labels = load_labels("judging/codex_labels.csv")
    faith = {(x["file"], x["id"], x["condition"]): x for p in
             ("results/faithfulness_W.jsonl", "results/faithfulness_W_unanswerable.jsonl") for x in read_jsonl(p)}
    commit = git_commit()
    ids_a = sorted(q["id"] for q in qs.values() if q["type"] == "answerable" and q["split"] == "test")
    corr, comp, sub, gate, sens = [], [], [], [], []
    for model in FILES:
        R = rows_of(FILES_W[model], lambda c: "W-F" if c == "wpr-fixed" else None, auto_w, labels, qs)
        R |= rows_of(FILES[model], lambda c: ARM[c] if ARM.get(c) in ("F0", "S-0.25") else None, auto, labels, qs)
        ids_u = sorted(i for (arm, p, i), x in R.items() if arm == "W-F" and p == "v2" and x["unanswerable"])
        assert len(ids_a) == 50 and len(ids_u) == 17
        for p in ("v2", "v3"):
            W = [R[("W-F", p, i)] for i in ids_a]
            ans = [x for x in W if x["answered"]]
            nc = sum(x["strict"] for x in W)
            corr.append({"model": model, "arm": "W-F", "prompt": p, "answered": len(ans), "correct": nc,
                         "partial": sum(x["label"] == "partial" for x in W),
                         "wrong": sum(x["label"] == "wrong" for x in W), "strict_of50": nc,
                         "lenient_of50": sum(x["lenient"] for x in W),
                         "correct_of_answered": f"{nc}/{len(ans)}", "git_commit": commit})
            for arm, role in COMPARE:
                for outcome, ids, f in (("strict correct /50", ids_a, lambda x: x["strict"]),
                                        ("answered /50", ids_a, lambda x: x["answered"]),
                                        ("unanswerable answered /17", ids_u, lambda x: x["answered"])):
                    xw = [f(R[("W-F", p, i)]) for i in ids]
                    xc = [f(R[(arm, p, i)]) for i in ids]
                    pv, b, c = mcnemar(xw, xc)
                    comp.append({"model": model, "prompt": p, "comparison": f"W-F vs {arm}", "role": role,
                                 "outcome": outcome, "W_count": sum(xw), "other_count": sum(xc),
                                 "b_only_W": b, "c_only_other": c, "p_unadjusted": round(pv, 4),
                                 "label": "exploratory", "git_commit": commit})
                both = [i for i in ids_a if R[("W-F", p, i)]["span"] and R[(arm, p, i)]["span"]]
                sub.append({"model": model, "prompt": p, "comparison": f"W-F vs {arm}", "n_both_span": len(both),
                            "W_strict": sum(R[("W-F", p, i)]["strict"] for i in both),
                            "other_strict": sum(R[(arm, p, i)]["strict"] for i in both),
                            "W_answered": sum(R[("W-F", p, i)]["answered"] for i in both),
                            "other_answered": sum(R[(arm, p, i)]["answered"] for i in both),
                            "W_lenient": sum(R[("W-F", p, i)]["lenient"] for i in both),
                            "other_lenient": sum(R[(arm, p, i)]["lenient"] for i in both),
                            "counts_only": True, "git_commit": commit})
            xw = [R[("W-F", p, i)]["lenient"] for i in ids_a]
            xc = [R[("F0", p, i)]["lenient"] for i in ids_a]
            pv, b, c = mcnemar(xw, xc)
            sens.append({"model": model, "prompt": p, "comparison": "W-F vs F0", "outcome": "lenient correct /50",
                         "W_count": sum(xw), "other_count": sum(xc), "b_only_W": b, "c_only_other": c,
                         "p_unadjusted": round(pv, 4), "label": "sensitivity, added after the drift check; exploratory",
                         "git_commit": commit})
            row = {"model": model, "arm": "W-F", "prompt": p}
            for grp, ids in (("answerable", ids_a), ("unanswerable", ids_u)):
                A = [R[("W-F", p, i)] for i in ids if R[("W-F", p, i)]["answered"]]
                row[f"{grp}_answered"] = len(A)
                for jn in ("minicheck", "hhem"):
                    kept = [x for x in A if (s := faith[x["key"]][f"{jn}_cited_min"]) is not None and s >= THRESHOLD]
                    row[f"{grp}_kept_{jn}"] = len(kept)
                    if grp == "answerable":
                        row[f"answerable_correct_kept_{jn}"] = sum(x["strict"] for x in kept)
            row["answerable_correct_ungated"] = sum(R[("W-F", p, i)]["strict"] for i in ids_a)
            row["git_commit"] = commit
            gate.append(row)
    write("results/w_correctness.csv", corr)
    write("results/w_comparisons.csv", comp)
    write("results/w_subset.csv", sub)
    write("results/w_gate.csv", gate)
    write("results/w_comparisons_lenient_sensitivity.csv", sens)
    for name, rows in (("correctness", corr), ("comparisons", comp), ("subset", sub), ("gate", gate),
                       ("lenient sensitivity", sens)):
        print(f"--- {name}")
        for r in rows:
            print({k: v for k, v in r.items() if k not in ("git_commit", "role", "label", "counts_only")})


if __name__ == "__main__":
    main()
