"""Score arm W-F (tuning_rule_wholepr.md): abstention, hedged, gold-PR-cited, answer span in context.

    python score_w.py      # -> results/summary_test_arm_W.csv (+ printed table)

W citations are PR-level: [PR<n>] and [PR<n>-c<k>] both count as PR n. Abstention and hedged use
score.abstained_strict / score.hedged after W citation ids are removed; empty = nothing with a word
character left once citation ids and brackets are removed.
Gold-PR-cited: answered, >= 1 citation, every cited PR shown in the context, >= 1 cited PR = the
question's PR. Per model x prompt: answerable test (50) and the 17 unanswerables (5 no-reason test,
5 no-reason dev, 5 whole PR excluded, rk16129, rk9789; 15 without nr9172 and nr13883).
"""
import csv
import re
import sys

from common import read_jsonl
from score import abstained_strict, hedged

FILES_W = {"4b-instruct": "results/gen_test_arm_W_4b-instruct.jsonl", "8b": "results/gen_test_arm_W_8b.jsonl"}
WCITE = re.compile(r"PR(\d+)(?:-c\d+)?")
PROMPT = {"c": "v2", "c3": "v3"}
PR_KEPT = ("rk16129", "rk9789")
CLUED = ("nr9172", "nr13883")


def strip_cites(resp):
    return WCITE.sub("", resp)


def auto_w(rec, q):
    resp = rec["response"].strip()
    cites = [int(n) for n in WCITE.findall(resp)]
    shown = {int(s[2:]) for s in rec["context_short_ids"]}
    t = strip_cites(resp)
    empty = not re.search(r"\w", t.replace("[", "").replace("]", ""))
    ab = abstained_strict(t)
    ok = (not empty) and not ab and bool(cites) and all(c in shown for c in cites)
    return {"abstained": ab, "hedged": hedged(t), "empty_answer": empty, "n_cites": len(cites),
            "n_valid_cites": sum(c in shown for c in cites), "cited_prs": sorted(set(cites)),
            "gold_pr_cited": ok and int(q["pr_number"]) in cites}


def unanswerable(r):
    return r["type"] in ("no_reason", "removed") or r["id"] in PR_KEPT


def main(paths):
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    rows = []
    for model, path in paths.items():
        recs = read_jsonl(path)
        for pk in ("c", "c3"):
            rs = [r for r in recs if r["condition"] == f"wpr-fixed:{pk}"]
            assert len(rs) == 67, (path, pk, len(rs))
            A = [(r, auto_w(r, qs[r["id"]])) for r in rs]
            ans = [(r, a) for r, a in A if r["type"] == "answerable" and r["split"] == "test"]
            un = [(r, a) for r, a in A if unanswerable(r)]
            assert len(ans) == 50 and len(un) == 17
            answered = lambda a: not a["abstained"] and not a["empty_answer"]  # noqa: E731
            r0 = rs[0]
            rows.append({
                "model": model, "arm": "W-F", "prompt": PROMPT[pk],
                "answered": sum(answered(a) for _, a in ans),
                "gold_pr_cited": sum(a["gold_pr_cited"] for _, a in ans),
                "span_in_ctx": sum(r["span_in_context"]["any"] for r, _ in ans),
                "abstained_with_span": sum(a["abstained"] and r["span_in_context"]["any"] for r, a in ans),
                "hedged_answerable": sum(a["hedged"] for _, a in ans),
                "empty_answers": sum(a["empty_answer"] for _, a in A),
                "cross_pr_borrowing": sum(1 for r, a in ans if answered(a) and a["cited_prs"]
                                          and int(r["pr_number"]) not in a["cited_prs"]),
                "invalid_citation_rows": sum(1 for _, a in A if a["n_cites"] > a["n_valid_cites"]),
                "unanswerable_answered_of17": sum(answered(a) for _, a in un),
                "unanswerable_answered_of15": sum(answered(a) for r, a in un if r["id"] not in CLUED),
                "hedged_unanswerable": sum(a["hedged"] for _, a in un),
                "rank1_truncated_rows": sum(r["pack"]["rank1_truncated"] for r in rs),
                "mean_prs_in_ctx": round(sum(r["pack"]["n_prs"] for r in rs) / len(rs), 2),
                "max_prompt_eval_count": max(r["prompt_eval_count"] for r in rs),
                "possibly_truncated": sum(r["possibly_truncated"] for r in rs),
                "ollama": r0["ollama_version"], "git_commit": r0["git_commit"], "gpu": r0["machine"]["gpu"]})
    with open("results/summary_test_arm_W.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main(dict(zip(FILES_W, sys.argv[1:])) if len(sys.argv) > 1 else FILES_W)
