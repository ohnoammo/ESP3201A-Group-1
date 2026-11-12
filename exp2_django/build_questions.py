"""Tier 1, steps 2-4: build questions.jsonl and review_sheet.csv from questions_src.py.

    python build_questions.py

Checks (results in build_report.json):
  - quote must occur verbatim in build_document(pr)["text"] inside a part of the stated type;
    failures are DROPPED and listed;
  - copied-text check: longest run of consecutive words (lowercased [a-z0-9]+, as in Exp 1's
    shares_ngram) shared by the question and the PR text; >= COPY_N words -> flagged (kept);
  - gold chunks: fixed 512/77 chunk ids whose span fully contains the quote span
    (used later to separate retrieval misses from generation errors);
  - quote_elsewhere: other pool PRs whose text contains the quote verbatim (for "removed"
    cases these must all be in exclude_prs, otherwise the answer is still retrievable);
  - split: "dev" for the prompt dev set (pilot_ids.json), "test" for everything else.
"""
import csv
import hashlib
import json
import os
import re

from common import external_ticket, doc, chunks, same_ticket_prs, pool_numbers, write_jsonl, git_commit
from questions_src import ANSWERABLE, NO_REASON, REMOVED, EDITS, FLAGGED

COPY_N = 6
PART_TYPES = {"description": "title_description", "review_thread": "review_thread",
              "comment": "conversation", "commit": "commits"}
N_REVIEW_PRIORITY = 20
NOT_FOUND = "Not found in the provided PRs"


def words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def longest_shared_run(question, text, max_n=20):
    q, t = words(question), words(text)
    best = 0
    for n in range(1, max_n + 1):
        grams = {tuple(t[i:i + n]) for i in range(len(t) - n + 1)}
        if any(tuple(q[i:i + n]) in grams for i in range(len(q) - n + 1)):
            best = n
        else:
            break
    return best


def find_span(d, quote, part):
    ptype = PART_TYPES[part]
    start = d["text"].find(quote)
    while start != -1:
        end = start + len(quote)
        if any(p["type"] == ptype and p["start"] <= start and end <= p["end"] for p in d["parts"]):
            return start, end
        start = d["text"].find(quote, start + 1)
    return None


def anchor_span(d, part, start_anchor, end_anchor):
    """Span from start_anchor to the end of the next end_anchor, inside one part of `part`."""
    ptype, t = PART_TYPES[part], d["text"]
    s = t.find(start_anchor)
    while s != -1:
        e = t.find(end_anchor, s)
        if e != -1:
            e += len(end_anchor)
            if any(p["type"] == ptype and p["start"] <= s and e <= p["end"] for p in d["parts"]):
                return s, e
        s = t.find(start_anchor, s + 1)
    return None


def chunk_sets(cks, spans):
    """supporting = chunks that fully contain ANY span; overlap = chunks touching any span."""
    full = [c["chunk_id"] for c in cks if any(c["start"] <= a and b <= c["end"] for a, b in spans)]
    over = [c["chunk_id"] for c in cks if any(c["start"] < b and a < c["end"] for a, b in spans)]
    return full, over


