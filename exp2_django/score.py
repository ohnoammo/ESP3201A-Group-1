"""Score a generation results file.

    python score.py results/gen_pilot_4b.jsonl [--judgements judgements/pilot_4b_claude.jsonl]
                    [--rerun other_run.jsonl] [--out results/summary_pilot_4b.csv]

Automatic (no judge needed):
  abstained_exact  response is exactly "Not found in the provided PRs" (trailing '.' allowed)
  abstained_any    contains that sentence, or a common refusal phrase ("not stated", "does not
                   mention", ...) - used for conditions (a)/(b), which were not told the sentence
  abstained        strict (test arms, 23 Oct): after removing citation ids/brackets and
                   whitespace, starts with that sentence (case-insensitive) and nothing with a
                   word character follows it
  hedged           contains that sentence and also other content (so not "abstained"); still
                   counted as answered (stats_arms.py --hedged-as-abstained for sensitivity)
  citations        ids like PR1234-c5; valid = shown in the context; gold = the chunk(s) that
                   overlap the answer quote's span
  cited_correctly  >= 1 citation, all citations valid, and >= 1 gold chunk cited
  overlap_cited    = cited_correctly (gold = chunks overlapping a gold span; the test-arm name
                   since 23 Oct, replacing "right-chunk-cited")
  contain_cited    same rule with gold = chunks that fully contain a gold span
                   (gold_chunks_<chunking>); None where that chunking has no such chunk (q14748
                   structural)
  empty_answer     nothing left once citation ids are removed (e.g. a bare "[PR9540-c0]");
                   counted as neither answered nor cited correctly
Judged (optional file): correct / partial / incorrect (answerable), abstained / fabricated /
  non_answer (no_reason, removed).
"""
import argparse
import csv
import re
from collections import defaultdict

from common import read_jsonl
from run_generation import short_id

NOT_FOUND = "not found in the provided prs"
REFUSAL = re.compile(r"not found in the provided prs|(does|do|did) not (state|mention|say|specify|"
                     r"explain|provide|include)|(is|are|was|were)n'?t? (stated|mentioned|"
                     r"specified|explained|provided)|no (information|mention|reason|explanation)"
                     r"|cannot (be )?determine", re.I)
CITE = re.compile(r"PR(\d+)-c(\d+)")


def abstained_strict(resp):
    t = re.sub(r"\[[\s,;]*\]", "", CITE.sub("", resp)).strip()
    return t.lower().startswith(NOT_FOUND) and not re.search(r"\w", t[len(NOT_FOUND):])


def hedged(resp):
    t = re.sub(r"\[[\s,;]*\]", "", CITE.sub("", resp)).strip()
    return NOT_FOUND in t.lower() and bool(re.search(r"\w", t.lower().replace(NOT_FOUND, "")))


def auto(rec, q):
    resp = rec["response"].strip()
    norm = resp.lower().strip().strip('"').rstrip(".").strip()
    cites = [f"PR{a}-c{b}" for a, b in CITE.findall(resp)]
    shown = set(rec["context_short_ids"])
    ch = (rec.get("pack") or {}).get("chunking")
    gold = {short_id(c) for c in (q.get(f"overlap_chunks_{ch}") if ch and f"overlap_chunks_{ch}" in q
                                  else q.get("overlap_chunks")) or []}
    valid = [c for c in cites if c in shown]
    empty = not re.search(r"\w", CITE.sub("", resp).replace("[", "").replace("]", ""))
    contain = {short_id(c) for c in q.get(f"gold_chunks_{ch}") or []} if ch else set()
    ok = (not empty) and bool(cites) and len(valid) == len(cites)
    return {"overlap_cited": ok and any(c in gold for c in cites),
            "contain_cited": (ok and any(c in contain for c in cites)) if contain else None,
            "empty_answer": empty, "abstained_exact": norm == NOT_FOUND,
            "abstained_sentence": NOT_FOUND in resp.lower(),
            "abstained_any": bool(REFUSAL.search(resp)),
            "abstained": abstained_strict(resp),
            "hedged": hedged(resp),
            "n_cites": len(cites), "n_valid_cites": len(valid),
            "n_gold_cites": sum(c in gold for c in cites),
            "cited_correctly": (not empty) and bool(cites) and len(valid) == len(cites)
                               and any(c in gold for c in cites)}


def load_judgements(path):
    if not path:
        return {}
    rows = read_jsonl(path)
    return {(r["id"], r["condition"]): r["label"] for r in rows if "label" in r}


