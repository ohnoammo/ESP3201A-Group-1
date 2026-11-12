"""Reconciles the answered Exp 2 correctness sheets into one (James's instruction, 5 Nov).
Reads the two answered sheets and questions.jsonl; never opens exp2_gitlab/keys/ and changes no input.

- Alyssa is the reference rater: `label` is her label, and James's is kept in `label_james`.
- A row with the same text as an earlier row is kept: the sheet has one row per arm and question, so these are
  two arms giving the same answer. The audit notes them.
- nr188 has no answer row (the sheet only holds answerable questions), so it gets a record row with no label.
- Labels and Alyssa's reasons are copied into correctness_sheet.csv, the file report() reads; nothing else there changes.

  python reconcile_correctness.py
"""
import csv
import json
import os

ANSWERED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exp2_gitlab", "Answered_csvs")
OUT = "exp2_gitlab"
TEXT = ("question", "gold_answer", "gold_quotes", "model_answer")
LABELS = {"correct", "partial", "wrong"}
RESOLVED = {"nr188": (
    "Resolved (James, 6 Nov): stays no_reason / unanswerable. The 94% comment came well after the MR opened and explains "
    "why the feature is useful in hindsight, not the problem that prompted adding it. The opening description states "
    "only the feature. The model's answer using the 94% figure is unsupported. Both people's ok is unchanged.")}
FULL_MR_READ = "Full MR read (description, 4 commits, all 16 notes), not just one isolated note. "
FIELDS = ["question_id", "blind_id", "status", *TEXT, "label", "label_james", "label_alyssa",
          "reason_james", "reason_alyssa", "note"]


def read(name):
    with open(os.path.join(ANSWERED, name), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fill_report_sheet(counted):
    """Copies labels and Alyssa's reasons into the sheet report() reads. Stops if a different label is already there."""
    path = os.path.join(OUT, "correctness_sheet.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields, sheet = reader.fieldnames, list(reader)
    by_id = {r["blind_id"]: r for r in counted}
    assert {s["blind_id"] for s in sheet} == set(by_id), "report sheet holds different rows"
    for s in sheet:
        r = by_id[s["blind_id"]]
        assert all(s[c] == r[c] for c in TEXT), f"{s['blind_id']}: report sheet text differs"
        assert s["label"] in ("", r["label"]), f"{s['blind_id']}: report sheet already has {s['label']!r}"
        s["label"], s["reason"] = r["label"], r["reason_alyssa"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(sheet)


def main():
    james = read("correctness_sheet_james.csv")
    alyssa = {r["blind_id"]: r for r in read("correctness_sheet_alyssa (2).csv")}
    with open(os.path.join(OUT, "questions.jsonl"), encoding="utf-8") as f:
        questions = [json.loads(line) for line in f]
    qid = {q["question"]: q["id"] for q in questions}
    assert len(qid) == len(questions), "question text is not unique"
    assert {r["blind_id"] for r in james} == set(alyssa), "sheets hold different rows"

    seen, rows, audit = {}, [], []
    for j in james:
        bid, y = j["blind_id"], alyssa[j["blind_id"]]
        assert all(j[c] == y[c] for c in TEXT), f"{bid}: sheet text differs between people"
        lj, ly = j["label"].strip().lower(), y["label"].strip().lower()
        assert ly in LABELS, f"{bid}: Alyssa's label {ly!r}"
        q, text = qid[j["question"]], tuple(j[c] for c in TEXT)
        same = (f"Same question, gold and model answer as {seen[text]}; kept as the other arm's answer."
                if text in seen else "")
        seen.setdefault(text, bid)
        if lj != ly:
            action = "label_overwritten" if lj in LABELS else "james_no_label_filled"
            audit.append({"action": action, "blind_id": bid, "question_id": q, "old_label": lj, "new_label": ly,
                          "detail": f"Alyssa is the reference rater. {same}".strip()})
        rows.append({"question_id": q, "blind_id": bid, "status": "counted", **{c: j[c] for c in TEXT}, "label": ly,
                     "label_james": lj, "label_alyssa": ly, "reason_james": j["reason"], "reason_alyssa": y["reason"],
                     "note": same})
    for q in questions:
        if q["id"] in RESOLVED:
            on_sheet = any(r["question_id"] == q["id"] for r in rows)
            assert not on_sheet, f"{q['id']} now has answer rows: decide how to treat them"
            rows.append({"question_id": q["id"], "blind_id": "", "status": "resolved-no-reason",
                         "question": q["question"], "gold_answer": "", "gold_quotes": "", "model_answer": "",
                         "label": "", "label_james": "", "label_alyssa": "", "reason_james": "", "reason_alyssa": "",
                         "note": RESOLVED[q["id"]]})
            audit.append({"action": "resolved_no_reason", "blind_id": "", "question_id": q["id"], "old_label": "",
                          "new_label": "", "detail": FULL_MR_READ + RESOLVED[q["id"]]})
    rows.sort(key=lambda r: (r["question_id"], r["blind_id"]))
    with open(os.path.join(OUT, "correctness_sheet_reconciled.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(OUT, "correctness_reconciliation_audit.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["action", "blind_id", "question_id", "old_label", "new_label", "detail"])
        w.writeheader()
        w.writerows(audit)
    counted = [r for r in rows if r["status"] == "counted"]
    fill_report_sheet(counted)
    print(f"{len(james)} rows in; {len(counted)} counted; " + ", ".join(
        f"{v} {sum(r['label'] == v for r in counted)}" for v in sorted(LABELS)))
    for a in audit:
        print(a["action"], a["blind_id"] or a["question_id"], a["old_label"], "->", a["new_label"], "|", a["detail"])


if __name__ == "__main__":
    main()
