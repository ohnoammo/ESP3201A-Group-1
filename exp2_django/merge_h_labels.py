"""Codex labels for arm H0 + drift check (tuning_rule_hybrid.md, 5 Nov).

    python merge_h_labels.py      # -> results/codex_drift_check_h.json; appends to judging/codex_labels.csv

Input judging/codex_labels_h.csv (blind_id, label, note): 177 H0 ids (J0793-J0969) + the 20 pre-declared
old ids re-judged as a drift check. Drift: re-judged vs original labels (agreement, Cohen's kappa, each
change, direction); drift labels are never used in any analysis and the originals are not changed.
Then only the 177 H0 rows are appended to judging/codex_labels.csv (existing bytes unchanged, same CSV
dialect and CRLF line ends). Refuses to run if judging/codex_labels.csv is not the 1 Nov file.
"""
import csv
import hashlib
import io
import json

from agreement import LABELS, kappa
from extend_judging import h0_drift_ids

ORIG, NEW = "judging/codex_labels.csv", "judging/codex_labels_h.csv"
ORIG_SHA = "f47f947285e2ee8aa809f03dfcac8943bcaa3296271d8528fac3c4f35d840c46"
H_IDS = [f"J{i:04d}" for i in range(793, 970)]
DRIFT = h0_drift_ids()


def main():
    raw = open(ORIG, "rb").read()
    assert hashlib.sha256(raw).hexdigest() == ORIG_SHA, "codex_labels.csv is not the 1 Nov file"
    assert raw.endswith(b"\r\n")
    orig = {r["blind_id"]: r for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))}
    with open(NEW, newline="", encoding="utf-8-sig") as f:
        new = {r["blind_id"].strip(): r for r in csv.DictReader(f)}
    assert sorted(new) == sorted(H_IDS + DRIFT) and not set(H_IDS) & set(orig)
    assert all(r["label"].strip().lower() in LABELS for r in new.values())
    pairs = [(orig[b]["label"].strip().lower(), new[b]["label"].strip().lower()) for b in DRIFT]
    drift = {"n": len(DRIFT), "agree": sum(a == b for a, b in pairs), "kappa_3class": round(kappa(pairs, LABELS), 3),
             "changes": [{"blind_id": b, "original": a, "rejudged": c, "original_note": orig[b]["note"],
                          "rejudged_note": new[b]["note"]} for b, (a, c) in zip(DRIFT, pairs) if a != c],
             "original_counts": {k: sum(a == k for a, _ in pairs) for k in LABELS},
             "rejudged_counts": {k: sum(c == k for _, c in pairs) for k in LABELS},
             "codex_labels_h_sha256": hashlib.sha256(open(NEW, "rb").read()).hexdigest(),
             "note": "drift labels are not used in any analysis; original labels unchanged"}
    with open("results/codex_drift_check_h.json", "w", encoding="utf-8") as f:
        json.dump(drift, f, indent=1)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    for b in H_IDS:
        w.writerow([b, new[b]["label"].strip().lower(), new[b]["note"]])
    with open(ORIG, "ab") as f:
        f.write(buf.getvalue().encode("utf-8"))
    out = open(ORIG, "rb").read()
    assert out.startswith(raw)
    print(json.dumps({k: v for k, v in drift.items() if k != "changes"}, indent=1))
    for c in drift["changes"]:
        print(f"  {c['blind_id']}: {c['original']} -> {c['rejudged']}")
    print(f"appended {len(H_IDS)} rows; {ORIG} sha256 {hashlib.sha256(out).hexdigest()}")


if __name__ == "__main__":
    main()
