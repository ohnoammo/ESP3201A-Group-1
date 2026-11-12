"""Arm H0 descriptive retrieval counts, H0 vs F0 (tuning_rule_hybrid.md; counts only, no tests).

    python h0_retrieval.py      # -> results/retrieval_H0_vs_F0.csv (per question)
                                #    results/retrieval_H0_vs_F0_summary.json

50 answerables: gold PR in the first 5 distinct ranked PRs (saved top-100 candidates); answer span in
context (span_in_context.any of the generated rows, which must agree across model x prompt).
67 questions: per model x prompt, how many have the same context_chunk_ids in H0 and F0. On those rows
a changed answer would be non-determinism and a changed label would be label drift.
"""
import csv
import json

from common import git_commit, read_jsonl

CANDS = {"F0": "results/candidates_fixed_s512_o77_k100.jsonl", "H0": "results/candidates_fixed_s512_o77_k100_hybrid.jsonl"}
GEN = {"F0": {"4b-instruct": "results/gen_test_arms_4b-instruct.jsonl", "8b": "results/gen_test_arms_8b.jsonl"},
       "H0": {"4b-instruct": "results/gen_test_arm_H0_4b-instruct.jsonl", "8b": "results/gen_test_arm_H0_8b.jsonl"}}
COND = {"F0": "pack-fixed-0-score", "H0": "packh-fixed-0-score"}
PROMPT = {"c": "v2", "c3": "v3"}
TOP = 5


def pr_rank(row, pr):
    """1-based position of pr among the distinct ranked PRs; None if not in the top-100 chunks."""
    seen = list(dict.fromkeys(row["retrieved_prs"]))
    return seen.index(pr) + 1 if pr in seen else None


def gen_rows(arm):
    """{(model, prompt, id): row}, restricted to the arm's context condition."""
    out = {}
    for model, path in GEN[arm].items():
        for r in read_jsonl(path):
            ctx, pk = r["condition"].split(":")
            if ctx == COND[arm]:
                out[(model, PROMPT[pk], r["id"])] = r
    return out


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    ans = sorted(i for i, q in qs.items() if q["type"] == "answerable" and q["split"] == "test")
    assert len(ans) == 50
    cand = {arm: {r["id"]: r for r in read_jsonl(p) if "id" in r} for arm, p in CANDS.items()}
    gen = {arm: gen_rows(arm) for arm in GEN}
    h0_keys = set(gen["H0"])
    assert len(h0_keys) == 268 and h0_keys <= set(gen["F0"])
    cells = sorted({k[:2] for k in h0_keys})
    commit = git_commit()

    rows = []
    for i in ans:
        pr = int(qs[i]["pr_number"])
        row = {"id": i, "pr_number": pr}
        for arm in ("F0", "H0"):
            rank = pr_rank(cand[arm][i], pr)
            span = {gen[arm][(*c, i)]["span_in_context"]["any"] for c in cells}
            assert len(span) == 1, (arm, i, span)
            row[f"{arm}_gold_pr_rank"] = rank
            row[f"{arm}_gold_pr_top5"] = rank is not None and rank <= TOP
            row[f"{arm}_span_in_ctx"] = span.pop()
        row["git_commit"] = commit
        rows.append(row)
    with open("results/retrieval_H0_vs_F0.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    same = {}
    for model, prompt in cells:
        ids = [k[2] for k in h0_keys if k[:2] == (model, prompt)]
        assert len(ids) == 67, (model, prompt, len(ids))
        same[f"{model}/{prompt}"] = sorted(i for i in ids if gen["H0"][(model, prompt, i)]["context_chunk_ids"]
                                           == gen["F0"][(model, prompt, i)]["context_chunk_ids"])
    summary = {"n_answerable": len(rows),
               "gold_pr_top5": {a: sum(r[f"{a}_gold_pr_top5"] for r in rows) for a in ("F0", "H0")},
               "span_in_ctx": {a: sum(r[f"{a}_span_in_ctx"] for r in rows) for a in ("F0", "H0")},
               "top5_lost": [r["id"] for r in rows if r["F0_gold_pr_top5"] and not r["H0_gold_pr_top5"]],
               "top5_gained": [r["id"] for r in rows if r["H0_gold_pr_top5"] and not r["F0_gold_pr_top5"]],
               "span_lost": [r["id"] for r in rows if r["F0_span_in_ctx"] and not r["H0_span_in_ctx"]],
               "span_gained": [r["id"] for r in rows if r["H0_span_in_ctx"] and not r["F0_span_in_ctx"]],
               "identical_contexts_of67": {k: len(v) for k, v in same.items()},
               "identical_context_ids": same, "git_commit": commit}
    with open("results/retrieval_H0_vs_F0_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