def summarise(recs, qs, judg, retrieval_hit=None):
    """Rows per (condition, type); with retrieval_hit ({id: bool}) also per retrieval hit/miss
    for answerable questions in the retrieved condition."""
    by = defaultdict(list)
    for r in recs:
        x = r | auto(r, qs[r["id"]]) | {"label": judg.get((r["id"], r["condition"]))}
        by[(r["condition"], r["type"], "")].append(x)
        if retrieval_hit and r["context"] == "retrieved" and r["type"] == "answerable":
            by[(r["condition"], r["type"],
                "retrieval_hit" if retrieval_hit[r["id"]] else "retrieval_miss")].append(x)
    out = []
    for (cond, typ, sub), rs in sorted(by.items()):
        n = len(rs)
        row = {"condition": cond, "type": typ, "subset": sub, "n": n,
               "answered": sum(not x["abstained_any"] and not x["empty_answer"] for x in rs),
               "empty_answer": sum(x["empty_answer"] for x in rs),
               "abstained_exact": sum(x["abstained_exact"] for x in rs),
               "abstained_sentence": sum(x["abstained_sentence"] for x in rs),
               "abstained_any": sum(x["abstained_any"] for x in rs),
               "any_citation": sum(x["n_cites"] > 0 for x in rs),
               "cited_correctly": sum(x["cited_correctly"] for x in rs),
               "cite_precision": (sum(x["n_gold_cites"] for x in rs)
                                  / max(1, sum(x["n_cites"] for x in rs))),
               "invalid_cites": sum(x["n_cites"] - x["n_valid_cites"] for x in rs),
               "possibly_truncated": sum(x["possibly_truncated"] for x in rs)}
        labels = [x["label"] for x in rs if x["label"]]
        for lab in ("correct", "partial", "incorrect", "abstained", "fabricated", "non_answer"):
            if any(x == lab for x in labels) or (labels and lab in (
                    ("correct", "partial", "incorrect") if typ == "answerable"
                    else ("abstained", "fabricated", "non_answer"))):
                row[f"judged_{lab}"] = sum(x == lab for x in labels)
        row["n_judged"] = len(labels)
        out.append(row)
    return out


def rerun_agreement(a, b, qs):
    A = {(r["id"], r["condition"]): r for r in a}
    B = {(r["id"], r["condition"]): r for r in b}
    keys = sorted(set(A) & set(B))
    same_text = sum(A[k]["response"] == B[k]["response"] for k in keys)
    flips = []
    for k in keys:
        x, y = auto(A[k], qs[k[0]]), auto(B[k], qs[k[0]])
        for m in ("abstained_exact", "abstained_any", "cited_correctly"):
            if x[m] != y[m]:
                flips.append((k, m, x[m], y[m]))
    return {"n": len(keys), "identical_text": same_text, "outcome_flips": flips}


def main(a):
    recs = read_jsonl(a.results)
    qs = {q["id"]: q for f in a.questions.split(",") for q in read_jsonl(f)}
    hit = None
    if a.retrieved:
        hit = {r["id"]: r.get("chunk_hit") for r in read_jsonl(a.retrieved)}
    rows = summarise(recs, qs, load_judgements(a.judgements), hit)
    meta = {k: sorted({str(r[k]) for r in recs})
            for k in ("model", "model_digest", "git_commit", "prompt_sha1")}
    print("results:", a.results, meta)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    print(" | ".join(keys))
    for r in rows:
        print(" | ".join(f"{r.get(k):.2f}" if isinstance(r.get(k), float) else str(r.get(k, ""))
                         for k in keys))
    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys + ["model", "git_commit"])
            w.writeheader()
            for r in rows:
                w.writerow(r | {"model": ";".join(meta["model"]),
                                "git_commit": ";".join(meta["git_commit"])})
    if a.rerun:
        ag = rerun_agreement(recs, read_jsonl(a.rerun), qs)
        print(f"\nRerun: {ag['identical_text']}/{ag['n']} identical responses; "
              f"{len(ag['outcome_flips'])} automatic-outcome flips")
        for f in ag["outcome_flips"]:
            print("  ", f)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--questions", default="questions.jsonl")
    ap.add_argument("--judgements", default=None)
    ap.add_argument("--rerun", default=None)
    ap.add_argument("--retrieved", default=None,
                    help="results/retrieved_top5.jsonl: adds retrieval hit/miss subsets")
    ap.add_argument("--out", default=None)
    main(ap.parse_args())
