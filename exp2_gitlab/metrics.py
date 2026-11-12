"""Experiment 1 metrics (SWE-bench / PRs).

MAIN, PR level (pr_level): the chunk ranking is collapsed to a PR ranking (first occurrence =
the PR's best chunk, MaxP-style). Hit@5 = gold PR among the top 5 PRs; MRR@5 = 1/rank of the
gold PR if it is in the top 5, else 0 (as in issue-commit linking work, Huang et al. 2026).

SECONDARY, top-5 chunks = what an LLM would receive (score_question_multidoc). Unchanged
span logic from the QASPER version, with LINES as the scoring units instead of sentences:
- a line counts as RETRIEVED if >= 50% of its characters fall inside the retrieved chunks;
- a line counts as EVIDENCE if >= 50% of it lies inside a gold evidence range (the fixing
  PR's changed lines, pr_document.evidence_ranges).
Everything uses character spans in the PR text, so fixed and structural chunks are scored
identically.
"""


def _covered(span, ranges, min_frac=0.5):
    s, e = span
    length = max(1, e - s)
    overlap = sum(max(0, min(e, re_) - max(s, rs)) for rs, re_ in ranges)
    return overlap / length >= min_frac


def evidence_sentences(sent_spans, evidence_ranges):
    return {i for i, sp in enumerate(sent_spans) if _covered(sp, evidence_ranges)}


def score_question(sent_spans, evidence_ranges, retrieved, k=5):
    """Single-document version (QASPER): every chunk and all evidence are in one paper.
    retrieved: ranked list of chunks with 'start'/'end'. Returns a metrics dict."""
    top = [c | {"paper_id": 0} for c in retrieved[:k]]
    return score_question_multidoc({0: sent_spans}, {0: evidence_ranges}, top, k)


def score_question_multidoc(doc_sents, doc_evidence, retrieved, k=5):
    """Multi-document version (MultiHop-RAG); QASPER also goes through this.

    doc_sents:    {doc_id: [(start, end)] sentence spans}
    doc_evidence: {doc_id: [(start, end)] evidence ranges}  (only docs that hold evidence)
    retrieved:    ranked list of chunks with 'paper_id', 'start', 'end'
    Sentences are identified as (doc_id, sentence index).
    """
    gold = {(d, i) for d, ranges in doc_evidence.items()
            for i in evidence_sentences(doc_sents[d], ranges)}
    top = retrieved[:k]

    ret_by_doc = {}
    for c in top:
        ret_by_doc.setdefault(c["paper_id"], []).append((c["start"], c["end"]))
    got = {(d, i) for d, ranges in ret_by_doc.items()
           for i, sp in enumerate(doc_sents[d]) if _covered(sp, ranges)}

    hit_both = gold & got
    recall = len(hit_both) / len(gold) if gold else 0.0
    precision = len(hit_both) / len(got) if got else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    # Hit@k / MRR: rank of the first chunk that contains any evidence sentence
    rr = 0.0
    for rank, c in enumerate(top, start=1):
        d = c["paper_id"]
        if any(_covered(doc_sents[d][i], [(c["start"], c["end"])])
               for gd, i in gold if gd == d):
            rr = 1.0 / rank
            break

    # Multi-hop: an evidence document counts as found if any of its evidence
    # sentences was retrieved. all_docs = 1 only if EVERY evidence document was found.
    ev_docs = {d for d, _ in gold}
    found_docs = {d for d, _ in hit_both}

    # MAP@k (average precision; the mean is taken over questions by the caller).
    # Relevant items = evidence documents. Walking down the ranking, each time a chunk
    # brings in evidence from a document not yet found, add precision-at-that-rank.
    # Divide by ALL evidence documents, so missed ones count as 0.
    # With one evidence document (QASPER) this equals MRR.
    credited, ap = set(), 0.0
    for rank, c in enumerate(top, start=1):
        d = c["paper_id"]
        if d in ev_docs and d not in credited and any(
                _covered(doc_sents[d][i], [(c["start"], c["end"])])
                for gd, i in gold if gd == d):
            credited.add(d)
            ap += len(credited) / rank
    ap = ap / len(ev_docs) if ev_docs else 0.0

    return {"recall": recall, "precision": precision, "f1": f1,
            "hit": 1.0 if rr > 0 else 0.0, "mrr": rr, "map": ap,
            "all_docs": 1.0 if ev_docs and found_docs == ev_docs else 0.0}


def best_over_annotators(sent_spans, evidence_range_sets, retrieved, k=5):
    """QASPER has several annotators per question; keep the one with the best F1."""
    scores = [score_question(sent_spans, r, retrieved, k) for r in evidence_range_sets if r]
    return max(scores, key=lambda s: s["f1"]) if scores else None


# ---------- PR level (main metric) ----------
def collapse_to_prs(ranked_chunks, key="paper_id"):
    """Chunk ranking -> PR ranking: keep each PR's first (= best-ranked) chunk, in order.
    Retrieve a deep chunk list first (e.g. 100) so there are enough distinct PRs."""
    seen, prs = set(), []
    for c in ranked_chunks:
        if c[key] not in seen:
            seen.add(c[key])
            prs.append(c[key])
    return prs


def pr_level(ranked_chunks, gold_pr, k=5):
    """PR-level Hit@k and MRR@k (reciprocal rank only counts inside the top k PRs)."""
    prs = collapse_to_prs(ranked_chunks)[:k]
    rank = prs.index(gold_pr) + 1 if gold_pr in prs else None
    return {"pr_hit": 1.0 if rank else 0.0, "pr_mrr": 1.0 / rank if rank else 0.0,
            "pr_rank": rank}
