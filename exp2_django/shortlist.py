"""Tier 1, step 1: shortlist candidate PRs for "why" questions.

    python shortlist.py            # -> shortlist.json (+ prints the funnel), pr_digests.txt

Thresholds (applied in this order, counts printed):
  1. in Exp 1 pool A (2,231 PRs)
  2. merged on GitHub
  3. not docs-only (at least one changed file outside docs/)
  4. substantive description: >= MIN_DESC_WORDS words after removing Django's PR template
     (ticket line, checklist, headings) and URLs
  5. discussion: >= MIN_THREADS human review threads, or >= MIN_DISCUSSION human review
     threads + conversation comments in total
  6. oracle context fits: PR document <= MAX_DOC_TOKENS tokens (Exp 1 token unit), so all of
     its fixed 512/77 chunks fit into num_ctx 8192 with the prompt
Then up to N_SHORTLIST PRs are taken in a fixed SHA-256 order (seed 42), no cherry-picking.
"""
import hashlib
import json
import re

from common import pool_numbers, load_pr, doc, chunks, build_document
from pr_document import is_bot
from chunking import count_tokens

MIN_DESC_WORDS = 40
MIN_THREADS = 2
MIN_DISCUSSION = 4
MAX_DOC_TOKENS = 4000
N_SHORTLIST = 60

_TEMPLATE = re.compile(r"^\s*(#{1,6}\s.*|[-*]\s*\[[ xX]\].*|ticket-\d+.*|Trac ticket.*|"
                       r"Branch description.*|Checklist.*)$", re.M)
_URL = re.compile(r"https?://\S+")


def clean_desc(body):
    body = re.sub(r"<!--.*?-->", " ", body or "", flags=re.S)
    return _URL.sub(" ", _TEMPLATE.sub(" ", body))


def features(n):
    pr = load_pr(n)
    roots = [c for c in pr.get("review_comments", [])
             if not c.get("in_reply_to_id") and not is_bot(c.get("user"))]
    conv = [c for c in pr.get("issue_comments", []) if not is_bot(c.get("user"))]
    files = pr.get("files", [])
    return {"n": n, "title": pr.get("title"), "merged": bool(pr.get("merged")),
            "docs_only": bool(files) and all(f["filename"].startswith("docs/") for f in files),
            "desc_words": len(clean_desc(pr.get("body")).split()),
            "threads": len(roots), "conv": len(conv),
            "doc_tokens": count_tokens(doc(n)["text"])}


def main():
    pool = pool_numbers()
    feats = [features(n) for n in pool]
    steps = [("in pool A", lambda f: True),
             ("merged", lambda f: f["merged"]),
             ("not docs-only", lambda f: not f["docs_only"]),
             (f"description >= {MIN_DESC_WORDS} words", lambda f: f["desc_words"] >= MIN_DESC_WORDS),
             (f"threads >= {MIN_THREADS} or threads+comments >= {MIN_DISCUSSION}",
              lambda f: f["threads"] >= MIN_THREADS or f["threads"] + f["conv"] >= MIN_DISCUSSION),
             (f"document <= {MAX_DOC_TOKENS} tokens", lambda f: f["doc_tokens"] <= MAX_DOC_TOKENS)]
    keep = feats
    funnel = []
    for name, ok in steps:
        keep = [f for f in keep if ok(f)]
        funnel.append((name, len(keep)))
        print(f"  {name:<45} {len(keep):>5}")
    order = sorted(keep, key=lambda f: hashlib.sha256(f"42:{f['n']}".encode()).hexdigest())
    short = order[:N_SHORTLIST]
    with open("shortlist.json", "w", encoding="utf-8") as fh:
        json.dump({"thresholds": {"MIN_DESC_WORDS": MIN_DESC_WORDS, "MIN_THREADS": MIN_THREADS,
                                  "MIN_DISCUSSION": MIN_DISCUSSION,
                                  "MAX_DOC_TOKENS": MAX_DOC_TOKENS, "N": N_SHORTLIST},
                   "funnel": funnel, "order": [f["n"] for f in order], "shortlist": short},
                  fh, indent=1)
    print(f"Shortlist: {len(short)} PRs -> shortlist.json")


if __name__ == "__main__":
    main()
