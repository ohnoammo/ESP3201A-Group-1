"""Import Clifton's SymPy transfer check into this repo and recount it (exploratory, counts only; no tests).

    python import_sympy.py <path to ESP3201A_SWE_exp1_sympy.zip> <path to Django stats_test_poolA_full.txt>

Copies the small input files to results/sympy/ with a SHA-256 manifest; no code from the zip is run or
imported. Writes results/sympy_transfer.csv (Exp 2 counts, lower and upper labels),
results/sympy_agreement.json (Alyssa vs James) and results/sympy_exp1_compare.csv (Exp 1, full query, Django vs
SymPy). Answered counts use this repo's score.abstained_strict and must equal Clifton's summary.csv and report.csv;
labels must follow results/sympy/LABEL_MERGE_RULE.txt.
"""
import csv
import hashlib
import json
import os
import re
import sys
import zipfile

from agreement import kappa
from common import read_jsonl
from score import CITE, abstained_strict

PREFIX = "ESP3201A_SWE_exp1_sympy/"
FILES = ["exp2_sympy/questions.jsonl", "exp2_sympy/gen_F0.jsonl", "exp2_sympy/gen_S0-G.jsonl",
         "exp2_sympy/summary.csv", "exp2_sympy/report.csv", "exp2_sympy/correctness_sheet.csv",
         "exp2_sympy/keys/sheet_key.json", "exp2_sympy/LABELLING.txt", "exp2_sympy/LABEL_MERGE_RULE.txt",
         "results/stats_sympy_full.txt", "START_HERE.md"]
OUT = "results/sympy"
LABELS = ("correct", "partial", "wrong")
ORDER = {"wrong": 0, "partial": 1, "correct": 2}
CONDITIONS = ["fixed_s512_o77|bm25|alpha=0|k1=1.2,b=0.75", "fixed_s512_o77|dense|alpha=0",
              "fixed_s512_o77|hybrid|alpha=0|k1=1.2,b=0.75", "struct_c256|bm25|alpha=0|k1=1.2,b=0.75",
              "struct_c256|dense|alpha=0", "struct_c256|hybrid|alpha=0|k1=1.2,b=0.75"]
PAIRS = [("fixed_s512_o77|dense|alpha=0", "fixed_s512_o77|hybrid|alpha=0|k1=1.2,b=0.75"),
         ("struct_c256|dense|alpha=0", "struct_c256|hybrid|alpha=0|k1=1.2,b=0.75")]


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def stats_table(path):
    """Condition -> n, Hit@5, MRR@5, and pair -> Hit@5 and MRR@5 p values, from a stats.py text file."""
    text = open(path, encoding="utf-8-sig").read()
    first = text.split("=== Retrievers compared", 1)[0]
    table = {}
    for line in first.splitlines():
        m = re.match(r"(\S+)\s+(\d+)\s+([\d.]+)\s+\[[^]]*\]\s+([\d.]+)\s+\[", line)
        if m:
            table[m[1]] = {"n": int(m[2]), "hit5": m[3], "mrr5": m[4]}
    pairs = {}
    for a, b in PAIRS:
        m = re.search(re.escape(f"{a}  vs  {b}") + r"\s+\(n=\d+\)\s+Hit@5 [\d.]+ vs [\d.]+: McNemar p=([\d.]+).*?\n"
                      r"\s+MRR@5 [\d.]+ vs [\d.]+: diff 95% CI \[[^]]*\], permutation p=([\d.]+)", text)
        assert m, (path, a, b)
        pairs[(a, b)] = {"hit5_p": m[1], "mrr5_p": m[2]}
    return table, pairs


