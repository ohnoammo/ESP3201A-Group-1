"""Make a blinded hand-check sheet from one or more generation results files.

    python blind.py results/gen_pilot_4b.jsonl --name pilot_v1

Writes
  blind/<name>_sheet.csv       shuffled rows; NO condition, model, prompt or file columns
  blind/keys/<name>_key.json   blind_id -> (results file, id, condition, model)   <- don't open
                               before labelling
Blinding notes (also written into the sheet's first row):
  - citation markers like [PR1234-c0] are removed from responses, because only the grounded
    prompt asks for them (citations are scored automatically by score.py instead);
  - an exact "Not found in the provided PRs" reply still reveals the grounded prompt; that is
    unavoidable and abstention is scored automatically anyway.
"""
import argparse
import csv
import json
import os
import random
import re
import secrets

from common import read_jsonl

CITE = re.compile(r"\s*\[(PR\d+-c\d+)(\]\s*\[PR\d+-c\d+)*\]")
LABELS = {"answerable": "correct / partial / incorrect",
          "no_reason": "abstained / fabricated / non_answer",
          "removed": "abstained / fabricated / non_answer",
          "removed_kept": "abstained / fabricated / non_answer"}


def main(a):
    qs = {q["id"]: q for q in read_jsonl("questions_retired.jsonl") + read_jsonl(a.questions)}
    recs = [(path, r) for path in a.results for r in read_jsonl(path)]
    seed = secrets.randbits(32)                     # recorded only in the key file
    random.Random(seed).shuffle(recs)
    os.makedirs("blind/keys", exist_ok=True)
    key, rows = {}, []
    for i, (path, r) in enumerate(recs, 1):
        bid = f"B{i:03d}"
        q = qs[r["id"]]
        key[bid] = {"file": path, "id": r["id"], "condition": r["condition"],
                    "model": r["model"]}
        rows.append({"blind_id": bid, "question_type": q["type"], "question": q["question"],
                     "gold_answer": q.get("gold_answer_if_present") or q["answer"],
                     "gold_quote": q["quote"] or "",
                     "pr_url": f"https://github.com/django/django/pull/{q['pr_number']}",
                     "response": CITE.sub("", r["response"]).strip(),
                     "allowed_labels": LABELS[q["type"]], "label": "", "notes": ""})
    sheet = f"blind/{a.name}_sheet.csv"
    with open(sheet, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(f"blind/keys/{a.name}_key.json", "w", encoding="utf-8") as f:
        json.dump({"shuffle_seed": seed, "results": a.results, "key": key}, f, indent=1)
    print(f"{len(rows)} rows -> {sheet} (key in blind/keys/{a.name}_key.json)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+")
    ap.add_argument("--questions", default="questions.jsonl")
    ap.add_argument("--name", required=True)
    main(ap.parse_args())
