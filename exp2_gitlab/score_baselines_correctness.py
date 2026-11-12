"""Correctness of the baseline arms from Clifton's final blind labels (secondary, single labeller, unadjusted).

Run from the repo root after the labels are committed:  python score_baselines_correctness.py
Reads   results/FOR_JAMES_baselines_labels/baselines_blind_sheet_labels.csv  (final, never written)
        results/baselines_blind_sheet_blank.csv, results/keys/baselines_blind_key.json,
        exp2_gitlab_A2000/gen_{F0,P0,CB,F0_rerun}.jsonl, results/baselines_counts.csv,
        exp2_gitlab_A2000/correctness_sheet.csv (old provisional F0 labels, via exp2_gitlab_baselines.f0_labels)
Writes  results/baselines_correctness.csv, results/baselines_correctness.md  (refuses to overwrite)

Out of 52 answerables per arm: answered (strict = on the sheet; lenient refusal rule shown too), strict correct
(label correct), lenient correct (correct + partial), wrong. An answer not on the sheet counts as not correct
(rule section 7). Exact two-sided McNemar from exp2_scale_stats.mcnemar (rule section 5), b = F0 only,
c = other arm only, unadjusted. F0_rerun has no rows of its own on the sheet: each of its answers is mapped to
the sheet row with the same question and the same citation-stripped answer (RUN_LOG D6).
"""
import collections
import csv
import hashlib
import json
import os
import sys

import exp2_gitlab_baselines as BL
import exp2_gitlab_scale as E
import exp2_scale_stats as S

RES = "results"
LABELS = os.path.join(RES, "FOR_JAMES_baselines_labels", "baselines_blind_sheet_labels.csv")
LABELS_SHA256 = "e33bb8a084f661e3c67c34299c44c46734c020546bde88ace108f1842c00b440"
BLANK = os.path.join(RES, "baselines_blind_sheet_blank.csv")
KEY = os.path.join(RES, "keys", "baselines_blind_key.json")
COUNTS = os.path.join(RES, "baselines_counts.csv")
OUT_CSV = os.path.join(RES, "baselines_correctness.csv")
OUT_MD = os.path.join(RES, "baselines_correctness.md")
ARMS = ("F0", "P0", "CB", "F0_rerun")
CATS = ("correct", "partial", "wrong")


