"""Tests for the scaled Exp 2, fixed before any result (rule: tuning_rule_exp2_scale.md).

  python exp2_scale_stats.py second-rater           James's fixed 20 rows, blank, from the correctness sheet
  python exp2_scale_stats.py check SHEET.csv        rejects a sheet with a missing or invalid label
  python exp2_scale_stats.py stats                  needs final labels, committed; reads keys/ itself

Exact McNemar, F0 vs C1, two-sided, one Holm family of 3: strict correct (primary), answered, unanswerable
answered. Lenient correct (correct + partial) is a sensitivity with unadjusted p. A question that was not
answered counts as not correct. Labels are provisional, James + Codex, not Alyssa's as the rule says: see
HANDOVER "Labelling state". Re-run on her labels when they exist.
"""
import csv
import hashlib
import json
import os
import subprocess
import sys
from math import comb

import exp2_gitlab_scale as E

LABELS = ("correct", "partial", "wrong")
FINAL = "correctness_sheet.csv"
SECOND = "correctness_sheet_james.csv"
CHECK = "correctness_sheet_codex.csv"  # Codex on James's 20 rows, before any were resolved
ARM_X, ARM_Y = "F0", "C1"


def mcnemar(b, c):
    n = b + c
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n) if n else 1.0


def holm(ps):
    order, out, top = sorted(range(len(ps)), key=lambda i: ps[i]), [0] * len(ps), 0
    for rank, i in enumerate(order):
        top = max(top, min(1, ps[i] * (len(ps) - rank)))
        out[i] = top
    return out


def kappa(x, y):
    n, cats = len(x), set(x) | set(y)
    po = sum(a == b for a, b in zip(x, y)) / n
    pe = sum(x.count(c) * y.count(c) for c in cats) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def read_sheet(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def bad_labels(rows):
    return [(r["blind_id"], r["label"]) for r in rows if (r["label"] or "").strip().lower() not in LABELS]


def second_rater():
    rows = read_sheet(os.path.join(E.OUT, "correctness_sheet.csv"))
    pick = sorted(rows, key=lambda r: hashlib.sha256(f"42:{r['blind_id']}".encode()).hexdigest())[:20]
    path = os.path.join(E.OUT, SECOND)
    if os.path.exists(path):
        raise SystemExit(f"{path} exists: not overwritten")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(pick)
    print(f"{len(pick)} rows -> {path}")


def check(path):
    rows = read_sheet(path)
    bad = bad_labels(rows)
    print(f"{path}: {len(rows)} rows, {len(bad)} invalid {bad}")
    return not bad


def clean_commit():
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise SystemExit("Uncommitted changes: commit the final labels before running")
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()


def outcomes(qs, gens, labels):
    """{outcome: {question id: {arm: True/False}}} for the two arms."""
    res = {"strict_correct": {}, "answered": {}, "unanswerable_answered": {}, "lenient_correct": {}}
    for arm in (ARM_X, ARM_Y):
        for r in gens[arm]:
            x = E.auto(r, qs[r["id"]], E.ARMS[arm][0])
            said = not x["abstained"] and not x["empty_answer"]
            if r["type"] != "answerable":
                res["unanswerable_answered"].setdefault(r["id"], {})[arm] = said
                continue
            lab = labels.get((arm, r["id"]))
            if said and lab is None:
                raise SystemExit(f"{arm} {r['id']}: answered but has no label")
            res["answered"].setdefault(r["id"], {})[arm] = said
            res["strict_correct"].setdefault(r["id"], {})[arm] = said and lab == "correct"
            res["lenient_correct"].setdefault(r["id"], {})[arm] = said and lab in ("correct", "partial")
    return res


def test_rows(res):
    rows = []
    for name, per_q in res.items():
        assert all(len(v) == 2 for v in per_q.values()), name
        b = sum(v[ARM_X] and not v[ARM_Y] for v in per_q.values())
        c = sum(v[ARM_Y] and not v[ARM_X] for v in per_q.values())
        rows.append({"outcome": name, "n": len(per_q), "F0": sum(v[ARM_X] for v in per_q.values()),
                     "C1": sum(v[ARM_Y] for v in per_q.values()), "only_F0": b, "only_C1": c, "p": mcnemar(b, c)})
    fam = [r for r in rows if r["outcome"] != "lenient_correct"]
    for r, h in zip(fam, holm([r["p"] for r in fam])):
        r["holm"] = h
        r["family"] = "primary" if r["outcome"] == "strict_correct" else "same Holm family"
    for r in rows:
        if r["outcome"] == "lenient_correct":
            r["holm"], r["family"] = "", "sensitivity, unadjusted"
    return rows


def stats():
    commit = clean_commit()
    final = read_sheet(os.path.join(E.OUT, FINAL))
    second = read_sheet(os.path.join(E.OUT, SECOND))
    if bad_labels(final) or bad_labels(second):
        raise SystemExit(f"invalid labels: {bad_labels(final)} {bad_labels(second)}")
    with open(os.path.join(E.OUT, "keys", "sheet_key.json"), encoding="utf-8") as f:
        key = json.load(f)
    qs = {q["id"]: q for q in E.read_jsonl(E.QUESTIONS)}
    labels = {(key[r["blind_id"]]["arm"], key[r["blind_id"]]["id"]): r["label"].strip().lower() for r in final}
    rows = test_rows(outcomes(qs, E._gens([ARM_X, ARM_Y]), labels))
    # FINAL already holds James's labels on these rows, so compare the two original sheets instead
    byid = {r["blind_id"]: r["label"].strip().lower() for r in read_sheet(os.path.join(E.OUT, CHECK))}
    a, b = [byid[r["blind_id"]] for r in second], [r["label"].strip().lower() for r in second]
    for r in rows:
        r["git_commit"] = commit
        print(r)
    print(f"James vs Codex on {len(a)} rows, before resolving: {sum(x == y for x, y in zip(a, b))} equal, "
          f"kappa {kappa(a, b):.3f}")
    with open(os.path.join(E.OUT, "stats.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "second-rater":
        second_rater()
    elif cmd == "check":
        sys.exit(0 if check(sys.argv[2]) else 1)
    elif cmd == "stats":
        stats()
    else:
        sys.exit(__doc__)