def main():
    pool = pool_numbers()
    rows, dropped, report = [], [], {"git_commit": git_commit()}
    by_pr = {}
    for e in ANSWERABLE:
        d = doc(e["pr"])
        span = find_span(d, e["quote"], e["part"])
        if span is None:
            dropped.append({"pr": e["pr"], "reason": "quote not found verbatim in that part"})
            continue
        assert d["text"][span[0]:span[1]] == e["quote"]
        ed = EDITS.get(e["pr"], {})
        parts = [(e["part"], span)]
        if "widen" in ed:
            w = anchor_span(d, e["part"], *ed["widen"])
            if w is None or not (w[0] <= span[0] and span[1] <= w[1]):
                dropped.append({"pr": e["pr"], "reason": f"widen anchors failed {ed['widen']}"})
                continue
            parts = [(e["part"], w)]
        for part, a, b in ed.get("more", []):
            m = anchor_span(d, part, a, b)
            if m is None:
                dropped.append({"pr": e["pr"], "reason": f"extra span anchors failed {(part, a, b)}"})
                break
            parts.append((part, m))
        else:
            spans = [sp for _, sp in parts]
            run = longest_shared_run(e["q"], d["text"])
            cks = chunks(e["pr"])
            full, over = chunk_sets(cks, spans)
            quotes = [d["text"][a:b] for a, b in spans]
            row = {"id": f"q{e['pr']}", "pr_number": e["pr"], "question": e["q"],
                   "answer": ed.get("answer", e["a"]),
                   "quote": quotes[0], "span": list(spans[0]), "source_part": parts[0][0],
                   "quotes": quotes, "spans": [list(sp) for sp in spans],
                   "source_parts": [p for p, _ in parts],
                   "type": "answerable", "exclude_prs": [],
                   "gold_chunks": full, "overlap_chunks": over,
                   "copy_max_run": run, "copy_flag": run >= COPY_N,
                   "edit": ed.get("why", ""), "flag": FLAGGED.get(e["pr"], "")}
            from link_map import chunks_for
            for ch in ("fixed_s512_o77", "struct_c256"):       # per-chunking supporting sets
                full_c, over_c = chunk_sets(chunks_for(ch, e["pr"]), spans)
                row[f"gold_chunks_{ch}"], row[f"overlap_chunks_{ch}"] = full_c, over_c
            rows.append(row)
            by_pr[e["pr"]] = row
    for e in NO_REASON:
        d = doc(e["pr"])
        run = longest_shared_run(e["q"], d["text"])
        rows.append({"id": f"nr{e['pr']}", "pr_number": e["pr"], "question": e["q"],
                     "answer": NOT_FOUND, "quote": None, "span": None, "source_part": None,
                     "quotes": [], "spans": [], "source_parts": [],
                     "type": "no_reason", "exclude_prs": [], "gold_chunks": [],
                     "overlap_chunks": [], "copy_max_run": run, "copy_flag": run >= COPY_N,
                     "note": e.get("note", "")} | external_ticket(e["pr"]))
    for n in REMOVED:
        src = by_pr[n]
        excl = [n] + same_ticket_prs(n, pool)
        rows.append(src | {"id": f"rm{n}", "type": "removed", "answer": NOT_FOUND,
                           "gold_answer_if_present": src["answer"], "exclude_prs": excl})

    texts = {m: doc(m)["text"] for m in pool}
    with open("pilot_ids.json", encoding="utf-8") as f:
        dev_ids = set(json.load(f)["ids"])
    for r in rows:
        r["split"] = "dev" if r["id"] in dev_ids else "test"
        r["quote_elsewhere"] = sorted(m for m, t in texts.items()
                                      if m != r["pr_number"] and any(qt in t for qt in r["quotes"]))
        r["quote_elsewhere_not_excluded"] = [m for m in r["quote_elsewhere"]
                                             if m not in r["exclude_prs"]]
    write_jsonl("questions.jsonl", rows)

    # review sheet: a fixed SHA-256 order picks the ~20 to hand-check first
    order = sorted(rows, key=lambda r: hashlib.sha256(f"42:{r['id']}".encode()).hexdigest())
    prio = {r["id"] for r in order if r["type"] == "answerable"}
    prio = set(sorted(prio, key=lambda i: hashlib.sha256(f"42:{i}".encode()).hexdigest())
               [:N_REVIEW_PRIORITY - len(NO_REASON)]) | {r["id"] for r in rows
                                                          if r["type"] == "no_reason"}
    if os.path.exists("review_sheet.csv"):           # never overwrite James's marking
        print("review_sheet.csv exists: not rewritten (James's v1 marks live there)")
        sheet_rows = []
    else:
        sheet_rows = rows
    with open("review_sheet.csv" if sheet_rows else os.devnull, "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["priority", "id", "type", "pr_number", "pr_url", "question", "answer",
                    "quote", "source_part", "copy_max_run", "copy_flag", "exclude_prs",
                    "decision (keep/fix/drop)", "reviewer_notes"])
        for r in sorted(sheet_rows, key=lambda r: (r["id"] not in prio, r["type"], r["id"])):
            w.writerow(["1" if r["id"] in prio else "", r["id"], r["type"], r["pr_number"],
                        f"https://github.com/django/django/pull/{r['pr_number']}",
                        r["question"], r["answer"], r["quote"] or "", r["source_part"] or "",
                        r["copy_max_run"], r["copy_flag"], " ".join(map(str, r["exclude_prs"])),
                        "", r.get("note", "")])

    types = {}
    for r in rows:
        types[r["type"]] = types.get(r["type"], 0) + 1
    splits = {}
    for r in rows:
        splits[f"{r['split']}/{r['type']}"] = splits.get(f"{r['split']}/{r['type']}", 0) + 1
    report |= {"counts": types, "splits": splits, "dropped": dropped,
               "quote_elsewhere": {r["id"]: r["quote_elsewhere"] for r in rows
                                   if r["quote_elsewhere"]},
               "removed_answer_still_retrievable": {
                   r["id"]: r["quote_elsewhere_not_excluded"] for r in rows
                   if r["type"] == "removed" and r["quote_elsewhere_not_excluded"]},
               "copy_flagged": [(r["id"], r["copy_max_run"]) for r in rows if r["copy_flag"]],
               "copy_run_distribution": sorted(r["copy_max_run"] for r in rows
                                               if r["type"] != "removed"),
               "no_gold_chunk": [r["id"] for r in rows
                                 if r["type"] == "answerable" and not r["gold_chunks"]],
               "source_parts": {p: sum(r["source_part"] == p for r in rows
                                       if r["type"] == "answerable") for p in PART_TYPES},
               "removed_excludes": {r["id"]: r["exclude_prs"] for r in rows
                                    if r["type"] == "removed"},
               "review_priority": sorted(prio)}
    with open("build_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "review_priority"}, indent=1))


if __name__ == "__main__":
    main()