def read_csv(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm(s):
    return (s or "").replace("\r\n", "\n").strip()


def kappa(pairs, cats):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    pe = sum(ca[c] * cb[c] for c in cats) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def main():
    for p in (OUT_CSV, OUT_MD):
        if os.path.exists(p):
            sys.exit(f"{p} exists: not overwritten")
    assert hashlib.sha256(open(LABELS, "rb").read()).hexdigest() == LABELS_SHA256, "labels file changed"
    labels, blank = read_csv(LABELS), read_csv(BLANK)
    assert len(labels) == len(blank) == 147
    for x, b in zip(labels, blank):
        assert all(x[k] == b[k] for k in ("blind_id", "question", "gold_answer", "gold_quotes", "model_answer"))
        assert x["label"] in CATS, x["blind_id"]
    lab = {x["blind_id"]: x for x in labels}
    key = json.load(open(KEY, encoding="utf-8"))
    assert set(key) == set(lab)

    qs = {q["id"]: q for q in BL.questions()}
    ans_ids = sorted(i for i, q in qs.items() if q["type"] == "answerable")
    assert len(ans_ids) == 52
    gens = BL.load_gens(ARMS)
    assert all(len(gens[a]) == 70 for a in ARMS)

    # sheet row per (arm, id) from the key; text check against the gen file
    sheet = {a: {} for a in ARMS}
    for bid, who in key.items():
        for w in who:
            r = gens[w["arm"]][w["id"]]
            assert norm(lab[bid]["question"]) == norm(qs[w["id"]]["question"]), (bid, w)
            assert norm(lab[bid]["model_answer"]) == norm(E.strip_citations(r["response"])), (bid, w)
            assert w["id"] not in sheet[w["arm"]], (bid, w)
            sheet[w["arm"]][w["id"]] = bid
    by_text = {(w["id"], norm(lab[bid]["model_answer"])): bid for bid, who in key.items() for w in who}

    fl = {a: {i: BL.flags(gens[a][i], qs[i]) for i in ans_ids} for a in ARMS}
    rerun_problems = []
    for i in ans_ids:                                   # F0_rerun via the shared answer text
        if fl["F0_rerun"][i]["answered_strict"]:
            bid = by_text.get((i, norm(E.strip_citations(gens["F0_rerun"][i]["response"]))))
            if bid is None:
                rerun_problems.append(i)
            else:
                sheet["F0_rerun"][i] = bid
    for a in ("F0", "P0", "CB"):                        # every strict-answered answerable is on the sheet
        assert {i for i in ans_ids if fl[a][i]["answered_strict"]} == set(sheet[a]), a

    status = {a: {i: lab[sheet[a][i]]["label"] if i in sheet[a] else "not_answered" for i in ans_ids} for a in ARMS}
    counts = {r["arm"]: r for r in read_csv(COUNTS)}

    rows, checks = [], []
    for a in ARMS:
        c = collections.Counter(status[a].values())
        ans_l = sum(fl[a][i]["answered_lenient"] for i in ans_ids)
        on_refusal = collections.Counter(status[a][i] for i in ans_ids
                                         if i in sheet[a] and not fl[a][i]["answered_lenient"])
        rows.append({"kind": "arm", "name": a, "n": 52, "answered_strict": len(sheet[a]),
                     "answered_lenient": ans_l, "correct": c["correct"], "partial": c["partial"],
                     "wrong": c["wrong"], "not_answered": c["not_answered"],
                     "strict_correct": c["correct"], "lenient_correct": c["correct"] + c["partial"],
                     "labelled_lenient_refusals": f"correct {on_refusal['correct']}, partial "
                                                  f"{on_refusal['partial']}, wrong {on_refusal['wrong']}"})
        checks.append((a, len(sheet[a]), int(counts[a]["answerable_answered_strict"]),
                       ans_l, int(counts[a]["answerable_answered_lenient"])))

    tests = []
    for other in ("P0", "CB"):
        for scoring, ok in (("strict", {"correct"}), ("lenient", {"correct", "partial"})):
            fx = {i: status["F0"][i] in ok for i in ans_ids}
            fy = {i: status[other][i] in ok for i in ans_ids}
            b = sum(fx[i] and not fy[i] for i in ans_ids)
            cc = sum(fy[i] and not fx[i] for i in ans_ids)
            tests.append({"kind": "mcnemar", "name": f"F0 vs {other}", "scoring": scoring, "n": 52,
                          "F0_correct": sum(fx.values()), "other_correct": sum(fy.values()),
                          "b_F0_only": b, "c_other_only": cc, "p_exact_two_sided": S.mcnemar(b, cc),
                          "adjustment": "none"})

    # old provisional F0 labels vs Clifton's
    old, problems, _ = BL.f0_labels(qs)
    both = [i for i in ans_ids if i in old and status["F0"][i] != "not_answered"]
    only_one = [i for i in ans_ids if (i in old) != (status["F0"][i] != "not_answered")]
    table = collections.Counter((old[i], status["F0"][i]) for i in both)
    k3 = kappa([(old[i], status["F0"][i]) for i in both], CATS)
    k_strict = kappa([(old[i] == "correct", status["F0"][i] == "correct") for i in both], (True, False))
    k_len = kappa([(old[i] != "wrong", status["F0"][i] != "wrong") for i in both], (True, False))
    old_strict = sum(old[i] == "correct" for i in ans_ids if i in old)
    old_len = sum(old[i] in ("correct", "partial") for i in ans_ids if i in old)

    fields = ["kind", "name", "scoring", "n", "answered_strict", "answered_lenient", "correct", "partial", "wrong",
              "not_answered", "strict_correct", "lenient_correct", "labelled_lenient_refusals", "F0_correct",
              "other_correct", "b_F0_only", "c_other_only", "p_exact_two_sided", "adjustment"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows + tests)

    L = ["# Baselines correctness (secondary, single labeller: Clifton, unadjusted)", "",
         f"Labels: `{LABELS}` (sha256 `{LABELS_SHA256[:12]}...`), 147 answers, final 12 Nov 2026, committed "
         "(e56c1f9, byte-exact in 4273d42) before the key was opened. Script: `score_baselines_correctness.py`.",
         "Out of the 52 answerables per arm. An answer that is not on the sheet (not answered under strict) counts "
         "as not correct. Strict correct = `correct`; lenient correct = `correct` + `partial`.", "",
         "| Arm | Answered (strict) /52 | Answered (lenient refusal rule) /52 | Strict correct /52 | "
         "Lenient correct /52 | Partial | Wrong | Not answered |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['name']} | {r['answered_strict']} | {r['answered_lenient']} | {r['strict_correct']} | "
                 f"{r['lenient_correct']} | {r['partial']} | {r['wrong']} | {r['not_answered']} |")
    L += ["", "F0_rerun is a check only: its answers are mapped to the sheet by question and citation-stripped text. "
          f"Same label as F0 on all 52: {status['F0'] == status['F0_rerun']}; unmapped F0_rerun answers: "
          f"{rerun_problems or 'none'}.", "",
          "Labels on answers that the lenient refusal rule counts as refusals (they are on the sheet because the "
          "sheet takes strict-answered answers): " + "; ".join(f"{r['name']} {r['labelled_lenient_refusals']}"
                                                              for r in rows), "",
          "## Exact McNemar, two-sided, unadjusted (secondary)", "",
          "b = correct for F0 only, c = correct for the other arm only. p from `exp2_scale_stats.mcnemar`.", "",
          "| Comparison | Scoring | F0 correct | Other correct | b | c | p (unadjusted) |",
          "|---|---|---|---|---|---|---|"]
    for t in tests:
        L.append(f"| {t['name']} | {t['scoring']} | {t['F0_correct']} | {t['other_correct']} | {t['b_F0_only']} | "
                 f"{t['c_other_only']} | {t['p_exact_two_sided']:.3g} |")
    L += ["", "## Cross-checks", "",
          "Answered per arm against `results/baselines_counts.csv` (answerables):", "",
          "| Arm | Strict here | Strict in counts | Lenient here | Lenient in counts | Match |", "|---|---|---|---|---|---|"]
    for a, s1, s2, l1, l2 in checks:
        L.append(f"| {a} | {s1} | {s2} | {l1} | {l2} | {'yes' if (s1, l1) == (s2, l2) else 'NO'} |")
    L += ["", "F0: old provisional labels (`exp2_gitlab_A2000/correctness_sheet.csv`, mapped by "
          f"`exp2_gitlab_baselines.f0_labels`, mapping problems: {problems or 'none'}) against Clifton's. "
          f"Old: strict {old_strict}/52, lenient {old_len}/52. New: strict {rows[0]['strict_correct']}/52, "
          f"lenient {rows[0]['lenient_correct']}/52. Answers labelled in one sheet only: {only_one or 'none'}.", "",
          f"Agreement on the {len(both)} F0 answers in both (rows old, columns Clifton):", "",
          "| Old \\ Clifton | correct | partial | wrong | total |", "|---|---|---|---|---|"]
    for o in CATS:
        L.append(f"| {o} | " + " | ".join(str(table[(o, n)]) for n in CATS) +
                 f" | {sum(table[(o, n)] for n in CATS)} |")
    L.append("| total | " + " | ".join(str(sum(table[(o, n)] for o in CATS)) for n in CATS) + f" | {len(both)} |")
    same = sum(table[(c, c)] for c in CATS)
    L += ["", f"Exact agreement {same}/{len(both)}. Cohen's kappa (unweighted, 3 labels) {k3:.3f}; "
          f"on strict correct vs not {k_strict:.3f}; on lenient correct vs wrong {k_len:.3f}.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
