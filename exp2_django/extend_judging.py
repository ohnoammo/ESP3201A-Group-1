"""Bring the Codex pack in line with the current answered set without reshuffling it.

    python extend_judging.py      # updates judging/codex_pack.csv and judging/keys/judging_key.json

After a scoring change (strict abstention, 23 Oct): answered answerable test rows not yet in the
key are appended with new ids J<n+1>... in SHA-256 order of their row key (same hash rule as
build_judging.py); rows in the key that are no longer answered are removed from the pack, the key
and the validation sample. Existing rows, ids, order and any labels are kept.
Arm W-F (tuning_rule_wholepr.md, 1 Nov): answered answerable rows of results/gen_test_arm_W_*.jsonl
(score_w.auto_w) are appended the same way; W citations ([PR<n>], [PR<n>-c<k>]) are stripped.
Arm H0 (tuning_rule_hybrid.md, 5 Nov): answered answerable rows of results/gen_test_arm_H0_*.jsonl
(score.auto) are appended the same way, from J0793; citations stripped as for the frozen arms.
"""
import csv
import json
import re

from build_judging import CITE, FILES, h
from common import read_jsonl
from score import auto
from score_w import FILES_W, auto_w

PACK, KEY, VAL = "judging/codex_pack.csv", "judging/keys/judging_key.json", "judging/validation_sample.csv"
WCITE = re.compile(r"\s*\[\s*PR\d+(?:-c\d+)?(?:\s*[,;]\s*PR\d+(?:-c\d+)?)*\s*\]")
FILES_H0 = ["results/gen_test_arm_H0_4b-instruct.jsonl", "results/gen_test_arm_H0_8b.jsonl"]


def h0_drift_ids():
    """tuning_rule_hybrid.md: the first 20 of J0001-J0659 in SHA-256 order of h0-drift:<blind_id>."""
    return sorted((f"J{i:04d}" for i in range(1, 660)), key=lambda b: h(f"h0-drift:{b}"))[:20]


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    want = {}
    for path in FILES + list(FILES_W.values()) + FILES_H0:
        score = auto_w if path in FILES_W.values() else auto
        for r in read_jsonl(path):
            q = qs[r["id"]]
            if r["type"] != "answerable" or q["split"] != "test":
                continue
            a = score(r, q)
            if not (a["abstained"] or a["empty_answer"]):
                want[(path, r["id"], r["condition"])] = (r, q)
    with open(KEY, encoding="utf-8") as f:
        key = json.load(f)
    have = {(v["file"], v["id"], v["condition"]): b for b, v in key.items()}
    removed = sorted(b for k, b in have.items() if k not in want)
    new = sorted((k for k in want if k not in have), key=lambda k: h("judge:" + "|".join(k)))
    fields, pack = read_csv(PACK)
    pack = [x for x in pack if x["blind_id"] not in removed]
    for b in removed:
        del key[b]
    n = max(int(b[1:]) for b in key)
    added = []
    for k in new:
        r, q = want[k]
        n += 1
        b = f"J{n:04d}"
        key[b] = {"file": k[0], "id": k[1], "condition": k[2], "model": r["model"]}
        pack.append({"blind_id": b, "question": q["question"], "gold_answer": q["answer"],
                     "gold_quotes": "\n---\n".join(q["quotes"]),
                     "model_answer": (WCITE if k[0] in FILES_W.values() else CITE).sub("", r["response"]).strip(),
                     "label": "", "reason": ""})
        added.append(b)
    write_csv(PACK, fields, pack)
    with open(KEY, "w", encoding="utf-8") as f:
        json.dump(key, f, indent=1)
    vfields, val = read_csv(VAL)
    val_removed = [x["blind_id"] for x in val if x["blind_id"] in removed]
    if val_removed:
        write_csv(VAL, vfields, [x for x in val if x["blind_id"] not in removed])
    assert len(pack) == len(key) == len(want)
    print(json.dumps({"pack_rows": len(pack), "added": added, "removed": removed,
                      "removed_from_validation_sample": val_removed}))


if __name__ == "__main__":
    main()
