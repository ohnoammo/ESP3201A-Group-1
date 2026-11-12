"""Shared helpers for Experiment 2. Experiment 1 code is imported READ-ONLY (never modified).

- PR documents come from Exp 1's pr_document.build_document, chunks from Exp 1's chunking.py,
  so character offsets and chunk boundaries match Exp 1 exactly.
- Frozen Exp 2 chunk setting: fixed 512 tokens / 77 overlap (chunk ids "<pr>_fixed_s512_o77_<i>",
  the same ids as Exp 1's chunk cache swe_fixed_s512_o77_2231docs_9cb76462.json).
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Exp 1 code + PR data: the read-only COPY outside OneDrive (code from ESP3201A_SWE_exp1_2210,
# 22 Oct; pool A with the same-ticket filter). Old OneDrive folder no longer used.
EXP1 = "C:/Users/kwekt/ESP3201A_local/exp1_copy"
PRS = os.path.join(EXP1, "prs", "django_django")
sys.path.append(EXP1)            # appended: Exp 2 modules must win (Exp 1 now has its own retrieve.py)

from pr_document import build_document          # noqa: E402  (Exp 1, read-only)
from chunking import fixed_size_chunks          # noqa: E402  (Exp 1, read-only)

CHUNK_CFG = {"name": "fixed_s512_o77", "size": 512, "overlap": 77}
EXP1_CHUNK_CACHE = os.path.join(EXP1, "chunks", "swe_fixed_s512_o77_2231docs_9cb76462.json")
TICKET = re.compile(r"#(\d{4,6})\b")


def pool_numbers():
    """The 2,231 PRs of Exp 1's pool A (231 fixing PRs + 2,000 distractors)."""
    with open(os.path.join(PRS, "_pool_A2000.json"), encoding="utf-8") as f:
        return json.load(f)["numbers"]


def load_pr(n):
    with open(os.path.join(PRS, f"{n}.json"), encoding="utf-8") as f:
        return json.load(f)


_docs = {}


def doc(n):
    if n not in _docs:
        _docs[n] = build_document(load_pr(n))
    return _docs[n]


def chunks(n):
    """Fixed 512/77 chunks of one PR, with Exp 1's chunk ids and character spans."""
    d = doc(n)
    out = []
    for i, c in enumerate(fixed_size_chunks(d["text"], CHUNK_CFG["size"], CHUNK_CFG["overlap"])):
        out.append(c | {"chunk_id": f"{n}_{CHUNK_CFG['name']}_{i}", "pr_number": n})
    return out


_tickets = {}


def tickets(n):
    """Trac ticket numbers cited in a PR's title."""
    if n not in _tickets:
        _tickets[n] = set(TICKET.findall(load_pr(n).get("title") or ""))
    return _tickets[n]


def same_ticket_prs(n, pool=None):
    """Other pool PRs whose title cites a ticket that PR n's title cites."""
    ts = tickets(n)
    if not ts:
        return []
    return sorted(m for m in (pool or pool_numbers()) if m != n and tickets(m) & ts)


def git_commit():
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                                      text=True, stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                        cwd=HERE, text=True)
        return sha + ("-dirty" if dirty.strip() else "")
    except Exception:
        return "unknown"


def git_dirty_files():
    """Uncommitted paths (e.g. review sheets being marked), recorded next to '-dirty'."""
    try:
        out = subprocess.check_output(["git", "status", "--porcelain"], cwd=HERE, text=True)
        return [line[3:] for line in out.splitlines() if line.strip()]
    except Exception:
        return ["unknown"]


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


_TICKET_URL = re.compile(r"code\.djangoproject\.com/ticket/(\d+)|\bticket[-#\s]?(\d{4,6})\b", re.I)


def external_ticket(n):
    """Does the PR point to an external Trac ticket? (for no-reason questions, where the reason
    may live outside the PR). Looks at title, description, commits and conversation."""
    pr = load_pr(n)
    texts = [pr.get("title") or "", pr.get("body") or ""] + [c["message"] for c in pr.get("commits", [])] \
        + [c.get("body") or "" for c in pr.get("issue_comments", [])]
    linked = sorted({a or b for t in texts for a, b in _TICKET_URL.findall(t)})
    cited = sorted({m for t in texts[:1] + texts[2:3] for m in TICKET.findall(t)})
    return {"links_external_ticket": bool(linked), "linked_ticket_ids": linked,
            "title_or_commit_cites_ticket": bool(cited or linked)}
