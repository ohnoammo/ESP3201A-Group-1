"""Relation factor, step C: retrieval-only evaluation of link arms (REPORTING ONLY, no tuning).

    python eval_links.py --split test        # -> results/links_eval_<split>.json / _per_query.csv

Arms: chunking in {fixed_s512_o77, struct_c256} x alpha in {0, 0.25, 0.5, 1}, labels off,
budget 2560 Exp 1 tokens. Per question and arm:
  any_cov / all_cov  any / all quote spans fully covered by the UNION of context chunks (gaps
                     that are only whitespace between adjacent chunks count as covered)
  gold_pr_in_ctx     some chunk of the answer PR is in the context
  headroom           gold PR in context but no span covered (what links could still fix)
  n_chunks, n_linked, tokens, qwen_tokens, n_prs (distinct PRs), excluded_leak (removed cases)
"""
import argparse
import csv
import json

from common import read_jsonl, doc, git_commit
from context_builder import build_context, TOKENIZER
from pack_exp1 import build_context_exp1

ARMS = [(c, a) for c in ("fixed_s512_o77", "struct_c256") for a in (0, 0.25, 0.5, 1)]
BUDGET = 2560


def covered(spans, ctx_chunks, pr, text):
    iv = sorted((c["start"], c["end"]) for c in ctx_chunks if c["pr_number"] == pr)
    merged = []
    for s, e in iv:
        if merged and (s <= merged[-1][1] or not text[merged[-1][1]:s].strip()):
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [any(ms <= a and b <= me for ms, me in merged) for a, b in spans]


def main(a):
    from transformers import AutoTokenizer
    qtok = AutoTokenizer.from_pretrained("Qwen/Qwen3-Embedding-0.6B",
                                         revision="97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3")
    qfile = "questions_dev2.jsonl" if a.split == "dev2" else "questions.jsonl"
    qs = [q for q in read_jsonl(qfile) if q["split"] == a.split]
    arms = [(c, al) for c, al in ARMS if al in a.alphas and c in a.chunkings]
    rows = []
    for chunking, alpha in arms:
        for q in qs:
            if a.packer == "exp1":
                ctx = build_context_exp1(q["id"], alpha, BUDGET, q["exclude_prs"], chunking, a.links)
            else:
                ctx = build_context(q["id"], alpha, BUDGET, False, q["exclude_prs"], chunking)
            ch = ctx["chunks"]
            r = {"id": q["id"], "type": q["type"], "chunking": chunking, "alpha": alpha,
                 "n_chunks": len(ch), "n_linked": ctx["n_linked"], "tokens": ctx["tokens"],
                 "qwen_tokens": len(qtok("\n\n".join(c["text"] for c in ch))["input_ids"]),
                 "n_prs": ctx["n_prs"],
                 "gold_pr_in_ctx": any(c["pr_number"] == q["pr_number"] for c in ch),
                 "excluded_leak": [c["pr_number"] for c in ch if c["pr_number"] in q["exclude_prs"]],
                 "chunk_ids": " ".join(c["chunk_id"] for c in ch)}
            if q["type"] in ("answerable", "removed") and q["spans"]:
                cov = covered(q["spans"], ch, q["pr_number"], doc(q["pr_number"])["text"])
                r |= {"any_cov": any(cov), "all_cov": all(cov)}
                r["headroom"] = r["gold_pr_in_ctx"] and not r["any_cov"]
            rows.append(r)

    def mean(xs):
        xs = list(xs)
        return round(sum(xs) / len(xs), 3) if xs else None

    summary = {"split": a.split, "budget": BUDGET, "packer": a.packer, "links": a.links, "tokenizer": TOKENIZER, "git_commit": git_commit(),
               "note": "reporting only; alpha is tuned on the dev set, never on test", "arms": {}}
    for chunking, alpha in arms:
        rs = [r for r in rows if r["chunking"] == chunking and r["alpha"] == alpha]
        ans = [r for r in rs if r["type"] == "answerable"]
        rm = [r for r in rs if r["type"] == "removed"]
        summary["arms"][f"{chunking}|a={alpha}"] = {
            "answerable_n": len(ans),
            "any_cov": mean(r["any_cov"] for r in ans), "all_cov": mean(r["all_cov"] for r in ans),
            "gold_pr_in_ctx": mean(r["gold_pr_in_ctx"] for r in ans),
            "headroom": sum(r["headroom"] for r in ans),
            "mean_chunks": mean(r["n_chunks"] for r in rs), "mean_linked": mean(r["n_linked"] for r in rs),
            "mean_tokens": mean(r["tokens"] for r in rs), "mean_qwen_tokens": mean(r["qwen_tokens"] for r in rs),
            "mean_prs": mean(r["n_prs"] for r in rs),
            "removed_quote_covered": sum(r["any_cov"] for r in rm),
            "removed_excluded_leak": sum(bool(r["excluded_leak"]) for r in rm)}
    tag = "" if a.packer == "own" else f"_exp1pack_{a.links}"
    with open(f"results/links_eval_{a.split}{tag}.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    with open(f"results/links_eval_{a.split}{tag}_per_query.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["dev", "test", "dev2"])
    ap.add_argument("--alphas", nargs="+", type=float, default=[0, 0.25, 0.5, 1])
    ap.add_argument("--packer", choices=["own", "exp1"], default="own",
                    help="own = context_builder (cosine scores); exp1 = relations.expand_and_pack")
    ap.add_argument("--links", choices=["exp2", "exp1_context"], default="exp2")
    ap.add_argument("--chunkings", nargs="+", default=["fixed_s512_o77", "struct_c256"])
    main(ap.parse_args())
