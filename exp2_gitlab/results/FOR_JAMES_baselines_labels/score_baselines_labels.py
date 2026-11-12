"""Score the baselines blind correctness sheet (tuning_rule_baselines.md, Task 1 optional check).

Pre-registered: strict (correct) and lenient (correct + partial) correctness out of the 52 answerables per
arm (F0, P0, CB), exact McNemar F0 vs P0 and F0 vs CB, two-sided, UNADJUSTED. An answer that is not on the
sheet (the arm refused, strict scoring) counts as not correct.

Run from the repo root (the folder with results/ and exp2_gitlab_A2000/), after committing the labels file:
    python score_baselines_labels.py

Reads   results/baselines_blind_sheet_labels.csv   final labels (Clifton, 12 Nov 2026)
        results/baselines_blind_sheet_blank.csv    to check the labels file lines up with the sheet
        results/keys/baselines_blind_key.json      the blind key (opened here, after the labels were final)
        exp2_gitlab_A2000/questions.jsonl
Writes  results/baselines_correctness_per_arm.csv, _tests.csv, _rows.csv, results/baselines_correctness.md
        (refuses to overwrite them unless --force)
Standard library only. Optional: compares F0's new labels with the provisional ones via
exp2_gitlab_baselines.f0_labels (skipped with a note if that fails).
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
import sys

RES = "results"
LABELS = os.path.join(RES, "baselines_blind_sheet_labels.csv")
BLANK = os.path.join(RES, "baselines_blind_sheet_blank.csv")
KEY = os.path.join(RES, "keys", "baselines_blind_key.json")
QUESTIONS = os.path.join("exp2_gitlab_A2000", "questions.jsonl")
LABELS_SHA256 = "e33bb8a084f661e3c67c34299c44c46734c020546bde88ace108f1842c00b440"
ARMS = ("F0", "P0", "CB")
EXPECTED_ON_SHEET = {"F0": 43, "P0": 52, "CB": 52}      # RUN_LOG step 8
OUTS = {k: os.path.join(RES, f"baselines_correctness_{k}.csv") for k in ("per_arm", "tests", "rows")}
MD = os.path.join(RES, "baselines_correctness.md")


def mcnemar(b, c):
    """Exact two-sided McNemar (binomial on the discordant pairs)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm(s):
    return (s or "").replace("\r\n", "\n").strip()


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="overwrite earlier outputs of this script")
    a = ap.parse_args()
    for p in list(OUTS.values()) + [MD]:
        if os.path.exists(p) and not a.force:
            sys.exit(f"{p} exists: not overwritten (use --force to redo)")

    # 1. the labels file is the one Clifton approved and it lines up with the blank sheet
    sha = hashlib.sha256(open(LABELS, "rb").read()).hexdigest()
    if sha != LABELS_SHA256:
        sys.exit(f"labels file hash {sha[:12]}... differs from the approved one {LABELS_SHA256[:12]}...: stop")
    labels = read_csv(LABELS)
    blank = read_csv(BLANK)
    assert len(labels) == len(blank) == 147, (len(labels), len(blank))
    lab = {}
    for x, b in zip(labels, blank):
        assert x["blind_id"] == b["blind_id"], (x["blind_id"], b["blind_id"])
        assert norm(x["question"]) == norm(b["question"]), x["blind_id"]
        assert norm(x["model_answer"]) == norm(b["model_answer"]), x["blind_id"]
        assert x["label"].strip().lower() in ("correct", "partial", "wrong"), x["blind_id"]
        lab[x["blind_id"]] = x
    print(f"labels: 147 rows, hash ok, aligned with the blank sheet")

    # 2. unblind
    with open(KEY, encoding="utf-8") as f:
        key = json.load(f)
    with open(QUESTIONS, encoding="utf-8") as f:
        qs = {q["id"]: q for q in (json.loads(l) for l in f if l.strip())}
    assert set(key) == set(lab), "key and labels have different blind ids"
    ans_ids = sorted(i for i, q in qs.items() if q["type"] == "answerable")
    assert len(ans_ids) == 52, len(ans_ids)
    per = {arm: {} for arm in ARMS}            # arm -> {qid: blind_id}
    for bid, who in key.items():
        for w in who:
            q = qs[w["id"]]
            assert q["type"] == "answerable", (bid, w)
            assert norm(q["question"]) == norm(lab[bid]["question"]), (bid, w)
            assert w["id"] not in per[w["arm"]], ("two rows for one arm and question", bid, w)
            per[w["arm"]][w["id"]] = bid
    for arm in ARMS:
        n = len(per[arm])
        flag = "" if n == EXPECTED_ON_SHEET[arm] else f"   <-- expected {EXPECTED_ON_SHEET[arm]}"
        print(f"{arm}: {n} answers on the sheet{flag}")

    # 3. per question and arm
    rows = []
    status = {arm: {} for arm in ARMS}
    for arm in ARMS:
        for i in ans_ids:
            bid = per[arm].get(i)
            l = lab[bid]["label"].strip().lower() if bid else "not_answered"
            status[arm][i] = l
            rows.append({"arm": arm, "id": i, "blind_id": bid or "", "label": l,
                         "strict_correct": l == "correct", "lenient_correct": l in ("correct", "partial")})

    per_arm = []
    for arm in ARMS:
        c = collections.Counter(status[arm].values())
        per_arm.append({"arm": arm, "n_answerable": 52, "answered_strict": 52 - c["not_answered"],
                        "correct": c["correct"], "partial": c["partial"], "wrong": c["wrong"],
                        "strict_correct_of_52": c["correct"], "lenient_correct_of_52": c["correct"] + c["partial"]})

    tests = []
    for other in ("P0", "CB"):
        for scoring, ok in (("strict", {"correct"}), ("lenient", {"correct", "partial"})):
            fx = {i: status["F0"][i] in ok for i in ans_ids}
            fy = {i: status[other][i] in ok for i in ans_ids}
            b = sum(fx[i] and not fy[i] for i in ans_ids)
            cc = sum(fy[i] and not fx[i] for i in ans_ids)
            tests.append({"comparison": f"F0 vs {other}", "scoring": scoring, "n": 52,
                          "F0": sum(fx.values()), "other": sum(fy.values()),
                          "b_F0_only": b, "c_other_only": cc, "p_exact_two_sided": round(mcnemar(b, cc), 6),
                          "adjustment": "none (pre-registered, unadjusted)"})

    # 4. optional: new F0 labels vs the provisional ones (correctness_sheet.csv)
    agree_txt = "skipped"
    try:
        import exp2_gitlab_baselines as BL
        old, problems, _ = BL.f0_labels(qs)
        both = [i for i in ans_ids if i in old and status["F0"][i] != "not_answered"]
        t = collections.Counter((old[i], status["F0"][i]) for i in both)
        same = sum(v for (o, n), v in t.items() if o == n)
        agree_txt = (f"{same}/{len(both)} F0 answers got the same label as in the provisional sheet; "
                     f"changes (old -> new): {dict((f'{o}->{n}', v) for (o, n), v in t.items() if o != n)}; "
                     f"mapping problems: {problems}")
    except Exception as e:                              # informative only
        agree_txt = f"skipped ({type(e).__name__}: {e})"
    print("F0 old vs new labels:", agree_txt)

    write_csv(OUTS["rows"], rows)
    write_csv(OUTS["per_arm"], per_arm)
    write_csv(OUTS["tests"], tests)
    L = ["# Baselines correctness (blind sheet, unblinded)", "",
         f"Labels: `{LABELS}` (sha256 {LABELS_SHA256[:16]}...), 147 answers, final on 12 Nov 2026 (Clifton),"
         " before the key was opened.", "",
         "| Arm | Answered (strict) /52 | correct | partial | wrong | Strict correct /52 | Lenient correct /52 |",
         "|---|---|---|---|---|---|---|"]
    for r in per_arm:
        L.append(f"| {r['arm']} | {r['answered_strict']} | {r['correct']} | {r['partial']} | {r['wrong']} | "
                 f"{r['strict_correct_of_52']} | {r['lenient_correct_of_52']} |")
    L += ["", "Exact McNemar, two-sided, unadjusted (pre-registered):", "",
          "| Comparison | Scoring | F0 | Other | F0 only | Other only | p |", "|---|---|---|---|---|---|---|"]
    for t in tests:
        L.append(f"| {t['comparison']} | {t['scoring']} | {t['F0']} | {t['other']} | {t['b_F0_only']} | "
                 f"{t['c_other_only']} | {t['p_exact_two_sided']:.4g} |")
    L += ["", f"F0 new vs provisional labels: {agree_txt}", ""]
    with open(MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\nwrote {', '.join(OUTS.values())}, {MD}")


if __name__ == "__main__":
    main()
