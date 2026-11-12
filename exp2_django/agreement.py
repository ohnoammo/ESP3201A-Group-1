"""Codex vs human agreement on the validation sample (queue b).

    python agreement.py [--human judgements/validation_sample_alyssa.csv]
        -> results/agreement_validation.json, results/agreement_disagreements.csv

Human file: a filled copy of judging/validation_sample.csv (blind_id, ..., label, reason). Blank
rows are dropped; an exact duplicate blind_id is kept once; blind ids of the sample with no human
label are listed as missing. Question/gold/answer text must match judging/validation_sample.csv
after normalising line endings and outer whitespace (otherwise the script stops).
Codex labels: judging/codex_labels.csv (blind_id, label, note).
Reported: Cohen's kappa on the 3 labels and on strict (correct vs rest) and lenient (correct or
partial vs wrong), raw agreement, per-class specific agreement 2*n_ii / (row_i + col_i),
confusion table (rows = human, columns = Codex) and each off-diagonal direction, per-stratum
(model x prompt x chunking) agreement, row bootstrap 95% CIs for the three kappas (2,000 resamples,
seed 0, the same resamples for all three).
The disagreement list shows model and condition from judging/keys/judging_key.json (labels complete).
"""
import argparse
import csv
import hashlib
import json
import random
from collections import Counter

from common import git_commit

LABELS = ("correct", "partial", "wrong")
FIELDS = ("question", "gold_answer", "gold_quotes", "model_answer")
CHUNKING = {"pack-fixed": "fixed", "pack-struct": "structural"}
PROMPT = {"c": "v2", "c3": "v3"}


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def norm(t):
    return t.replace("\r\n", "\n").strip()


def kappa(pairs, classes):
    n = len(pairs)
    po = sum(h == c for h, c in pairs) / n
    hc, cc = Counter(h for h, _ in pairs), Counter(c for _, c in pairs)
    pe = sum(hc[k] * cc[k] for k in classes) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main(a):
    sample = {r["blind_id"]: r for r in read_csv("judging/validation_sample.csv")}
    codex = {r["blind_id"]: r for r in read_csv("judging/codex_labels.csv")}
    with open("judging/keys/judging_key.json", encoding="utf-8") as f:
        key = json.load(f)
    human, dupes = {}, []
    for r in read_csv(a.human):
        if not any(v.strip() for v in r.values() if v):
            continue
        b = r["blind_id"].strip()
        assert b in sample, f"{b} is not in the validation sample"
        assert all(norm(r[k]) == norm(sample[b][k]) for k in FIELDS), f"{b}: text differs from the sample"
        lab = r["label"].strip().lower()
        assert lab in LABELS, f"{b}: label {r['label']!r}"
        if b in human:
            assert human[b]["label"] == lab, f"{b}: duplicate with a different label"
            dupes.append(b)
            continue
        human[b] = {"label": lab, "reason": r["reason"].strip()}
    missing = sorted(set(sample) - set(human))
    ids = sorted(human)
    pairs = [(human[b]["label"], codex[b]["label"].strip().lower()) for b in ids]

    def stratum(b):
        k = key[b]
        ctx, pk = k["condition"].split(":")
        return f"{k['model']}|{PROMPT[pk]}|{CHUNKING['-'.join(ctx.split('-')[:2])]}"

    conf = {h: {c: sum(1 for x, y in pairs if x == h and y == c) for c in LABELS} for h in LABELS}
    per_class = {k: round(2 * conf[k][k] / (sum(conf[k].values()) + sum(conf[h][k] for h in LABELS)), 3)
                 for k in LABELS}
    strict = [(h == "correct", c == "correct") for h, c in pairs]
    lenient = [(h != "wrong", c != "wrong") for h, c in pairs]
    rng = random.Random(0)
    boots = {"3class": [], "strict": [], "lenient": []}
    for _ in range(2000):
        idx = [rng.randrange(len(pairs)) for _ in pairs]
        boots["3class"].append(kappa([pairs[i] for i in idx], LABELS))
        boots["strict"].append(kappa([strict[i] for i in idx], (True, False)))
        boots["lenient"].append(kappa([lenient[i] for i in idx], (True, False)))
    ci = {k: [round(sorted(v)[49], 3), round(sorted(v)[1949], 3)] for k, v in boots.items()}
    strata = {}
    for b, (h, c) in zip(ids, pairs):
        s = strata.setdefault(stratum(b), [0, 0])
        s[0] += h == c
        s[1] += 1
    out = {
        "n": len(ids), "missing_human_label": missing, "duplicate_rows_dropped": dupes,
        "human_counts": dict(Counter(h for h, _ in pairs)), "codex_counts": dict(Counter(c for _, c in pairs)),
        "raw_agreement": round(sum(h == c for h, c in pairs) / len(pairs), 3),
        "kappa_3class": round(kappa(pairs, LABELS), 3),
        "kappa_3class_ci95": ci["3class"],
        "kappa_strict": round(kappa(strict, (True, False)), 3),
        "kappa_strict_ci95": ci["strict"],
        "agreement_strict": round(sum(h == c for h, c in strict) / len(strict), 3),
        "kappa_lenient": round(kappa(lenient, (True, False)), 3),
        "kappa_lenient_ci95": ci["lenient"],
        "agreement_lenient": round(sum(h == c for h, c in lenient) / len(lenient), 3),
        "per_class_specific_agreement": per_class,
        "confusion_rows_human_cols_codex": conf,
        "disagreement_directions": {f"human_{h}_codex_{c}": conf[h][c] for h in LABELS for c in LABELS
                                    if h != c},
        "per_stratum_agree_of_n": {k: f"{v[0]}/{v[1]}" for k, v in sorted(strata.items())},
        "human_file": a.human, "human_sha256": sha(a.human),
        "codex_sha256": sha("judging/codex_labels.csv"), "git_commit": git_commit(),
    }
    with open("results/agreement_validation.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    dis = [{"blind_id": b, "human": h, "codex": c, "model": key[b]["model"], "condition": key[b]["condition"],
            "question_id": key[b]["id"], "human_reason": human[b]["reason"], "codex_note": codex[b]["note"],
            "question": sample[b]["question"], "gold_quotes": sample[b]["gold_quotes"],
            "model_answer": sample[b]["model_answer"]}
           for b, (h, c) in zip(ids, pairs) if h != c]
    with open("results/agreement_disagreements.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(dis[0]))
        w.writeheader()
        w.writerows(dis)
    print(json.dumps({k: v for k, v in out.items() if not k.endswith("sha256")}, indent=1))
    print(f"{len(dis)} disagreements -> results/agreement_disagreements.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--human", default="judgements/validation_sample_alyssa.csv")
    main(ap.parse_args())
