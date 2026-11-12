"""Merge the two raters' SymPy H0 labels and count correctness (tuning_rule_sympy_h0.md; counts only, no tests).

    python sympy_h0_labels.py      # -> results/sympy_h0/correctness_sheet_merged.csv, correctness.csv, labels_check.json

Every non-label cell must equal the generated sheet. Final label = the lower of the two; upper is the sensitivity.
Arms come from keys/sheet_key.json, opened only after the merge. F0 = Clifton's labels. F0 rerun = Clifton's label where
the answer text is identical to his, otherwise the new merged label. Re-labelled F0 rows are a drift check only.
"""
import csv
import json

ROOT = "results/sympy_h0"
ORDER = {"wrong": 0, "partial": 1, "correct": 2}
FIXED = ["blind_id", "question", "gold_answer", "gold_quotes", "model_answer"]


def sheet(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {r["blind_id"]: r for r in csv.DictReader(f)}


def rd(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def kappa(x, y, labels):
    n = len(x)
    po = sum(a == b for a, b in zip(x, y)) / n
    pe = sum(sum(a == k for a in x) * sum(b == k for b in y) for k in labels) / n ** 2
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def main():
    base = sheet(f"{ROOT}/correctness_sheet.csv")
    a, j = sheet(f"{ROOT}/correctness_sheet_alyssa.csv"), sheet(f"{ROOT}/correctness_sheet_james.csv")
    assert set(base) == set(a) == set(j)
    edits = [(b, c) for b in base for c in FIXED if not (base[b][c] == a[b][c] == j[b][c])]
    assert not edits, edits
    ids = sorted(base)
    la, lj = [a[b]["label"].strip().lower() for b in ids], [j[b]["label"].strip().lower() for b in ids]
    assert all(x in ORDER for x in la + lj)
    lower = {b: min(x, y, key=ORDER.get) for b, x, y in zip(ids, la, lj)}
    upper = {b: max(x, y, key=ORDER.get) for b, x, y in zip(ids, la, lj)}
    with open(f"{ROOT}/correctness_sheet_merged.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["blind_id", "label_alyssa", "label_james", "label", "label_upper"])
        for b, x, y in zip(ids, la, lj):
            w.writerow([b, x, y, lower[b], upper[b]])

    with open(f"{ROOT}/keys/sheet_key.json", encoding="utf-8") as f:
        key = json.load(f)
    with open("results/sympy/sheet_key.json", encoding="utf-8") as f:
        ckey = json.load(f)
    csheet = sheet("results/sympy/correctness_sheet.csv")
    clif = {v["id"]: (csheet[b]["label"].strip(), csheet[b]["label_upper"].strip()) for b, v in ckey.items() if v["arm"] == "F0"}
    new = {(v["arm"], v["id"]): b for b, v in key.items()}
    clif_text = {r["id"]: r["response"] for r in rd("results/sympy/gen_F0.jsonl")}
    answered = {"H0": sorted(i for arm, i in new if arm == "H0"), "F0": sorted(clif)}
    rerun = {}
    summary = {r["arm"]: r for r in csv.DictReader(open(f"{ROOT}/summary.csv", encoding="utf-8"))}
    for r in rd(f"{ROOT}/gen_F0-rerun.jsonl"):
        if r["type"] != "answerable":
            continue
        if r["response"] == clif_text[r["id"]]:
            if r["id"] in clif:
                rerun[r["id"]] = clif[r["id"]]
        elif ("F0-rerun", r["id"]) in new:
            b = new[("F0-rerun", r["id"])]
            rerun[r["id"]] = (lower[b], upper[b])
    assert len(rerun) == int(summary["F0-rerun"]["answered"]), (len(rerun), summary["F0-rerun"]["answered"])
    labels = {"F0 (Clifton, 3050 Ti)": clif, "F0 rerun (5070)": rerun,
              "H0 (5070)": {i: (lower[new[("H0", i)]], upper[new[("H0", i)]]) for i in answered["H0"]}}
    source = {"F0 (Clifton, 3050 Ti)": "F0", "F0 rerun (5070)": "F0-rerun", "H0 (5070)": "H0"}
    rows = []
    for arm, d in labels.items():
        s = summary[source[arm]]
        row = {"arm": arm, "answered": len(d), "n_answerable": 15}
        for name, k in (("lower", 0), ("upper", 1)):
            for lab in ORDER:
                row[f"{lab}_{name}"] = sum(v[k] == lab for v in d.values())
        row |= {"overlap_cited": s["overlap_cited"], "span_in_context": s["span_in_context"],
                "unanswerable_answered": s["unanswerable_answered"], "unanswerable_ids": s["unanswerable_ids"]}
        rows.append(row)
    with open(f"{ROOT}/correctness.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    drift = [(v["id"], clif[v["id"]][0], lower[b]) for b, v in key.items() if v["arm"] == "F0"]
    check = {"n": len(ids), "agree": sum(x == y for x, y in zip(la, lj)), "kappa_3class": kappa(la, lj, list(ORDER)),
             "disagreements": [b for b, x, y in zip(ids, la, lj) if x != y],
             "label_counts_alyssa": {k: la.count(k) for k in ORDER}, "label_counts_james": {k: lj.count(k) for k in ORDER},
             "drift_F0_n": len(drift), "drift_F0_agree": sum(x == y for _, x, y in drift),
             "drift_F0_changes": [d for d in drift if d[1] != d[2]]}
    with open(f"{ROOT}/labels_check.json", "w", encoding="utf-8") as f:
        json.dump(check, f, indent=1)
    print(json.dumps(check))
    for r in rows:
        print(r)
    print("rows by arm", {a_: sum(v["arm"] == a_ for v in key.values()) for a_ in ("H0", "F0", "F0-rerun")})
    print("per question", [(i, clif.get(i, ("-",))[0], rerun.get(i, ("-",))[0], labels["H0 (5070)"].get(i, ("-",))[0])
                           for i in sorted({*clif, *rerun, *labels["H0 (5070)"]})])


if __name__ == "__main__":
    main()
