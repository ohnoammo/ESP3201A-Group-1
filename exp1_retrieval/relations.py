"""Relation factor: link chunks of the same PR, then fill a fixed token budget.

The search itself is unchanged. AFTER the search, every retrieved chunk may bring in chunks
it is linked to; each linked chunk competes for the same fixed token budget as everything
else, so a method can never win just by handing over more text.

Links (all inside ONE PR; never across PRs):
  kind "code" (Experiment 1: a link may only add CODE)
    structural chunks:
      PR description / commit messages -> the PR's hunks (in document order)
      review thread                    -> the hunk it comments on (file + line match;
                                          if the line can't be matched, that file's hunks)
      hunk                             -> the PR's other hunks (same file, nearest first;
                                          then other files)
    fixed chunks:
      chunk                            -> the chunks just before and after it
  kind "context" (Experiment 2 only: adds EXPLANATIONS; off in Experiment 1)
      hunk                             -> review threads on it + the PR description
  Excluded comments (Exp 2 leakage rule) must be removed from the PR documents before
  chunking; then they are not chunks and can never be linked.

Scoring (relation factor alpha):
  a retrieved chunk at rank r scores 1 / r                 (rank-based, so the same alpha
                                                            works for BM25, dense, hybrid)
  a chunk linked from a chunk at rank r scores alpha / r
  So alpha = 0.5 puts a link from rank 1 level with rank 2, alpha = 0.25 with rank 4.
  (1/(60+r), the RRF formula, was tried first on dev: it is so flat that alpha 0.25 and 0.5
  never beat any chunk inside the budget, so only alpha near 1 did anything.)
  A chunk reached several ways keeps its best score. Everything is sorted by score (ties:
  better rank of the chunk that brought it in, then nearer link) and packed greedily into
  the token budget. alpha = 0 -> no links = the plain ranking packed into the same budget.
"""
from collections import defaultdict

from chunking import count_tokens

RRF_K = 0                      # score = alpha / (RRF_K + rank); 0 -> 1/rank
FAR = 1000                     # link distance offset for hunks in OTHER files


def _part_of(chunk, parts):
    """The PR part a structural chunk was cut from (its start lies inside the part)."""
    for p in parts:
        if p["start"] <= chunk["start"] < p["end"]:
            return p
    return None


def _thread_hunks(thread_part, hunks, hunk_part):
    """Hunks a review thread comments on: same file and the thread's line inside the hunk's
    new-file line range; if no line matches, all hunks of that file."""
    same_file = [h for h in hunks if h.get("file_path") == thread_part.get("file_path")]
    line = thread_part.get("line")
    if line is not None:
        hit = [h for h in same_file
               if (r := (hunk_part[h["chunk_id"]] or {}).get("new_lines")) and r[0] <= line <= r[1]]
        if hit:
            return hit
    return same_file


def build_links(chunks, docs, kinds=("code",)):
    """{chunk_id: [(linked_chunk_id, distance), ...]} for one chunk set.
    docs: {paper_id: PR document} (pr_document.build_document)."""
    by_pr = defaultdict(list)
    for c in chunks:
        by_pr[c["paper_id"]].append(c)
    links = defaultdict(list)
    for pid, cs in by_pr.items():
        cs.sort(key=lambda c: c["start"])
        if cs[0].get("chunk_type") == "fixed":                    # fixed: neighbours
            if "code" in kinds:
                for i, c in enumerate(cs):
                    links[c["chunk_id"]] += [(cs[j]["chunk_id"], 1)
                                             for j in (i - 1, i + 1) if 0 <= j < len(cs)]
            continue
        parts = docs[pid]["parts"]
        part = {c["chunk_id"]: _part_of(c, parts) for c in cs}
        hunks = [c for c in cs if c["chunk_type"] == "hunk"]
        pos = {h["chunk_id"]: i for i, h in enumerate(hunks)}
        descs = [c for c in cs if c["chunk_type"] == "title_description"]
        threads = [c for c in cs if c["chunk_type"] == "review_thread"]
        if "code" in kinds:
            for c in cs:
                cid, t = c["chunk_id"], c["chunk_type"]
                if t in ("title_description", "commits"):
                    links[cid] += [(h["chunk_id"], i) for i, h in enumerate(hunks)]
                elif t == "review_thread" and part[cid]:
                    links[cid] += [(h["chunk_id"], 0)
                                   for h in _thread_hunks(part[cid], hunks, part)]
                elif t == "hunk":
                    links[cid] += [(h["chunk_id"],
                                    abs(pos[h["chunk_id"]] - pos[cid])
                                    + (0 if h.get("file_path") == c.get("file_path") else FAR))
                                   for h in hunks if h["chunk_id"] != cid]
        if "context" in kinds:
            for th in threads:
                if part[th["chunk_id"]]:
                    for h in _thread_hunks(part[th["chunk_id"]], hunks, part):
                        links[h["chunk_id"]].append((th["chunk_id"], 0))
            for h in hunks:
                links[h["chunk_id"]] += [(d["chunk_id"], 1) for d in descs]
    return dict(links)


def expand_and_pack(ranked, alpha, links, chunk_by_id, budget_tokens, ntok, rrf_k=RRF_K):
    """ranked: the search result (best first). Returns the chunks that fill the token budget,
    each with "score" and "linked" (True if it got in only through a link)."""
    best = {}                                   # chunk_id -> (score, tiebreak, chunk, linked)

    def offer(cid, score, tie, chunk, linked):
        cur = best.get(cid)
        if cur is None or (score, [-x for x in tie]) > (cur[0], [-x for x in cur[1]]):
            best[cid] = (score, tie, chunk, linked)

    for r, c in enumerate(ranked, 1):
        offer(c["chunk_id"], 1.0 / (rrf_k + r), (r, 0), c, False)
    if alpha > 0:
        for r, c in enumerate(ranked, 1):
            for lid, dist in links.get(c["chunk_id"], ()):
                if lid in chunk_by_id:
                    offer(lid, alpha / (rrf_k + r), (r, dist), chunk_by_id[lid], True)
    order = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[1][1], kv[0]))
    packed, used = [], 0
    for cid, (score, _, chunk, linked) in order:
        n = ntok(cid, chunk)
        if used + n > budget_tokens:
            continue                            # doesn't fit; a smaller one may still fit
        packed.append(chunk | {"score": score, "linked": linked})
        used += n
        if used >= budget_tokens:
            break
    return packed


def token_counter():
    """Memoised token count per chunk id (same unit as chunk sizes: chunking.count_tokens)."""
    cache = {}

    def ntok(cid, chunk):
        if cid not in cache:
            cache[cid] = count_tokens(chunk["text"])
        return cache[cid]
    return ntok
