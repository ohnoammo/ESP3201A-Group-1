"""Faithfulness of arm W-F answers (tuning_rule_wholepr.md), same judges and settings as faithfulness.py.

    python faithfulness_w.py                      # answered answerable -> results/faithfulness_W.jsonl
    python faithfulness_w.py --set unanswerable   # -> results/faithfulness_W_unanswerable.jsonl

Premises: (a) cited whole PR block(s) as shown (truncated text for a truncated rank-1 PR), primary;
(b) the full W context. Blocks go through faithfulness.windows (<= 400 words, one-block overlap,
blocks over 400 words split 400/100), MiniCheck max over windows; HHEM gets the blocks joined.
Claims: faithfulness.sentences after removing W citations ([PR<n>], [PR<n>-c<k>]).
Contexts are rebuilt with run_generation.wholepr_context and must match the generated row.
Answered / unanswerable as in score_w.py. Resumes.
"""
import argparse
import json
import os
import re
import statistics as st

from tqdm import tqdm

from common import git_commit, read_jsonl
from faithfulness import HHEM, MiniCheck, sentences
from run_generation import wholepr_context
from score_w import FILES_W, auto_w, unanswerable

OUT = {"answerable": "results/faithfulness_W.jsonl", "unanswerable": "results/faithfulness_W_unanswerable.jsonl"}
WCITES = re.compile(r"\[\s*PR\d+(?:-c\d+)?(?:\s*[,;]\s*PR\d+(?:-c\d+)?)*\s*\]")


def main(args):
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    todo = []
    for path in FILES_W.values():
        for r in read_jsonl(path):
            q = qs[r["id"]]
            if args.set == "answerable" and not (r["type"] == "answerable" and q["split"] == "test"):
                continue
            if args.set == "unanswerable" and not unanswerable(r):
                continue
            a = auto_w(r, q)
            if not (a["abstained"] or a["empty_answer"]):
                todo.append((path, r, q, a))
    out_path = OUT[args.set]
    print(f"{len(todo)} rows to score ({args.set})")
    if os.path.exists(out_path):
        done = {(x["file"], x["id"], x["condition"]) for x in read_jsonl(out_path)}
        todo = [t for t in todo if (t[0], t[1]["id"], t[1]["condition"]) not in done]
    mc, hh = MiniCheck(), HHEM()
    commit = git_commit()
    with open(out_path, "a", encoding="utf-8") as f:
        for path, r, q, a in tqdm(todo, mininterval=10):
            blocks, _ = wholepr_context(q, "wpr-fixed")
            assert [b["chunk_id"] for b in blocks] == r["context_chunk_ids"], (r["id"], r["condition"])
            cited = set(a["cited_prs"])
            prem = {"cited": [b["text"] for b in blocks if b["pr_number"] in cited],
                    "full": [b["text"] for b in blocks]}
            sents = sentences(WCITES.sub("", r["response"]))
            rec = {"file": path, "id": r["id"], "condition": r["condition"], "model": r["model"],
                   "n_sentences": len(sents), "n_cited": len(cited), "git_commit": commit}
            for pn, chunks in prem.items():
                for jn, judge in (("minicheck", mc), ("hhem", hh)):
                    if pn == "cited" and not chunks:
                        rec[f"{jn}_{pn}_min"] = rec[f"{jn}_{pn}_mean"] = None
                        continue
                    s = [judge.score(chunks, x) for x in sents]
                    rec[f"{jn}_{pn}_min"], rec[f"{jn}_{pn}_mean"] = min(s), st.mean(s)
            f.write(json.dumps(rec) + "\n")
            f.flush()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=list(OUT), default="answerable")
    main(ap.parse_args())
