"""Paired exact McNemar tests on correctness labels (50 test answerables, per model).

    python stats_correctness.py [--labels judging/codex_labels.csv]   # -> results/stats_correctness.csv

Rule: tuning_rule_correctness.md (committed before the first run).

Same pairs and test as stats_arms.py: F0 vs S0, S0 vs S0-G, S0-G vs S-0.25 (within each prompt),
v2 vs v3 within each arm; exact two-sided McNemar on discordant pairs; min_p = 2^(1-(b+c)).
Labels: the labelled pack (blind_id, label in correct / partial / wrong), joined to rows through
judging/keys/judging_key.json. Rows that were not answered (abstained or empty) have no label and
count as not correct. Every answered row must carry a valid label, otherwise the script stops.
Outcomes: correct (label = correct) and correct_or_partial.
40 tests = 2 models x 10 pairs x 2 outcomes, Holm-adjusted as one family (separate from the 60
tests in stats_arms.py).
Consistency check (printed first): rows with the same question and the same normalised answer
(lower case, punctuation removed, whitespace collapsed) should get the same label; reports how
many such groups (and rows in them) got more than one label.
"""
import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict

from common import git_commit, read_jsonl
from stats_arms import ARM, FILES, holm, mcnemar

LABELS = ("correct", "partial", "wrong")
OUTCOMES = {"correct": ("correct",), "correct_or_partial": ("correct", "partial")}


def load_labels(path):
    with open("judging/keys/judging_key.json", encoding="utf-8") as f:
        key = json.load(f)
    with open(path, newline="", encoding="utf-8-sig") as f:
        pack = list(csv.DictReader(f))
    if pack and "model_answer" not in pack[0]:      # labels-only file (blind_id, label, note)
        with open("judging/codex_pack.csv", newline="", encoding="utf-8-sig") as f:
            text = {r["blind_id"]: r for r in csv.DictReader(f)}
        pack = [text[r["blind_id"]] | {"label": r["label"]} for r in pack]
    assert {r["blind_id"] for r in pack} == set(key), "pack and key blind ids differ"
    bad = [r["blind_id"] for r in pack if r["label"].strip().lower() not in LABELS]
    assert not bad, f"{len(bad)} rows without a valid label, e.g. {bad[:5]}"
    consistency(pack)
    return {(key[r["blind_id"]]["file"], key[r["blind_id"]]["id"], key[r["blind_id"]]["condition"]):
            r["label"].strip().lower() for r in pack}


def norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", t.lower())).strip()


def consistency(pack):
    groups = defaultdict(list)
    for r in pack:
        groups[(r["question"], norm(r["model_answer"]))].append(r)
    dup = {k: v for k, v in groups.items() if len(v) > 1}
    bad = {k: v for k, v in dup.items() if len({r["label"].strip().lower() for r in v}) > 1}
    print(f"consistency: {len(groups)} unique (question, normalised answer) pairs; {len(dup)} with "
          f"> 1 row ({sum(map(len, dup.values()))} rows); {len(bad)} of these got different labels "
          f"({sum(map(len, bad.values()))} rows)")
    for v in bad.values():
        print("  " + ", ".join(f"{r['blind_id']}={r['label'].strip().lower()}" for r in v))


def main(a):
    labels = load_labels(a.labels)
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    ids = sorted(q["id"] for q in qs.values() if q["type"] == "answerable" and q["split"] == "test")
    pairs = [(("F0", p), ("S0", p)) for p in ("v2", "v3")] + \
            [(("S0", p), ("S0-G", p)) for p in ("v2", "v3")] + \
            [(("S0-G", p), ("S-0.25", p)) for p in ("v2", "v3")] + \
            [((arm, "v2"), (arm, "v3")) for arm in ("F0", "S0", "S0-G", "S-0.25")]
    rows = []
    for model, path in FILES.items():
        lab = {}
        for r in read_jsonl(path):
            if r["type"] != "answerable" or qs[r["id"]]["split"] != "test":
                continue
            ctx, pk = r["condition"].split(":")
            lab[(ARM[ctx], {"c": "v2", "c3": "v3"}[pk], r["id"])] = labels.get((path, r["id"], r["condition"]))
        for (a1, p1), (a2, p2) in pairs:
            for m, ok in OUTCOMES.items():
                x = [lab[(a1, p1, i)] in ok for i in ids]
                y = [lab[(a2, p2, i)] in ok for i in ids]
                p, n01, n10 = mcnemar(x, y)
                rows.append({"model": model, "A": f"{a1}/{p1}", "B": f"{a2}/{p2}", "outcome": m,
                             "A_count": sum(x), "B_count": sum(y), "only_A": n01, "only_B": n10,
                             "p": p, "min_p": min(1.0, 2.0 ** (1 - n01 - n10))})
    for r, h in zip(rows, holm([r["p"] for r in rows])):
        r["p_holm"] = h
    with open(a.labels, "rb") as f:
        lab_sha = hashlib.sha256(f.read()).hexdigest()[:12]
    commit = git_commit()
    for r in rows:
        for k in ("p", "min_p", "p_holm"):
            r[k] = round(r[k], 4)
        r["labels_sha256_12"], r["git_commit"] = lab_sha, commit
    with open("results/stats_correctness.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{'model':12} {'A':10} {'B':10} {'outcome':20} {'b':>3} {'c':>3} {'p':>7} {'Holm p':>7}")
    for r in rows:
        if r["only_A"] + r["only_B"] >= 5:
            print(f"{r['model']:12} {r['A']:10} {r['B']:10} {r['outcome']:20} {r['only_A']:>3} "
                  f"{r['only_B']:>3} {r['p']:>7.4f} {r['p_holm']:>7.4f}")
    print(f"{len(rows)} tests; {sum(r['only_A'] + r['only_B'] >= 5 for r in rows)} with b+c >= 5; "
          f"{sum(r['p'] < 0.05 for r in rows)} with p < 0.05; {sum(r['p_holm'] < 0.05 for r in rows)} "
          f"with Holm p < 0.05")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="judging/codex_labels.csv")
    main(ap.parse_args())