def main(zip_path, django_stats):
    os.makedirs(OUT, exist_ok=True)
    manifest = {"source_zip": os.path.basename(zip_path), "source_zip_sha256": sha(zip_path),
                "django_stats": django_stats.replace("\\", "/").split("/ESP3201A/")[-1],
                "django_stats_sha256": sha(django_stats), "files": {}}
    with zipfile.ZipFile(zip_path) as z:
        for name in FILES:
            data = z.read(PREFIX + name)
            dest = os.path.join(OUT, os.path.basename(name))
            with open(dest, "wb") as f:
                f.write(data)
            manifest["files"][name] = hashlib.sha256(data).hexdigest()
    with open(os.path.join(OUT, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)

    qs = {q["id"]: q for q in read_jsonl(f"{OUT}/questions.jsonl")}
    sheet = read_csv(f"{OUT}/correctness_sheet.csv")
    with open(f"{OUT}/sheet_key.json", encoding="utf-8") as f:
        key = json.load(f)
    summary = {r["arm"]: r for r in read_csv(f"{OUT}/summary.csv")}
    report = {r["arm"]: r for r in read_csv(f"{OUT}/report.csv")}
    for r in sheet:
        pair = (r["label_alyssa"].strip(), r["label_james"].strip())
        assert r["label"].strip() == min(pair, key=ORDER.get), r["blind_id"]
        assert r["label_upper"].strip() == max(pair, key=ORDER.get), r["blind_id"]
    rows = []
    for arm in ("F0", "S0-G"):
        gen = read_jsonl(f"{OUT}/gen_{arm}.jsonl")
        ans = [r for r in gen if qs[r["id"]]["type"] == "answerable"]
        un = [r for r in gen if qs[r["id"]]["type"] != "answerable"]
        answered = lambda r: not abstained_strict(r["response"]) and bool(  # noqa: E731
            re.search(r"\w", CITE.sub("", r["response"]).replace("[", "").replace("]", "")))
        got = {r["id"] for r in ans if answered(r)}
        labelled = [r for r in sheet if key[r["blind_id"]]["arm"] == arm]
        assert {key[r["blind_id"]]["id"] for r in labelled} == got, arm
        row = {"arm": arm, "n_answerable": len(ans), "span_in_context": sum(r["span_in_context"]["any"] for r in ans),
               "answered": len(got), "n_unanswerable": len(un), "unanswerable_answered": sum(answered(r) for r in un),
               "unanswerable_ids": " ".join(r["id"] for r in un if answered(r)),
               "overlap_cited": summary[arm]["overlap_cited"], "cross_pr_borrowing": summary[arm]["cross_pr_borrowing"]}
        for name, col in (("lower", "label"), ("upper", "label_upper")):
            for lab in LABELS:
                row[f"{lab}_{name}"] = sum(r[col].strip() == lab for r in labelled)
        assert str(row["answered"]) == summary[arm]["answered"] == report[arm]["answered"], arm
        assert str(row["span_in_context"]) == summary[arm]["span_in_context"], arm
        assert str(row["unanswerable_answered"]) == summary[arm]["unanswerable_answered"], arm
        assert all(str(row[f"{lab}_lower"]) == report[arm][lab] for lab in LABELS), arm
        row |= {"model": gen[0]["model"], "ollama": gen[0]["ollama_version"], "gpu": gen[0]["machine"]["gpu"]}
        rows.append(row)
    write("results/sympy_transfer.csv", rows)

    a, j = [r["label_alyssa"].strip() for r in sheet], [r["label_james"].strip() for r in sheet]
    agreement = {"n": len(sheet), "agree": sum(x == y for x, y in zip(a, j)),
                 "kappa_3class": round(kappa(list(zip(a, j)), LABELS), 3),
                 "kappa_strict": round(kappa([(x == "correct", y == "correct") for x, y in zip(a, j)], (True, False)), 3),
                 "disagreements": [{"blind_id": r["blind_id"], "arm": key[r["blind_id"]]["arm"], "id": key[r["blind_id"]]["id"],
                                    "alyssa": x, "james": y} for r, x, y in zip(sheet, a, j) if x != y]}
    with open("results/sympy_agreement.json", "w", encoding="utf-8") as f:
        json.dump(agreement, f, indent=1)

    s_table, s_pairs = stats_table(f"{OUT}/stats_sympy_full.txt")
    d_table, d_pairs = stats_table(django_stats)
    compare = [{"project": p, "condition": c, "n": t[c]["n"], "hit5": t[c]["hit5"], "mrr5": t[c]["mrr5"]}
               for p, t in (("Django", d_table), ("SymPy", s_table)) for c in CONDITIONS]
    write("results/sympy_exp1_compare.csv", compare)
    p_rows = [{"project": p, "A": a_, "B": b_, "hit5_mcnemar_p": v["hit5_p"], "mrr5_permutation_p": v["mrr5_p"]}
              for p, t in (("Django", d_pairs), ("SymPy", s_pairs)) for (a_, b_), v in t.items()]
    write("results/sympy_exp1_dense_vs_hybrid.csv", p_rows)
    for r in rows:
        print(r)
    print(json.dumps(agreement))
    for r in compare + p_rows:
        print(r)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
