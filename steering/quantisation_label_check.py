"""Why the unsteered bf16 model scores higher than the deployed 4-bit model (report Section 6.3; post hoc).

    python steering/quantisation_label_check.py   # -> steering/results_final/quantisation_label_check.txt

Compares, question by question on the 52 GitLab Runner answerable questions, one labeller's (Liu's) correctness
labels for
  - F0: Ollama qwen3:4b-instruct-2507-q4_K_M (4-bit), from the baselines sheet
    (exp2_gitlab/results/baselines_correctness_clifton_rows.csv), and
  - the unsteered Hugging Face Qwen3-4B-Instruct-2507 (bf16) baseline of the steering experiment
    (steering/results_final/blind_sheet_labels.csv + keys/blind_key.json, rows whose arms include "baseline").
Both used the same contexts. An answerable question with no label was not answered (refused).
Prints the cross-table, strict-correct totals, the ids behind each changed cell, and a text-similarity ratio
(difflib) between the two answers, to separate model behaviour from labelling of near-identical answers.
Reads committed files only; nothing is re-generated or re-labelled.
"""
import collections
import csv
import difflib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)


def jl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    qs = jl(P("exp2_gitlab", "exp2_gitlab_A2000", "questions.jsonl"))
    ans_ids = [q["id"] for q in qs if q.get("type") == "answerable"]
    assert len(ans_ids) == 52

    q4 = {}
    with open(P("exp2_gitlab", "results", "baselines_correctness_clifton_rows.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["arm"] == "F0":
                q4[r["id"]] = r["label"]

    key = json.load(open(P("steering", "results_final", "keys", "blind_key.json"), encoding="utf-8"))
    labels = {}
    with open(P("steering", "results_final", "blind_sheet_labels.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            labels[r["blind_id"]] = r["label"]
    bf16 = {v["id"]: labels[b] for b, v in key.items() if "baseline" in v["arms"]}

    resp4 = {r["id"]: r["response"] for r in jl(P("exp2_gitlab", "exp2_gitlab_A2000", "gen_F0.jsonl"))}
    resp16 = {r["id"]: r["response"] for r in jl(P("steering", "results_final", "gen_baseline.jsonl"))}

    norm = lambda x: x if x in ("correct", "partial", "wrong") else "refused"
    cells = collections.defaultdict(list)
    for i in ans_ids:
        cells[(norm(q4.get(i)), norm(bf16.get(i)))].append(i)

    out = ["4-bit Ollama F0 vs bf16 unsteered HF, 52 GitLab Runner answerable questions (Liu's labels; post hoc)", ""]
    out.append("4-bit label -> bf16 label: n  [ids, answer-text similarity]")
    for (a, b), ids in sorted(cells.items()):
        detail = ""
        if a != b:
            detail = "  " + ", ".join(f"{i} ({difflib.SequenceMatcher(None, resp4[i], resp16[i]).ratio():.2f})"
                                      for i in sorted(ids))
        out.append(f"  {a:8s} -> {b:8s}: {len(ids):2d}{detail}")
    s4 = sum(norm(q4.get(i)) == "correct" for i in ans_ids)
    s16 = sum(norm(bf16.get(i)) == "correct" for i in ans_ids)
    out += ["", f"Strictly correct: 4-bit {s4}/52, bf16 {s16}/52 (difference {s16 - s4})",
            f"Refused by bf16 but not by 4-bit: "
            f"{sum(1 for (a, b), ids in cells.items() if b == 'refused' and a != 'refused' for _ in ids)}"]
    text = "\n".join(out)
    print(text)
    with open(P("steering", "results_final", "quantisation_label_check.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
