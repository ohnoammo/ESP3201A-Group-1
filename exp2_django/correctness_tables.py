"""Correctness per model x arm x prompt on the 50 answerable test questions (queue b).

    python correctness_tables.py [--labels judging/codex_labels.csv]
        -> results/correctness_test_arms.csv

Labels joined to rows through stats_correctness.load_labels (also prints the duplicate-answer
consistency check). Rows not answered (abstained or empty) have no label and count as not correct.
strict = correct / 50, lenient = (correct + partial) / 50; also correct among answered and among
overlap-cited answers.
"""
import argparse
import csv
import hashlib

from common import git_commit, read_jsonl
from score import auto
from stats_arms import ARM, FILES
from stats_correctness import load_labels

PROMPT = {"c": "v2", "c3": "v3"}


def main(a):
    labels = load_labels(a.labels)
    with open(a.labels, "rb") as f:
        lab_sha = hashlib.sha256(f.read()).hexdigest()[:12]
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    commit = git_commit()
    rows = []
    for model, path in FILES.items():
        by = {}
        for r in read_jsonl(path):
            q = qs[r["id"]]
            if r["type"] != "answerable" or q["split"] != "test":
                continue
            ctx, pk = r["condition"].split(":")
            by.setdefault((ARM[ctx], PROMPT[pk]), []).append((r, auto(r, q)))
        for (arm, prompt), rs in sorted(by.items()):
            assert len(rs) == 50
            ans = [(r, x) for r, x in rs if not x["abstained"] and not x["empty_answer"]]
            lab = [labels[(path, r["id"], r["condition"])] for r, _ in ans]
            assert None not in lab
            oc = [labels[(path, r["id"], r["condition"])] for r, x in ans if x["overlap_cited"]]
            n_c, n_p = lab.count("correct"), lab.count("partial")
            rows.append({"model": model, "arm": arm, "prompt": prompt, "n": 50, "answered": len(ans),
                         "correct": n_c, "partial": n_p, "wrong": lab.count("wrong"),
                         "strict": round(n_c / 50, 2), "lenient": round((n_c + n_p) / 50, 2),
                         "correct_of_answered": round(n_c / len(ans), 2) if ans else None,
                         "overlap_cited": len(oc), "correct_of_overlap_cited": oc.count("correct"),
                         "labels_sha256_12": lab_sha, "git_commit": commit})
    with open("results/correctness_test_arms.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{'model':12} {'arm':7} {'pr':3} {'ans':>4} {'C':>3} {'P':>3} {'W':>3} {'strict':>6} {'lenient':>7}")
    for r in rows:
        print(f"{r['model']:12} {r['arm']:7} {r['prompt']:3} {r['answered']:>4} {r['correct']:>3} "
              f"{r['partial']:>3} {r['wrong']:>3} {r['strict']:>6} {r['lenient']:>7}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="judging/codex_labels.csv")
    main(ap.parse_args())
