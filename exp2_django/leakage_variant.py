"""Removed-case leakage variant: "answer removed, PR kept" (group rule, 22 Oct).

    python leakage_variant.py      # -> redacted PR JSONs + questions_removed_kept.jsonl + report

For each "removed" test case, the comment(s)/span(s) holding the answer (and repeats of it in the
same PR's description, commit messages or other comments) are removed from that PR's raw JSON
BEFORE pr_document/chunking, following relations.py ("Excluded comments ... must be removed from
the PR documents before chunking; then they are not chunks and can never be linked"). Diffs are
never edited. The rest of the PR stays in the index.

Output (separate index variant; main pool untouched):
  C:/Users/kwekt/ESP3201A_local/exp1_copy_redacted/prs/django_django/<pr>.json  (5 redacted PRs)
  questions_removed_kept.jsonl   ids "rk<pr>": same question, exclude_prs = same-ticket PRs only
  results/leakage_variant_report.json   per case: what was removed, residual checks, flags
"""
import copy
import json
import os
import re

from common import read_jsonl, write_jsonl, load_pr, git_commit
from pr_document import build_document

OUT = "C:/Users/kwekt/ESP3201A_local/exp1_copy_redacted/prs/django_django"

# ops: ("drop_issue", id) | ("drop_review", id) | ("cut_body", text) | ("cut_commit", text)
#      | ("cut_issue", id, text)
REDACT = {
    13671: dict(ops=[
        ("cut_body", "Many of the cache operations make use of `get()` with the implicit `default=None` and assume that the returned `None` value indicates the value is not stored. This may not be true as `None` can be explicitly set into the cache. "),
        ("cut_commit", "Many of the cache operations make use of the default argument to the\n.get() operation to determine whether the key was found in the cache.\nThe default value of the default argument is None, so this results in\nthese operations assuming that None is not stored in the cache when it\nactually is. Adding a sentinel object solves this issue.\n\n")],
        flag="docs/topics/cache.txt diff still shows the removed line \"won't be able to distinguish between your stored None value and a cache miss\" (diffs are not edited)"),
    16129: dict(ops=[
        ("drop_issue", 1260553787),
        ("cut_issue", 1260587266, "> It needs to be done before setup_test_environment(), unconditionally. \r\n\r\n")],
        flag=""),
    9789: dict(ops=[("drop_review", 176149339)], flag=""),
    11459: dict(ops=[
        ("cut_body", "For `filesizeformat`, the `filesize` value is expected to be an int -- it fills `%d` string formatting placeholders. It was likely coerced to a float to ensure floating point division on Python 2. Python 3 always does floating point division, so coerce to an int instead of a float to fix the warning.\r\n\r\n"),
        ("cut_commit", "For filesizeformat, the filesize value is expected to be an int -- it\nfills %d string formatting placeholders. It was likely coerced to a\nfloat to ensure floating point division on Python 2. Python 3 always\ndoes floating point division, so coerce to an int instead of a float to\nfix the warning.\n\n")],
        flag=""),
    12342: dict(ops=[
        ("drop_issue", 576236632),
        ("cut_body", " If a third database is added,\r\n   accessing it is prevented by the test environment, resulting in a\r\n   failing testcase.")],
        flag="weaker hints remain: description 'makes it easier to add an additional database in the future'; felixxm 'remove assumption that connections contains only default and other'"),
}


def apply(pr, ops):
    pr = copy.deepcopy(pr)
    done = []
    for op in ops:
        kind = op[0]
        if kind == "drop_issue":
            n0 = len(pr["issue_comments"])
            pr["issue_comments"] = [c for c in pr["issue_comments"] if c["id"] != op[1]]
            ok = len(pr["issue_comments"]) == n0 - 1
        elif kind == "drop_review":
            n0 = len(pr["review_comments"])
            pr["review_comments"] = [c for c in pr["review_comments"] if c["id"] != op[1]]
            ok = len(pr["review_comments"]) == n0 - 1
        elif kind == "cut_body":
            ok = pr["body"].count(op[1]) == 1
            pr["body"] = pr["body"].replace(op[1], "")
        elif kind == "cut_commit":
            hits = [c for c in pr["commits"] if op[1] in c["message"]]
            ok = len(hits) == 1
            for c in hits:
                c["message"] = c["message"].replace(op[1], "")
        elif kind == "cut_issue":
            hits = [c for c in pr["issue_comments"] if c["id"] == op[1] and op[2] in c["body"]]
            ok = len(hits) == 1
            for c in hits:
                c["body"] = c["body"].replace(op[2], "")
        else:
            raise ValueError(kind)
        if not ok:
            raise RuntimeError(f"redaction op did not apply exactly once: {op}")
        done.append(op[0] if kind.startswith("drop") else f"{kind} ({len(op[-1])} chars)")
    pr["redacted_for_exp2"] = [list(map(str, op[:2])) for op in ops]
    return pr, done


def words(t):
    return re.findall(r"[a-z0-9]+", t.lower())


def ngrams(t, n=6):
    w = words(t)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def main():
    os.makedirs(OUT, exist_ok=True)
    qs = [q for q in read_jsonl("questions.jsonl") if q["type"] == "removed"]
    report, kept = {"git_commit": git_commit(), "cases": {}}, []
    for q in qs:
        n = q["pr_number"]
        spec = REDACT[n]
        red, done = apply(load_pr(n), spec["ops"])
        with open(os.path.join(OUT, f"{n}.json"), "w", encoding="utf-8") as f:
            json.dump(red, f)
        d_old, d_new = build_document(load_pr(n)), build_document(red)
        qg = set().union(*(ngrams(x) for x in q["quotes"]))
        report["cases"][q["id"]] = {
            "pr": n, "ops": done,
            "doc_chars_before": len(d_old["text"]), "doc_chars_after": len(d_new["text"]),
            "quote_verbatim_left": any(x in d_new["text"] for x in q["quotes"]),
            "quote_6grams_left": len(qg & ngrams(d_new["text"])),
            "quote_6grams_before": len(qg & ngrams(d_old["text"])),
            "flag": spec["flag"]}
        kept.append(q | {"id": f"rk{n}", "type": "removed_kept",
                         "exclude_prs": [p for p in q["exclude_prs"] if p != n],
                         "variant": "answer removed, PR kept (exp1_copy_redacted)"})
    write_jsonl("questions_removed_kept.jsonl", kept)
    with open("results/leakage_variant_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
