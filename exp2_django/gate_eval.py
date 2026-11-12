"""Faithfulness gate (tuning_rule_gate.md): an answered row becomes an abstention if its cited-chunk
MiniCheck min-sentence score is < 0.5; rows with no valid citation (no cited premise) are gated;
hedged rows count as answered and are gated by the same rule.

    python gate_eval.py                     # -> results/gate_eval.csv, gate_auroc.csv,
                                            #    gate_unanswerable_rows.csv, gate_sweep.csv
    python gate_eval.py --exclude-clued     # P3: 15 unanswerables (no nr9172, nr13883) -> *_excl15.csv
    python gate_eval.py --labels judging/codex_labels.csv
                                            # (d) correctness instead of overlap-cited
                                            #    -> results/gate_*_correctness.csv (prepared, not run)

(a) per model x arm x prompt, ungated vs gated (threshold 0.5): answered (of 50 test answerables),
    overlap-cited (was "right-chunk-cited"; answered after gating and cited correctly), answered on
    the 17 unanswerable rows (5 no-reason test, 5 no-reason dev, 5 whole PR excluded, PR kept
    rk16129 and rk9789; 15 with --exclude-clued).
(b) discrimination: per model, AUROC of MiniCheck cited min and of HHEM cited min for separating
    answered unanswerable rows (positive; lower score = more likely unanswerable) from answered
    answerables (negative), with two negative classes: overlap-cited answerables (a conditional
    contrast) and all answered answerables (with --labels: labelled correct, and all answered).
    Overall, F0 only and structural arms (S0, S0-G, S-0.25), both prompts pooled. A row with no
    cited premise scores 0 (it is gated). 95% CI: bootstrap over PR families (all questions on one
    PR: q<pr>, rm<pr>, rk<pr> kept together, so redacted twins are never split across draws),
    families resampled with replacement from those with a row in either class, 1,000 reps, seed 42,
    percentile; draws missing a class are redrawn. Also lists every unanswerable row the gate
    converts to abstention or lets through.
(c) secondary only: thresholds 0.1-0.9 (step 0.1), same counts. Not used to choose a threshold.
Scores: results/faithfulness_test_arms.jsonl (answerables) and results/faithfulness_unanswerable.jsonl.
"""
import argparse
import csv
import random
from collections import defaultdict

import numpy as np
from scipy.stats import rankdata

from common import read_jsonl
from faithfulness import PR_KEPT
from score import auto
from stats_arms import ARM, FILES

THRESHOLD = 0.5
BOOT, SEED = 1000, 42
SUBSETS = {"all": ("F0", "S0", "S0-G", "S-0.25"), "F0": ("F0",), "structural": ("S0", "S0-G", "S-0.25")}
SWEEP = [round(0.1 * i, 1) for i in range(1, 10)]
PROMPT = {"c": "v2", "c3": "v3"}
ORDER = ["F0", "S0", "S0-G", "S-0.25"]
FAITH = ["results/faithfulness_test_arms.jsonl", "results/faithfulness_unanswerable.jsonl"]
CLUED = ("nr9172", "nr13883")


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def load(labels, exclude_clued=False):
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    faith = {(x["file"], x["id"], x["condition"]): x for p in FAITH for x in read_jsonl(p)}
    rows = []
    for model, path in FILES.items():
        for r in read_jsonl(path):
            q = qs[r["id"]]
            if r["type"] == "answerable" and q["split"] == "test":
                group = "answerable"
            elif (r["type"] in ("no_reason", "removed") or r["id"] in PR_KEPT) and \
                    not (exclude_clued and r["id"] in CLUED):
                group = "unanswerable"
            else:
                continue
            a = auto(r, q)
            answered = not a["abstained"] and not a["empty_answer"]
            key = (path, r["id"], r["condition"])
            if answered:
                assert key in faith, f"no faithfulness score for {key}"
            ctx, pk = r["condition"].split(":")
            lab = labels.get(key) if labels is not None else None
            rows.append({"model": model, "arm": ARM[ctx], "prompt": PROMPT[pk], "id": r["id"],
                         "family": q["pr_number"], "type": r["type"], "split": q["split"],
                         "group": group, "answered": answered, "hedged": a["hedged"],
                         "overlap_cited": a["overlap_cited"] and answered, "all_answered": answered,
                         "correct": lab == "correct", "correct_or_partial": lab in ("correct", "partial"),
                         "score": faith[key]["minicheck_cited_min"] if answered else None,
                         "hhem": faith[key]["hhem_cited_min"] if answered else None})
    return rows


def families(rows):
    """{pr: [ids]} for PRs with more than one question id among the rows."""
    d = defaultdict(set)
    for x in rows:
        d[x["family"]].add(x["id"])
    return {k: sorted(v) for k, v in sorted(d.items()) if len(v) > 1}


def auroc(pos, neg):
    """P(score of a positive < score of a negative), ties 1/2 (Mann-Whitney U on the negatives)."""
    r = rankdata(np.concatenate([pos, neg]))
    return (r[len(pos):].sum() - len(neg) * (len(neg) + 1) / 2) / (len(pos) * len(neg))


def auroc_ci(pos_rows, neg_rows, judge):
    fam = defaultdict(lambda: ([], []))
    for cls, rs in ((0, pos_rows), (1, neg_rows)):
        for x in rs:
            fam[x["family"]][cls].append(0.0 if x[judge] is None else x[judge])
    keys = sorted(fam)
    est = auroc(np.array([v for x in pos_rows for v in [0.0 if x[judge] is None else x[judge]]]),
                np.array([v for x in neg_rows for v in [0.0 if x[judge] is None else x[judge]]]))
    rng, reps = random.Random(SEED), []
    while len(reps) < BOOT:
        draw = rng.choices(keys, k=len(keys))
        pos = [v for k in draw for v in fam[k][0]]
        neg = [v for k in draw for v in fam[k][1]]
        if pos and neg:
            reps.append(auroc(np.array(pos), np.array(neg)))
    lo, hi = np.percentile(reps, [2.5, 97.5])
    return est, lo, hi, len({x["family"] for x in pos_rows}), len({x["family"] for x in neg_rows})


