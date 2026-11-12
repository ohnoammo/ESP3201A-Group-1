"""Removed-case contexts under both variants (retrieval only).

    python eval_removed.py     # -> results/removed_variants.json

rm<pr>  whole PR (+ same-ticket PRs) excluded           (main index)
rk<pr>  answer text removed, PR kept; same-ticket PRs excluded (exp1_copy_redacted index)
Per case x arm: is any quote verbatim in the context, shared 6-word sequences with the quotes,
is the case's own PR in context (rk only), distinct PRs, tokens.
"""
import json
import re

from common import read_jsonl, git_commit
from pack_exp1 import build_context_exp1, build_context_redacted

ARMS = [("fixed_s512_o77", 0.0), ("struct_c256", 0.0), ("struct_c256", 0.25)]


def ngrams(t, n=6):
    w = re.findall(r"[a-z0-9]+", t.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def main():
    rm = [q for q in read_jsonl("questions.jsonl") if q["type"] == "removed"]
    rk = read_jsonl("questions_removed_kept.jsonl")
    out = {"git_commit": git_commit(), "rows": []}
    for q in rm + rk:
        qg = set().union(*(ngrams(x) for x in q["quotes"]))
        for ch, a in ARMS:
            f = build_context_redacted if q["type"] == "removed_kept" else build_context_exp1
            ctx = f(q["id"], a, 2560, q["exclude_prs"], ch)
            text = "\n".join(c["text"] for c in ctx["chunks"])
            out["rows"].append({
                "id": q["id"], "variant": q["type"], "chunking": ch, "alpha": a,
                "quote_verbatim": any(x in text for x in q["quotes"]),
                "quote_6grams": len(qg & ngrams(text)),
                "own_pr_in_context": any(c["pr_number"] == q["pr_number"] for c in ctx["chunks"]),
                "own_pr_chunks": sum(c["pr_number"] == q["pr_number"] for c in ctx["chunks"]),
                "n_prs": ctx["n_prs"], "tokens": ctx["tokens"], "n_linked": ctx["n_linked"]})
    with open("results/removed_variants.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    for r in out["rows"]:
        print(f"{r['id']:<9}{r['chunking']:<16}a={r['alpha']:<5} verbatim={r['quote_verbatim']!s:<6}"
              f" 6grams={r['quote_6grams']:<3} ownPR={r['own_pr_in_context']!s:<6}({r['own_pr_chunks']}) prs={r['n_prs']}")


if __name__ == "__main__":
    main()
