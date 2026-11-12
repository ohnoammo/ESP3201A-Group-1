"""Relation factor, step B: explanation-link maps from character spans only (no LLM).

    python link_map.py         # -> C:/Users/kwekt/ESP3201A_local/links_<chunking>.json + summary

Part-level links (decided 21 Oct, James):
  hunk <-> review_thread   only threads mapped to a hunk of the final diff (inspect_links.map_thread:
                           exact @@ header, current line in range, or unique commented-line text)
  part  -> title_description   every other part points to its PR's title+description (parent)
  conversation <-> conversation  each comment to the previous and next comment by created_at
                           (comment id breaks ties); bot comments excluded as in pr_document
Not included: file-level fallback for outdated threads; description -> all conversation.

Chunk level: a chunk inherits the links of every part it overlaps; a link points at every chunk
overlapping the target part. Self-links dropped. Stored as
  {chunk_id: [[target_chunk_id, link_type], ...]}   link_type in hunk->thread, thread->hunk,
                                                    parent, conv_prev, conv_next
"""
import json
import os
from collections import Counter

from common import doc, load_pr, chunks, pool_numbers
from pr_document import _threads, is_bot
from inspect_links import hunks_by_file, map_thread

LOCAL = "C:/Users/kwekt/ESP3201A_local"
STRUCT_FILE = os.path.join(LOCAL, "exp1_copy", "chunks", "swe_struct_c256_2231docs_0611be80.json")  # new pool A
CHUNKINGS = ("fixed_s512_o77", "struct_c256")

_struct = None


def chunks_for(chunking, n):
    """Chunk dicts (chunk_id, pr_number, start, end, text) for one PR."""
    global _struct
    if chunking == "fixed_s512_o77":
        return chunks(n)
    if _struct is None:
        with open(STRUCT_FILE, encoding="utf-8") as f:
            _struct = {}
            for c in json.load(f)["chunks"]:
                _struct.setdefault(int(c["pr_number"]), []).append(c)
    return _struct.get(int(n), [])


def part_links(n, pr=None, d=None):
    """[(source_part_index, target_part_index, link_type)] for one PR (pr/d: optional raw PR
    and document, e.g. a redacted variant; default = the pool PR)."""
    pr = pr or load_pr(n)
    d = d or doc(n)
    parts = d["parts"]
    idx = {id(p): i for i, p in enumerate(parts)}
    out = []
    parent = next((i for i, p in enumerate(parts) if p["type"] == "title_description"), None)
    if parent is not None:
        out += [(i, parent, "parent") for i, p in enumerate(parts) if i != parent]
    # hunk <-> review thread
    hunks = hunks_by_file(d)
    threads = [[c for c in t if not is_bot(c.get("user"))]
               for t in _threads(pr.get("review_comments", []))]
    threads = [t for t in threads if t]
    tparts = [i for i, p in enumerate(parts) if p["type"] == "review_thread"]
    assert len(threads) == len(tparts), n
    for t, ti in zip(threads, tparts):
        h, _ = map_thread(t[0], hunks)
        if h:
            hi = idx[id(h["part"])]
            out += [(hi, ti, "hunk->thread"), (ti, hi, "thread->hunk")]
    # conversation neighbours by created_at
    conv = [c for c in pr.get("issue_comments", []) if not is_bot(c.get("user"))]
    cparts = [i for i, p in enumerate(parts) if p["type"] == "conversation"]
    assert len(conv) == len(cparts), n
    order = sorted(range(len(conv)), key=lambda j: (conv[j].get("created_at") or "", conv[j]["id"]))
    for a, b in zip(order, order[1:]):
        out += [(cparts[b], cparts[a], "conv_prev"), (cparts[a], cparts[b], "conv_next")]
    return parts, out


def chunk_links(chunking, n, pr=None, d=None, cks=None):
    parts, plinks = part_links(n, pr, d)
    cks = cks if cks is not None else chunks_for(chunking, n)
    over = [[c["chunk_id"] for c in cks if c["start"] < p["end"] and p["start"] < c["end"]]
            for p in parts]
    links = {c["chunk_id"]: set() for c in cks}
    for s, t, typ in plinks:
        for cs in over[s]:
            for ct in over[t]:
                if cs != ct:
                    links[cs].add((ct, typ))
    return {k: sorted(v) for k, v in links.items()}


def main():
    pool = pool_numbers()
    for chunking in CHUNKINGS:
        allmap, by_type, zero_thread_prs, prs_with_threads = {}, Counter(), 0, 0
        for n in pool:
            m = chunk_links(chunking, n)
            allmap.update(m)
            types = Counter(t for v in m.values() for _, t in v)
            by_type.update(types)
            if any(p["type"] == "review_thread" for p in doc(n)["parts"]):
                prs_with_threads += 1
                zero_thread_prs += types["hunk->thread"] == 0
        path = os.path.join(LOCAL, f"links_{chunking}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(allmap, f)
        n_ch = len(allmap)
        summary = {"chunking": chunking, "n_chunks": n_ch,
                   "links_by_type": dict(by_type),
                   "chunks_with_any_link": sum(bool(v) for v in allmap.values()),
                   "mean_links_per_chunk": sum(len(v) for v in allmap.values()) / n_ch,
                   "prs_with_review_threads": prs_with_threads,
                   "prs_with_threads_but_zero_hunk_thread_links": zero_thread_prs,
                   "file": path}
        os.makedirs("results", exist_ok=True)
        with open(f"results/link_map_{chunking}_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=1)
        print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
