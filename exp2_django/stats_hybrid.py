"""Arm H0 vs F0: the "hybrid 16" family and descriptive correctness counts (tuning_rule_hybrid.md).

    python stats_hybrid.py      # -> results/stats_hybrid.csv (16 tests, Holm)
                                #    results/stats_hybrid_lenient.csv (sensitivity, unadjusted)
                                #    results/correctness_H0.csv (counts per model x prompt, H0 and F0)

H0 vs F0, same model and prompt, paired by question; exact two-sided McNemar (stats_arms.mcnemar).
b = only H0, c = only F0. Outcomes: answered /50, overlap-cited /50, unanswerable answered /17, strict
correct /50 (Codex label correct; unanswered = not correct). Unanswerables: the 17 rows of the rule, so
rk11459 and rk12342 are out for F0 too. Answered-wrong /50 is descriptive and adds no test.
"""
import csv

from common import git_commit, read_jsonl
from extend_judging import FILES_H0
from score import auto
from score_arms import PR_KEPT
from stats_arms import FILES, holm, mcnemar
from stats_correctness import load_labels

LABELS_FILE = "judging/codex_labels.csv"
H0 = dict(zip(FILES, FILES_H0))
COND = {"F0": "pack-fixed-0-score", "H0": "packh-fixed-0-score"}
PK = {"v2": "c", "v3": "c3"}
OUTCOMES = {"answered /50": ("ans", "answered"), "overlap-cited /50": ("ans", "overlap"),
            "unanswerable answered /17": ("un", "answered"), "strict correct /50": ("ans", "strict")}


def is_unanswerable(r):
    return r["type"] in ("no_reason", "removed") or r["id"] in PR_KEPT


def load(path, cond, qs, labels):
    """{(prompt, id): outcomes} for one model file and context condition."""
    out = {}
    for prompt, pk in PK.items():
        condition = f"{cond}:{pk}"
        for r in read_jsonl(path):
            if r["condition"] != condition:
                continue
            q = qs[r["id"]]
            a = auto(r, q)
            answered = not a["abstained"] and not a["empty_answer"]
            ansq = r["type"] == "answerable" and q["split"] == "test"
            lab = labels.get((path, r["id"], condition)) if ansq else None
            if ansq and answered:
                assert lab is not None, (path, r["id"], condition)
            out[(prompt, r["id"])] = {"ansq": ansq, "unq": is_unanswerable(r), "answered": answered,
                                      "overlap": bool(a["overlap_cited"]), "label": lab,
                                      "strict": lab == "correct", "lenient": lab in ("correct", "partial"),
                                      "wrong": lab == "wrong"}
    return out


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    labels = load_labels(LABELS_FILE)
    commit = git_commit()
    fam, sens, counts = [], [], []
    for model, f0_path in FILES.items():
        F = load(f0_path, COND["F0"], qs, labels)
        H = load(H0[model], COND["H0"], qs, labels)
        for prompt in PK:
            ids = sorted(i for p, i in H if p == prompt)
            ans = [i for i in ids if H[(prompt, i)]["ansq"]]
            un = [i for i in ids if H[(prompt, i)]["unq"]]
            assert len(ids) == 67 and len(ans) == 50 and len(un) == 17, (model, prompt, len(ids), len(ans), len(un))
            for name, (grp, field) in OUTCOMES.items():
                use = ans if grp == "ans" else un
                x = [H[(prompt, i)][field] for i in use]
                y = [F[(prompt, i)][field] for i in use]
                p, b, c = mcnemar(x, y)
                fam.append({"model": model, "prompt": prompt, "outcome": name, "H0": sum(x), "F0": sum(y),
                            "b_only_H0": b, "c_only_F0": c, "p": p, "min_p": min(1.0, 2.0 ** (1 - b - c))})
            x = [H[(prompt, i)]["lenient"] for i in ans]
            y = [F[(prompt, i)]["lenient"] for i in ans]
            p, b, c = mcnemar(x, y)
            sens.append({"model": model, "prompt": prompt, "outcome": "lenient correct /50", "H0": sum(x), "F0": sum(y),
                         "b_only_H0": b, "c_only_F0": c, "p_unadjusted": round(p, 4),
                         "label": "sensitivity, not in the family", "git_commit": commit})
            for arm, R in (("H0", H), ("F0", F)):
                rows = [R[(prompt, i)] for i in ans]
                counts.append({"model": model, "arm": arm, "prompt": prompt,
                               "answered": sum(r["answered"] for r in rows),
                               "correct": sum(r["label"] == "correct" for r in rows),
                               "partial": sum(r["label"] == "partial" for r in rows),
                               "wrong": sum(r["wrong"] for r in rows),
                               "strict_of50": sum(r["strict"] for r in rows),
                               "lenient_of50": sum(r["lenient"] for r in rows),
                               "answered_wrong_of50": sum(r["wrong"] for r in rows),
                               "unanswerable_answered_of17": sum(R[(prompt, i)]["answered"] for i in un),
                               "git_commit": commit})
    assert len(fam) == 16
    for r, h in zip(fam, holm([r["p"] for r in fam])):
        r["p_holm"] = h
    for r in fam:
        for k in ("p", "min_p", "p_holm"):
            r[k] = round(r[k], 4)
        r["family"] = "hybrid 16"
        r["git_commit"] = commit
    write("results/stats_hybrid.csv", fam)
    write("results/stats_hybrid_lenient.csv", sens)
    write("results/correctness_H0.csv", counts)
    print(f"{'model':12} {'pr':3} {'outcome':26} {'H0':>3} {'F0':>3} {'b':>3} {'c':>3} {'p':>7} {'min_p':>7} {'Holm':>7}")
    for r in fam:
        print(f"{r['model']:12} {r['prompt']:3} {r['outcome']:26} {r['H0']:>3} {r['F0']:>3} {r['b_only_H0']:>3} "
              f"{r['c_only_F0']:>3} {r['p']:>7.4f} {r['min_p']:>7.4f} {r['p_holm']:>7.4f}")
    print("--- lenient sensitivity")
    for r in sens:
        print({k: r[k] for k in ("model", "prompt", "H0", "F0", "b_only_H0", "c_only_F0", "p_unadjusted")})
    print("--- counts")
    for r in counts:
        print({k: v for k, v in r.items() if k != "git_commit"})


if __name__ == "__main__":
    main()
