"""Build Exp 2 dev set 2 (relation-factor tuning only) -> questions_dev2.jsonl + review_dev2.csv.

    python build_dev2.py

Same rules as build_questions.py: spans are cut from the PR document by anchors inside the
stated part (verbatim by construction; anchors not found -> row dropped and reported), copied-text
check (>= 6 consecutive shared words flagged), supporting chunks per chunking (chunks that fully
contain any span). Extra checks: no dev PR shares a Trac ticket with a test-set question PR or a
removed-case exclusion, and quote_elsewhere (other pool PRs containing a quote verbatim).
review_dev2.csv is written only if it does not exist yet (never overwrites James's marks).
"""
import csv
import json
import os

from build_questions import anchor_span, chunk_sets, longest_shared_run, COPY_N
from common import external_ticket, doc, pool_numbers, same_ticket_prs, read_jsonl, write_jsonl, git_commit
from link_map import chunks_for
from questions_dev2_src import ANSWERABLE, NO_REASON

NOT_FOUND = "Not found in the provided PRs"
CHUNKINGS = ("fixed_s512_o77", "struct_c256")


def main():
    pool = pool_numbers()
    test = read_jsonl("questions.jsonl")
    test_prs = {q["pr_number"] for q in test} | {p for q in test for p in q["exclude_prs"]}
    rows, dropped = [], []
    for e in ANSWERABLE:
        d = doc(e["pr"])
        spans, parts = [], []
        for part, a, b in e["spans"]:
            sp = anchor_span(d, part, a, b)
            if sp is None:
                dropped.append({"pr": e["pr"], "reason": f"anchors not found: {(part, a, b)}"})
                break
            spans.append(sp)
            parts.append(part)
        else:
            run = longest_shared_run(e["q"], d["text"])
            r = {"id": f"d{e['pr']}", "pr_number": e["pr"], "question": e["q"], "answer": e["a"],
                 "quotes": [d["text"][a:b] for a, b in spans], "spans": [list(s) for s in spans],
                 "source_parts": parts, "source_part": e["part"], "type": "answerable",
                 "exclude_prs": [], "split": "dev2", "copy_max_run": run, "copy_flag": run >= COPY_N}
            for ch in CHUNKINGS:
                full, over = chunk_sets(chunks_for(ch, e["pr"]), spans)
                r[f"gold_chunks_{ch}"], r[f"overlap_chunks_{ch}"] = full, over
            rows.append(r)
    for e in NO_REASON:
        run = longest_shared_run(e["q"], doc(e["pr"])["text"])
        rows.append({"id": f"dnr{e['pr']}", "pr_number": e["pr"], "question": e["q"],
                     "answer": NOT_FOUND, "quotes": [], "spans": [], "source_parts": [],
                     "source_part": None, "type": "no_reason", "exclude_prs": [],
                     "split": "dev2", "copy_max_run": run, "copy_flag": run >= COPY_N,
                     "note": e.get("note", "")} | external_ticket(e["pr"]))
    texts = {m: doc(m)["text"] for m in pool}
    for r in rows:
        r["same_ticket_as_test"] = [m for m in same_ticket_prs(r["pr_number"], pool) if m in test_prs]
        r["quote_elsewhere"] = sorted(m for m, t in texts.items()
                                      if m != r["pr_number"] and any(q in t for q in r["quotes"]))
    write_jsonl("questions_dev2.jsonl", rows)

    if not os.path.exists("review_dev2.csv"):
        with open("review_dev2.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id", "type", "pr_number", "pr_url", "question", "gold_answer",
                        "quotes (all spans)", "source_parts", "copy_max_run", "copy_flag",
                        "what_to_check", "decision (keep/fix/drop)", "reviewer_notes"])
            for r in rows:
                check = ("Read the WHOLE PR incl. diff; keep only if the reason is stated nowhere."
                         if r["type"] == "no_reason" else
                         "Unambiguous question? Do the quotes support every claim in the gold? Gold right?")
                w.writerow([r["id"], r["type"], r["pr_number"],
                            f"https://github.com/django/django/pull/{r['pr_number']}",
                            r["question"], r["answer"], "\n---\n".join(r["quotes"]),
                            " ".join(r["source_parts"]), r["copy_max_run"], r["copy_flag"],
                            check, "", ""])
    rep = {"git_commit": git_commit(),
           "counts": {t: sum(r["type"] == t for r in rows) for t in ("answerable", "no_reason")},
           "dropped": dropped,
           "copy_flagged": [(r["id"], r["copy_max_run"]) for r in rows if r["copy_flag"]],
           "source_part": {p: sum(r["source_part"] == p for r in rows if r["type"] == "answerable")
                           for p in ("description", "review_thread", "comment", "commit")},
           "multi_span": {r["id"]: len(r["spans"]) for r in rows if len(r["spans"]) > 1},
           "no_supporting_chunk": {ch: [r["id"] for r in rows if r["type"] == "answerable"
                                        and not r[f"gold_chunks_{ch}"]] for ch in CHUNKINGS},
           "same_ticket_as_test": {r["id"]: r["same_ticket_as_test"] for r in rows
                                   if r["same_ticket_as_test"]},
           "quote_elsewhere": {r["id"]: r["quote_elsewhere"] for r in rows if r["quote_elsewhere"]}}
    with open("build_dev2_report.json", "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
