"""Correctness judging material for the test arms (answered answerable rows only).

    python build_judging.py
      judging/codex_pack.csv            all ANSWERED answerable rows, blind + shuffled (fixed seed)
      judging/codex_instructions.md     labelling rules for Codex
      judging/validation_sample.csv     ~80 rows for the human rater (Alyssa), stratified model x prompt x chunking
      judging/keys/judging_key.json     blind_id -> file, id, condition, model  (don't open)

Blinding: no model, arm, prompt or chunk ids (citation markers removed). Shuffle and sample
order use SHA-256 of the row key (fixed rule, reproducible). The validation sample is a subset
of the Codex pack with the same blind ids, so the two label sets can be compared.
"""
import csv
import hashlib
import json
import os
import re

from common import read_jsonl
from score import auto

FILES = ["results/gen_test_arms_4b-instruct.jsonl", "results/gen_test_arms_8b.jsonl"]
CITE = re.compile(r"\s*\[(PR\d+-c\d+)(\]\s*\[PR\d+-c\d+)*\]")
PER_STRATUM = 10
ARM_CHUNKING = {"pack-fixed": "fixed", "pack-struct": "structural"}


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    rows = []
    for path in FILES:
        for r in read_jsonl(path):
            q = qs[r["id"]]
            if r["type"] != "answerable" or q["split"] != "test":
                continue
            a = auto(r, q)
            if a["abstained"] or a["empty_answer"]:
                continue
            ctx, pk = r["condition"].split(":")
            rows.append({"key": f"{path}|{r['id']}|{r['condition']}", "file": path, "id": r["id"],
                         "condition": r["condition"], "model": r["model"],
                         "prompt": {"c": "v2", "c3": "v3"}[pk],
                         "chunking": ARM_CHUNKING["-".join(ctx.split("-")[:2])],
                         "question": q["question"], "gold_answer": q["answer"],
                         "gold_quotes": "\n---\n".join(q["quotes"]),
                         "model_answer": CITE.sub("", r["response"]).strip()})
    rows.sort(key=lambda x: h("judge:" + x["key"]))
    for i, x in enumerate(rows, 1):
        x["blind_id"] = f"J{i:04d}"
    os.makedirs("judging/keys", exist_ok=True)
    pub = ["blind_id", "question", "gold_answer", "gold_quotes", "model_answer", "label", "reason"]
    with open("judging/codex_pack.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=pub, extrasaction="ignore")
        w.writeheader()
        w.writerows([x | {"label": "", "reason": ""} for x in rows])
    with open("judging/keys/judging_key.json", "w", encoding="utf-8") as f:
        json.dump({x["blind_id"]: {k: x[k] for k in ("file", "id", "condition", "model")} for x in rows},
                  f, indent=1)
    # validation sample: fixed-rule stratified, model x prompt x chunking, PER_STRATUM each
    strata = {}
    for x in rows:
        strata.setdefault((x["model"], x["prompt"], x["chunking"]), []).append(x)
    sample = []
    for k in sorted(strata):
        sample += sorted(strata[k], key=lambda x: h("val:" + x["key"]))[:PER_STRATUM]
    sample.sort(key=lambda x: x["blind_id"])
    with open("judging/validation_sample.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=pub, extrasaction="ignore")
        w.writeheader()
        w.writerows([x | {"label": "", "reason": ""} for x in sample])
    with open("judging/codex_instructions.md", "w", encoding="utf-8") as f:
        f.write(INSTRUCTIONS)
    print(json.dumps({"answered_rows": len(rows), "strata": {"|".join(k): len(v) for k, v in strata.items()},
                      "validation_sample": len(sample)}, indent=1))


INSTRUCTIONS = """# Judging instructions (Exp 2, test arms)

File: `codex_pack.csv`. Each row is one model answer to a "why" question about a Django pull
request. You see the question, the gold answer, the gold quotes (verbatim PR text that states the
reason) and the model answer. Model, prompt and retrieval condition are hidden; citation ids were
removed.

Fill `label` with exactly one of: correct / partial / wrong, and give a one-line `reason`.
- correct: states the reason the gold quotes support (paraphrase is fine; extra details are fine
  only if they do not contradict the PR).
- partial: gets part of the reason, or is in the right area but misses the key point (e.g. for
  the cookie-prefix question, saying such cookies are "HTTPS-only" without saying browsers ignore
  the Set-Cookie header counts as partial).
- wrong: a different or invented reason, or contradicts the gold.
Judge against the gold quotes, not against general knowledge. Do not change any other column.
"""

if __name__ == "__main__":
    main()
