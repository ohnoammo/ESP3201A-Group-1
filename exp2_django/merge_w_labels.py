"""Codex labels for arm W-F + drift check (1 Nov).

    python merge_w_labels.py      # -> results/codex_drift_check.json; appends to judging/codex_labels.csv

Input judging/codex_labels_w.csv (blind_id, label, note): 133 W-F ids (J0660-J0792) + 20 old ids
re-judged as a drift check. Drift: re-judged vs original labels (agreement, Cohen's kappa, each
change); drift labels are never used in any analysis and the originals are not changed.
Then only the 133 W rows are appended to judging/codex_labels.csv (existing bytes unchanged, same
CSV dialect and CRLF line ends). Refuses to run if judging/codex_labels.csv is not the 23 Oct file.
"""
import csv
import hashlib
import io
import json

from agreement import LABELS, kappa

ORIG, NEW = "judging/codex_labels.csv", "judging/codex_labels_w.csv"
ORIG_SHA = "806d14ecc7231c4b3c27a2de998d1a5e613731d840414f15259ed2d771ed238c"
W_IDS = [f"J{i:04d}" for i in range(660, 793)]
DRIFT = ["J0026", "J0028", "J0031", "J0033", "J0090", "J0096", "J0105", "J0115", "J0143", "J0224", "J0229",
         "J0239", "J0251", "J0282", "J0433", "J0518", "J0559", "J0605", "J0617", "J0655"]


def main():
    raw = open(ORIG, "rb").read()
    assert hashlib.sha256(raw).hexdigest() == ORIG_SHA, "codex_labels.csv is not the 23 Oct file"
    assert raw.endswith(b"\r\n")
    orig = {r["blind_id"]: r for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))}
    with open(NEW, newline="", encoding="utf-8-sig") as f:
        new = {r["blind_id"].strip(): r for r in csv.DictReader(f)}
    assert sorted(new) == sorted(W_IDS + DRIFT) and not set(W_IDS) & set(orig)
    assert all(r["label"].strip().lower() in LABELS for r in new.values())
    pairs = [(orig[b]["label"].strip().lower(), new[b]["label"].strip().lower()) for b in DRIFT]
    drift = {"n": len(DRIFT), "agree": sum(a == b for a, b in pairs), "kappa_3class": round(kappa(pairs, LABELS), 3),
             "changes": [{"blind_id": b, "original": a, "rejudged": c, "original_note": orig[b]["note"],
                          "rejudged_note": new[b]["note"]} for b, (a, c) in zip(DRIFT, pairs) if a != c],
             "original_counts": {k: sum(a == k for a, _ in pairs) for k in LABELS},
             "rejudged_counts": {k: sum(c == k for _, c in pairs) for k in LABELS},
             "codex_labels_w_sha256": hashlib.sha256(open(NEW, "rb").read()).hexdigest(),
             "note": "drift labels are not used in any analysis; original labels unchanged"}
    with open("results/codex_drift_check.json", "w", encoding="utf-8") as f:
        json.dump(drift, f, indent=1)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    for b in W_IDS:
        w.writerow([b, new[b]["label"].strip().lower(), new[b]["note"]])
    with open(ORIG, "ab") as f:
        f.write(buf.getvalue().encode("utf-8"))
    out = open(ORIG, "rb").read()
    assert out.startswith(raw)
    print(json.dumps({k: v for k, v in drift.items() if k != "changes"}, indent=1))
    for c in drift["changes"]:
        print(f"  {c['blind_id']}: {c['original']} -> {c['rejudged']}")
    print(f"appended {len(W_IDS)} rows; {ORIG} sha256 {hashlib.sha256(out).hexdigest()}")


if __name__ == "__main__":
    main()
