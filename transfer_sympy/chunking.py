"""Two chunking methods for PR documents (pr_document.build_document). Both return chunks
with character spans in the PR text, so evaluation can check exactly which changed lines
each chunk covers.

Chunk format: {"text": str, "start": int, "end": int, "chunk_type": str, "file_path": str|None}

Size unit = "tokens" = words and single punctuation symbols (regex \\w+|[^\\w\\s]). Simple,
fast and independent of any retriever's own tokenizer. (Qwen3 truncation is checked
separately in dense_retrieval.py.)

Why structural instead of semantic chunking: semantic chunking is sentence-based (built for
prose), but a PR is mostly diff lines, and PRs already have explicit boundaries (description,
commits, hunks, comment threads).
"""
import re

TOKEN = re.compile(r"\w+|[^\w\s]")


def count_tokens(text):
    return len(TOKEN.findall(text))


# ---------- Fixed-size chunking ----------
def fixed_size_chunks(text, size=256, overlap=0):
    """Windows of `size` tokens over the whole PR text, stepping by size - overlap tokens."""
    toks = [(m.start(), m.end()) for m in TOKEN.finditer(text)]
    step = max(1, size - overlap)
    chunks = []
    for i in range(0, len(toks), step):
        window = toks[i:i + size]
        if not window:
            break
        s, e = window[0][0], window[-1][1]
        chunks.append({"text": text[s:e], "start": s, "end": e,
                       "chunk_type": "fixed", "file_path": None})
        if i + size >= len(toks):
            break
    return chunks


# ---------- Structural chunking ----------
def _split_at_lines(text, start, end, cap):
    """Split text[start:end] into pieces of <= cap tokens, cutting only at line breaks
    (a single line longer than cap is cut by tokens)."""
    pieces, cur_s, cur_e, cur_n = [], None, None, 0
    for m in re.finditer(r"[^\n]*\n?", text[start:end]):
        if not m.group():
            continue
        ls, le = start + m.start(), start + m.end()
        n = count_tokens(text[ls:le])
        if n > cap:                                      # very long line: cut by tokens
            if cur_s is not None:
                pieces.append((cur_s, cur_e))
                cur_s, cur_n = None, 0
            for c in fixed_size_chunks(text[ls:le], size=cap):
                pieces.append((ls + c["start"], ls + c["end"]))
            continue
        if cur_s is not None and cur_n + n > cap:
            pieces.append((cur_s, cur_e))
            cur_s, cur_n = None, 0
        if cur_s is None:
            cur_s = ls
        cur_e, cur_n = le, cur_n + n
    if cur_s is not None:
        pieces.append((cur_s, cur_e))
    return pieces


def structural_chunks(doc, cap=512, stats=None):
    """One chunk per PR part: title + description, commit messages, each diff hunk (text
    prefixed with its 'File: path' header), each review comment thread, each conversation
    comment. Never cuts across parts; a part over `cap` tokens is split at line breaks.
    stats: optional dict, counts parts that had to be split ("split_parts")."""
    text, chunks = doc["text"], []
    for p in doc["parts"]:
        pieces = [(p["start"], p["end"])]
        if count_tokens(text[p["start"]:p["end"]]) > cap:
            pieces = _split_at_lines(text, p["start"], p["end"], cap)
            if stats is not None:
                stats["split_parts"] = stats.get("split_parts", 0) + 1
        for s, e in pieces:
            body = text[s:e].rstrip("\n")
            e = s + len(body)
            if not body.strip():
                continue
            chunks.append({"text": p.get("header", "") + body, "start": s, "end": e,
                           "chunk_type": p["type"], "file_path": p.get("file_path")})
    return chunks
