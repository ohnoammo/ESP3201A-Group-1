"""Step 1 (relation factor): what link metadata actually exists? Read-only, no LLM.

    python inspect_links.py      # -> results/link_inspection.json + printed summary

Per review THREAD (root comment = first non-bot comment, as pr_document groups them), try to
map it to a hunk of the PR's final diff (pr_document "hunk" parts):
  M1 header   the thread's diff_hunk "@@ -a,b +c,d @@" header equals a hunk header in that file
  M2 line     `line` (current new-file line; None if the comment is outdated) falls inside a
              hunk's new-file range [c, c+d) in that file
  M3 content  the commented line (last line of diff_hunk) appears verbatim in one hunk's text
Also: conversation comments (anchors?), and fixed 512/77 chunk composition.
"""
import json
import re
from collections import Counter

from common import doc, load_pr, chunks, pool_numbers
from pr_document import _threads, is_bot

HDR = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def hunks_by_file(d):
    out = {}
    for p in d["parts"]:
        if p["type"] != "hunk":
            continue
        text = d["text"][p["start"]:p["end"]]
        m = HDR.match(text)
        new = (int(m.group(3)), int(m.group(4) or 1)) if m else None
        out.setdefault(p["file_path"], []).append({"part": p, "header": text.split("\n", 1)[0].split(" @@")[0] + " @@",
                                                    "new": new, "text": text})
    return out


def map_thread(root, hunks):
    fh = hunks.get(root.get("path"), [])
    if not fh:
        return None, "file_not_in_final_diff"
    dh = root.get("diff_hunk") or ""
    hdr = dh.split("\n", 1)[0].split(" @@")[0] + " @@" if dh.startswith("@@") else None
    m1 = [h for h in fh if hdr and h["header"] == hdr]
    if len(m1) == 1:
        return m1[0], "M1_header"
    if root.get("line"):
        m2 = [h for h in fh if h["new"] and h["new"][0] <= root["line"] < h["new"][0] + h["new"][1]]
        if len(m2) == 1:
            return m2[0], "M2_line"
    last = dh.rstrip("\n").split("\n")[-1] if dh else ""
    if len(last.strip()) > 3:
        m3 = [h for h in fh if last in h["text"]]
        if len(m3) == 1:
            return m3[0], "M3_content"
        if len(m3) > 1:
            return None, "M3_ambiguous"
    return None, "outdated_or_unmatched" if not root.get("line") else "unmatched"


def main():
    pool = pool_numbers()
    how = Counter()
    n_threads = n_prs_with_threads = n_prs_zero_links = 0
    same_chunk = diff_chunk = 0
    conv_n = 0
    chunk_mix = Counter()
    per_pr = {}
    for n in pool:
        pr, d = load_pr(n), doc(n)
        hunks = hunks_by_file(d)
        threads = [[c for c in t if not is_bot(c.get("user"))]
                   for t in _threads(pr.get("review_comments", []))]
        threads = [t for t in threads if t]
        thread_parts = [p for p in d["parts"] if p["type"] == "review_thread"]
        assert len(threads) == len(thread_parts), n
        cks = chunks(n)
        linked = 0
        for t, tp in zip(threads, thread_parts):
            n_threads += 1
            h, method = map_thread(t[0], hunks)
            how[method] += 1
            if h:
                linked += 1
                hc = {c["chunk_id"] for c in cks if c["start"] < h["part"]["end"] and h["part"]["start"] < c["end"]}
                tc = {c["chunk_id"] for c in cks if c["start"] < tp["end"] and tp["start"] < c["end"]}
                if hc & tc:
                    same_chunk += 1
                else:
                    diff_chunk += 1
        if threads:
            n_prs_with_threads += 1
            n_prs_zero_links += linked == 0
        conv_n += sum(1 for p in d["parts"] if p["type"] == "conversation")
        for c in cks:
            types = sorted({p["type"] for p in d["parts"]
                            if p["start"] < c["end"] and c["start"] < p["end"]})
            chunk_mix["+".join(types)] += 1
        per_pr[n] = {"threads": len(threads), "linked": linked}
    res = {"n_prs": len(pool), "n_review_threads": n_threads,
           "thread_mapping": dict(how),
           "threads_linked": sum(v for k, v in how.items() if k in ("M1_header", "M2_line", "M3_content")),
           "prs_with_threads": n_prs_with_threads,
           "prs_with_threads_but_zero_links": n_prs_zero_links,
           "prs_without_any_review_thread": len(pool) - n_prs_with_threads,
           "linked_thread_and_hunk_in_same_fixed_chunk": same_chunk,
           "linked_thread_and_hunk_in_different_chunks": diff_chunk,
           "conversation_comments": conv_n,
           "conversation_comment_anchor_fields": "none (id, user, body, created_at only)",
           "fixed_chunk_part_mix_top": chunk_mix.most_common(15),
           "n_chunks": sum(chunk_mix.values())}
    with open("results/link_inspection.json", "w", encoding="utf-8") as f:
        json.dump(res | {"per_pr": per_pr}, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
