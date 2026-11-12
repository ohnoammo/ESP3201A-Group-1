"""Run 1, Django part: dense (F0) vs hybrid (H0) retrieval on the 50 answerable test "why" questions
(gitlab_runner_copy/tuning_rule_hybrid_13nov.md; POST HOC, the counts were already seen on 5 Nov).

    python h0_retrieval_tests.py      # -> results/retrieval_why_django.csv (per question)

No new retrieval. Reads the saved F0 and H0 top-100 candidates and the existing generations (for span in the
packed context), reusing h0_retrieval.py's functions without editing it. Per question and arm:
  hit5   gold PR among the first 5 distinct ranked PRs
  rr5    1 / rank of the gold PR if rank <= 5, else 0
  span   span_in_context.any of the generated rows (identical across model x prompt; asserted)
The tests (McNemar, sign-flip permutation, bootstrap CI, Holm over 6) are run with the GitLab part by
gitlab_runner_copy/gitlab_h0.py retrieval-tests.
"""
import csv

import h0_retrieval as H
from common import git_commit, read_jsonl

OUT = "results/retrieval_why_django.csv"


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    ans = sorted(i for i, q in qs.items() if q["type"] == "answerable" and q["split"] == "test")
    assert len(ans) == 50
    cand = {arm: {r["id"]: r for r in read_jsonl(p) if "id" in r} for arm, p in H.CANDS.items()}
    gen = {arm: H.gen_rows(arm) for arm in H.GEN}
    cells = sorted({k[:2] for k in gen["H0"]})
    commit = git_commit()
    rows = []
    for i in ans:
        pr = int(qs[i]["pr_number"])
        row = {"repo": "django", "id": i, "pr_number": pr}
        for arm, name in (("F0", "dense"), ("H0", "hybrid")):
            rank = H.pr_rank(cand[arm][i], pr)
            span = {gen[arm][(*c, i)]["span_in_context"]["any"] for c in cells}
            assert len(span) == 1, (arm, i, span)
            row[f"{name}_gold_rank"] = rank
            row[f"{name}_hit5"] = int(rank is not None and rank <= H.TOP)
            row[f"{name}_rr5"] = round(1 / rank, 6) if rank is not None and rank <= H.TOP else 0.0
            row[f"{name}_span"] = int(span.pop())
        row["git_commit"] = commit
        rows.append(row)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for name in ("dense", "hybrid"):
        print(name, {k: round(sum(r[f"{name}_{k}"] for r in rows), 3) for k in ("hit5", "rr5", "span")})
    print(f"{len(rows)} questions -> {OUT}")


if __name__ == "__main__":
    main()