def passes(x, t):
    return x["answered"] and x["score"] is not None and x["score"] >= t


def strata(rows):
    for m in FILES:
        for p in ("v2", "v3"):
            for arm in ORDER:
                sub = [x for x in rows if x["model"] == m and x["prompt"] == p and x["arm"] == arm]
                yield m, arm, p, [x for x in sub if x["group"] == "answerable"], \
                    [x for x in sub if x["group"] == "unanswerable"]


def main(a):
    labels = None
    if a.labels:
        from stats_correctness import load_labels
        labels = load_labels(a.labels)
    rows = load(labels, a.exclude_clued)
    n_un = 15 if a.exclude_clued else 17
    outs = ("correct", "correct_or_partial") if labels is not None else ("overlap_cited",)
    sfx = ("_correctness" if labels is not None else "") + ("_excl15" if a.exclude_clued else "")

    # (a) + (c)
    def counts(m, arm, p, ans, un, t):
        row = {"model": m, "arm": arm, "prompt": p, "threshold": t,
               "answered_ungated": sum(x["answered"] for x in ans),
               "answered_gated": sum(passes(x, t) for x in ans)}
        for o in outs:
            row[f"{o}_ungated"] = sum(x[o] and x["answered"] for x in ans)
            row[f"{o}_gated"] = sum(x[o] and passes(x, t) for x in ans)
        row[f"unanswerable_answered_ungated_of{n_un}"] = sum(x["answered"] for x in un)
        row[f"unanswerable_answered_gated_of{n_un}"] = sum(passes(x, t) for x in un)
        return row

    table, sweep = [], []
    for m, arm, p, ans, un in strata(rows):
        assert len(ans) == 50 and len(un) == n_un, (m, arm, p, len(ans), len(un))
        table.append(counts(m, arm, p, ans, un, THRESHOLD))
        sweep += [counts(m, arm, p, ans, un, t) for t in SWEEP]
    write(f"results/gate_eval{sfx}.csv", table)
    write(f"results/gate_sweep{sfx}.csv", sweep)
    print(f"(a) threshold {THRESHOLD}: ungated -> gated")
    print(f"{'model':12} {'arm':6} {'pr':3} | answered/50 | " + " | ".join(outs) + f" | unanswerable answered/{n_un}")
    for r in table:
        print(f"{r['model']:12} {r['arm']:6} {r['prompt']:3} | {r['answered_ungated']:>2} -> {r['answered_gated']:>2} | "
              + " | ".join(f"{r[o + '_ungated']:>2} -> {r[o + '_gated']:>2}" for o in outs)
              + f" | {r[f'unanswerable_answered_ungated_of{n_un}']:>2} -> {r[f'unanswerable_answered_gated_of{n_un}']:>2}")

    # (b) discrimination
    print("\nShared-PR families (bootstrap unit):", families(rows))
    negs = ("correct", "all_answered") if labels is not None else ("overlap_cited", "all_answered")
    disc = []
    for m in FILES:
        for sub, arms in SUBSETS.items():
            pos = [x for x in rows if x["model"] == m and x["arm"] in arms and x["group"] == "unanswerable"
                   and x["answered"]]
            for neg_key in negs:
                neg = [x for x in rows if x["model"] == m and x["arm"] in arms and x["group"] == "answerable"
                       and x["answered"] and x[neg_key]]
                for judge, name in (("score", "minicheck"), ("hhem", "hhem")):
                    est, lo, hi, npf, nnf = auroc_ci(pos, neg, judge)
                    disc.append({"model": m, "arms": sub, "negatives": neg_key, "judge": name,
                                 "n_pos_rows": len(pos), "n_neg_rows": len(neg),
                                 "n_pos_families": npf, "n_neg_families": nnf,
                                 "auroc": round(est, 3), "ci_lo": round(lo, 3), "ci_hi": round(hi, 3)})
    write(f"results/gate_auroc{sfx}.csv", disc)
    print("\n(b) AUROC, unanswerable answered (pos) vs answerables (neg), 95% PR-family bootstrap CI")
    for r in disc:
        print(f"{r['model']:12} {r['arms']:10} {r['negatives']:13} {r['judge']:9} "
              f"pos={r['n_pos_rows']:>3} ({r['n_pos_families']:>2} fam) neg={r['n_neg_rows']:>3} "
              f"({r['n_neg_families']:>2} fam) AUROC={r['auroc']:.3f} [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]")
    if labels is None:
        un = [x for x in rows if x["group"] == "unanswerable" and x["answered"]]
        lst = [{"model": x["model"], "arm": x["arm"], "prompt": x["prompt"], "id": x["id"],
                "set": x["type"] + ("/" + x["split"] if x["type"] == "no_reason" else ""),
                "hedged": x["hedged"],
                "score": None if x["score"] is None else round(x["score"], 3),
                "gate": "let through" if passes(x, THRESHOLD) else "abstain"} for x in un]
        write(f"results/gate_unanswerable_rows{sfx}.csv", lst)
        print(f"\nUnanswerable rows: {sum(x['gate'] == 'abstain' for x in lst)} -> abstain, "
              f"{sum(x['gate'] == 'let through' for x in lst)} let through")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", help="Codex labels (part d); omit for overlap-cited")
    ap.add_argument("--exclude-clued", action="store_true", help="drop nr9172 and nr13883 (P3)")
    main(ap.parse_args())
