"""Turn one cached PR (github_prs.py) into one text document with character spans.

Document order (fixed): title, description, commit messages, each file's diff (with a file
path header), review comment threads, conversation comments. Bot comments are excluded.
No other content is stripped (issue numbers, links, names stay).

Every part is recorded as a character span, so:
  - structural chunks are exactly these parts (chunking.structural_chunks), and
  - evidence (the fixing PR's changed lines) uses the same coordinates as every chunk,
    fixed-size or structural, so metrics.py scores both the same way.

Document dict:
  {"paper_id": "<pr number>", "pr_number", "text", "created_ts", "n_files",
   "parts": [{"type", "start", "end", "file_path", "header"}],
   "changed_lines": [(start, end, file_path)],      # '+'/'-' lines of every file diff
   "line_spans": [(start, end)]}                     # every non-empty line (scoring units)
Part types: title_description, commits, hunk, file_nodiff, review_thread, conversation.
Hunk parts also carry "new_lines" (first, last line in the new file) and review_thread parts
carry "line" (the line the thread's first comment is on), used by relations.py to link a
review thread to the hunk it comments on. These fields never change the text or spans.
"""
import re

from swebench_loader import to_ts

EXTRA_BOTS = {"github-actions", "codecov", "dependabot", "netlify", "readthedocs"}


def is_bot(user, extra_bots=EXTRA_BOTS):
    login = (user or {}).get("login") or ""
    return ((user or {}).get("type") == "Bot" or login.endswith("[bot]")
            or login.lower() in extra_bots)


class _Doc:
    def __init__(self):
        self.buf, self.pos, self.parts = [], 0, []

    def add(self, text):
        start = self.pos
        self.buf.append(text)
        self.pos += len(text)
        return start, self.pos

    def part(self, ptype, start, end, file_path=None, header="", **extra):
        if end > start:
            self.parts.append({"type": ptype, "start": start, "end": end,
                               "file_path": file_path, "header": header} | extra)


def _hunks(patch):
    """(offset, end) of each '@@ ... @@' hunk inside one file's patch text."""
    starts = [m.start() for m in re.finditer(r"^@@", patch, flags=re.M)] or [0]
    return [(s, (starts[i + 1] - 1) if i + 1 < len(starts) else len(patch))
            for i, s in enumerate(starts)]


def _hunk_new_lines(hunk_text):
    """(first, last) line numbers a hunk covers in the NEW version of the file, from its
    '@@ -a,b +c,d @@' header; None if there is no header. Used to attach review threads
    (GitHub gives each review comment a line number in the new file) to their hunk."""
    m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", hunk_text)
    if not m:
        return None
    first, count = int(m.group(1)), int(m.group(2) or 1)
    return (first, first + max(count, 1) - 1)


def _threads(review_comments):
    """Group review comments into threads: root comment + its replies, in time order."""
    roots, replies = [], {}
    for c in sorted(review_comments, key=lambda c: (c.get("created_at") or "", c["id"])):
        if c.get("in_reply_to_id"):
            replies.setdefault(c["in_reply_to_id"], []).append(c)
        else:
            roots.append(c)
    known = {c["id"] for c in roots}
    for rid, cs in replies.items():                   # replies whose root is a bot / missing
        if rid not in known:
            roots.append(cs.pop(0))
            replies.setdefault(roots[-1]["id"], []).extend(cs)
    return [[r] + replies.get(r["id"], []) for r in roots]


def build_document(pr, extra_bots=EXTRA_BOTS):
    d = _Doc()
    # title + description (one part)
    s, _ = d.add(f"Title: {pr.get('title') or ''}\n\n")
    _, e = d.add(f"Description:\n{(pr.get('body') or '').strip()}\n")
    d.part("title_description", s, e)
    d.add("\n")

    # commit messages (one part)
    msgs = [c["message"].strip() for c in pr.get("commits", []) if c.get("message")]
    if msgs:
        s, e = d.add("Commit messages:\n" + "\n\n".join(msgs) + "\n")
        d.part("commits", s, e)
        d.add("\n")

    # file diffs: one part per hunk; header line kept in the text and repeated in the chunk
    changed = []
    for f in pr.get("files", []):
        path = f["filename"]
        header = f"File: {path} ({f.get('status')})\n"
        if f.get("patch") is None:
            s, e = d.add(header.rstrip("\n") + " [diff not available]\n")
            d.part("file_nodiff", s, e, path)
            d.add("\n")
            continue
        d.add(header)
        patch = f["patch"].rstrip("\n")
        ps, _ = d.add(patch + "\n")
        for hs, he in _hunks(patch):
            d.part("hunk", ps + hs, ps + he, path, header,
                   new_lines=_hunk_new_lines(patch[hs:he]))
        for m in re.finditer(r"^[+-].*$", patch, flags=re.M):
            if m.end() > m.start() + 1:                   # skip bare '+' / '-' (blank lines)
                changed.append((ps + m.start(), ps + m.end(), path))
        d.add("\n")

    # review comment threads (one part each)
    for thread in _threads(pr.get("review_comments", [])):
        thread = [c for c in thread if not is_bot(c.get("user"), extra_bots)]
        if not thread:
            continue
        path = thread[0].get("path")
        body = "".join(f"@{c['user']['login']}: {(c.get('body') or '').strip()}\n" for c in thread)
        s, e = d.add(f"Review thread on {path}:\n{body}")
        root = thread[0]
        d.part("review_thread", s, e, path,
               line=root.get("line") or root.get("original_line"))
        d.add("\n")

    # conversation comments (one part each)
    for c in pr.get("issue_comments", []):
        if is_bot(c.get("user"), extra_bots):
            continue
        s, e = d.add(f"Comment by @{c['user']['login']}:\n{(c.get('body') or '').strip()}\n")
        d.part("conversation", s, e)
        d.add("\n")

    text = "".join(d.buf)
    return {"paper_id": str(pr["number"]), "pr_number": pr["number"], "text": text,
            "created_ts": to_ts(pr["created_at"]) if pr.get("created_at") else None,
            "n_files": len(pr.get("files", [])), "parts": d.parts,
            "changed_lines": changed,
            "line_spans": [(m.start(), m.end()) for m in re.finditer(r"[^\n]*\S[^\n]*", text)]}


def evidence_ranges(doc, source_files=None):
    """Gold evidence = the fixing PR's changed lines (source + tests + docs). With
    source_files (the files in SWE-bench's `patch`), only lines in those files."""
    return [(s, e) for s, e, path in doc["changed_lines"]
            if source_files is None or path in source_files]


# ---------- copied-text check ----------
def _words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def shares_ngram(a, b, n=10):
    """True if texts a and b share >= n consecutive (lowercased) words."""
    wa, wb = _words(a), _words(b)
    if len(wa) < n or len(wb) < n:
        return False
    grams = {tuple(wa[i:i + n]) for i in range(len(wa) - n + 1)}
    return any(tuple(wb[i:i + n]) in grams for i in range(len(wb) - n + 1))
