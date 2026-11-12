"""Arm H0 vs F0: gate at 0.5 as counts, no tests (tuning_rule_hybrid.md, tuning_rule_gate.md).

    python gate_h0.py      # -> results/gate_H0.csv

An answered row is kept if MiniCheck cited min >= 0.5; no cited premise = gated. HHEM cited min >= 0.5 is
shown alongside (descriptive, no rule change), as for W-F. F0 rows reuse the frozen faithfulness files and
must reproduce results/gate_eval.csv at 0.5.
"""
import csv

from common import git_commit, read_jsonl
from extend_judging import FILES_H0
from score import auto
from score_arms import PR_KEPT
from stats_arms import FILES
from stats_correctness import load_labels

THRESHOLD = 0.5
PROMPT = {"c": "v2", "c3": "v3"}
ARMS = {"F0": ("pack-fixed-0-score", FILES, ("results/faithfulness_test_arms.jsonl", "results/faithfulness_unanswerable.jsonl")),
        "H0": ("packh-fixed-0-score", dict(zip(FILES, FILES_H0)),
               ("results/faithfulness_H0.jsonl", "results/faithfulness_H0_unanswerable.jsonl"))}


def kept(score):
    return score is not None and score >= THRESHOLD


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    labels = load_labels("judging/codex_labels.csv")
    commit = git_commit()
    frozen = {(r["model"], r["prompt"]): r for r in csv.DictReader(open("results/gate_eval.csv", encoding="utf-8"))
              if r["arm"] == "F0"}
    rows = []
    for arm, (cond, files, faith_files) in ARMS.items():
        faith = {(x["file"], x["id"], x["condition"]): x for p in faith_files for x in read_jsonl(p)}
        for model, path in files.items():
            recs = read_jsonl(path)
            for pk, prompt in PROMPT.items():
                condition = f"{cond}:{pk}"
                row = {"model": model, "arm": arm, "prompt": prompt}
                answerable, unanswerable = [], []
                for r in recs:
                    if r["condition"] != condition:
                        continue
                    a = auto(r, qs[r["id"]])
                    if a["abstained"] or a["empty_answer"]:
                        continue
                    k = (path, r["id"], condition)
                    if r["type"] == "answerable" and r["split"] == "test":
                        answerable.append((faith[k], a, labels[k]))
                    elif r["type"] in ("no_reason", "removed") or r["id"] in PR_KEPT:
                        unanswerable.append(faith[k])
                row["answerable_answered"] = len(answerable)
                row["unanswerable_answered"] = len(unanswerable)
                for j in ("minicheck", "hhem"):
                    got = [(a, lab) for f, a, lab in answerable if kept(f[f"{j}_cited_min"])]
                    row[f"answerable_kept_{j}"] = len(got)
                    row[f"correct_kept_{j}"] = sum(lab == "correct" for _, lab in got)
                    row[f"wrong_kept_{j}"] = sum(lab == "wrong" for _, lab in got)
                    row[f"overlap_cited_kept_{j}"] = sum(bool(a["overlap_cited"]) for a, _ in got)
                    row[f"unanswerable_kept_{j}"] = sum(kept(f[f"{j}_cited_min"]) for f in unanswerable)
                row["correct_ungated"] = sum(lab == "correct" for _, _, lab in answerable)
                row["wrong_ungated"] = sum(lab == "wrong" for _, _, lab in answerable)
                row["git_commit"] = commit
                if arm == "F0":
                    g = frozen[(model, prompt)]
                    assert (str(row["answerable_answered"]), str(row["answerable_kept_minicheck"]),
                            str(row["overlap_cited_kept_minicheck"]), str(row["unanswerable_answered"]),
                            str(row["unanswerable_kept_minicheck"])) == (
                        g["answered_ungated"], g["answered_gated"], g["overlap_cited_gated"],
                        g["unanswerable_answered_ungated_of17"], g["unanswerable_answered_gated_of17"]), (model, prompt)
                rows.append(row)
    with open("results/gate_H0.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print({k: v for k, v in r.items() if k != "git_commit"})


if __name__ == "__main__":
    main()
