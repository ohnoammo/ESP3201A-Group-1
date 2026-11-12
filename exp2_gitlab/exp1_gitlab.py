"""Experiment 1 on gitlab-runner: issue -> the MR that closes it, on the final setting
(dense Qwen3-Embedding-0.6B, fixed 512/77), packed into 2,560 tokens at alpha 0 and alpha 1.
Same metrics as run_retrieval_swe.evaluate. Labels come from closing references, not SWE-bench,
so these numbers are not comparable like for like with the Django ones. Counts only; no tests.

  python exp1_gitlab.py --pool A270
"""
import argparse
import csv
import json
import os
import subprocess

import numpy as np

from dense_retrieval import Qwen3Embedder, DEFAULT_MODEL, TASKS
from exp1_common import make_chunks
from github_prs import load_pool, load_pr
from metrics import pr_level, score_question_multidoc
from pr_document import build_document, evidence_ranges, shares_ngram
from relations import build_links, expand_and_pack, token_counter

REPO = "gitlab-org/gitlab-runner"
CFG = {"name": "fixed_s512_o77", "method": "fixed", "size": 512, "overlap": 77}
INSTRUCTION = TASKS["swe"]                      # Exp 1's instruction, unchanged
BUDGET, K, DEPTH, ALPHAS = 2560, 5, 100, (0.0, 1.0)


def clean_commit():
    """Hard rule: commit before every run. Stops on uncommitted changes; returns the commit for the result rows."""
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise SystemExit("Uncommitted changes: commit before running")
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()


def main(a):
    commit = clean_commit()
    tasks = json.load(open(os.path.join("exp1_gitlab", f"tasks_{a.pool}.json"), encoding="utf-8"))["tasks"]
    docs = {}
    for n in load_pool(REPO, a.pool)["numbers"]:
        pr = load_pr(REPO, n)
        assert pr.get("comments_fetched"), f"MR {n} was saved without its comments"
        d = build_document(pr)
        if d["text"].strip():
            docs[d["paper_id"]] = d
    doc_list = [docs[k] for k in sorted(docs, key=int)]
    chunks, info = make_chunks(doc_list, CFG, "gitlab_nobots2")  # new cache name: older chunks had no comments
    by_id = {c["chunk_id"]: c for c in chunks}
    links = build_links(chunks, docs, kinds=("code",))
    emb = Qwen3Embedder(DEFAULT_MODEL, task=INSTRUCTION, cache_path=os.path.join("emb_cache", "qwen3_gitlab.npz"))
    E = emb.embed_documents([c["text"] for c in chunks])
    emb.embed_queries([t["problem_statement"] for t in tasks])
    lines = {pid: d["line_spans"] for pid, d in docs.items()}
    ntok, rows = token_counter(), []
    for t in tasks:
        gold = str(t["pr_number"])
        s = E @ emb.embed_query(t["problem_statement"])
        ranked = [chunks[i] for i in np.argsort(-s, kind="stable")[:DEPTH]]
        base = {"config": CFG["name"], "budget": BUDGET, "model": DEFAULT_MODEL, "git_commit": commit,
                "pr": gold, "issue": t["issue"],
                "copied_10gram": shares_ngram(t["problem_statement"], docs[gold]["text"], 10)}
        base |= pr_level(ranked, gold, K)
        ev = evidence_ranges(docs[gold])
        for alpha in ALPHAS:
            p = expand_and_pack(ranked, alpha, links, by_id, BUDGET, ntok)
            m = score_question_multidoc(lines, {gold: ev}, p, len(p)) if ev and p else {}
            rows.append(base | {"alpha": alpha, "budget_recall": m.get("recall"), "budget_f1": m.get("f1"),
                                "budget_precision": m.get("precision"),
                                "gold_in_budget": any(c["paper_id"] == gold for c in p),
                                "n_linked": sum(c["linked"] for c in p), "n_chunks": len(p)})
    with open(os.path.join("results", f"exp1_gitlab_{a.pool}_per_query.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(tasks)} tasks, {len(doc_list)} MRs, {len(chunks)} chunks, set {info['chunk_set']}, "
          f"query truncated {emb.n_truncated_queries}, chunks truncated {emb.n_truncated}, "
          f"copied 10-gram {sum(r['copied_10gram'] for r in rows) // len(ALPHAS)}")
    for alpha in ALPHAS:
        sel = [r for r in rows if r["alpha"] == alpha]
        mean = lambda key: np.mean([r[key] for r in sel if r[key] is not None])
        print(f"alpha {alpha}: Hit@5 {sum(r['pr_hit'] for r in sel):.0f}/{len(sel)}, MRR@5 {mean('pr_mrr'):.3f}, "
              f"gold MR in budget {sum(r['gold_in_budget'] for r in sel)}/{len(sel)}, "
              f"budget recall {mean('budget_recall'):.3f}, precision {mean('budget_precision'):.3f}, "
              f"F1 {mean('budget_f1'):.3f}, linked chunks {mean('n_linked'):.1f}, chunks {mean('n_chunks'):.1f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="A270")
    main(ap.parse_args())
