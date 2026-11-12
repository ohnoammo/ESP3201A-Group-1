"""Score the test generation arms (F0, S0, S0-G, S-0.25 x prompt v2/v3) per model.

    python score_arms.py results/gen_test_arms_4b-instruct.jsonl [more files]
        -> results/summary_test_arms.csv (+ printed table)
    python score_arms.py results/gen_test_arm_H0_4b-instruct.jsonl results/gen_test_arm_H0_8b.jsonl \
        --out results/summary_test_arm_H0.csv       # arm H0, same rules (tuning_rule_hybrid.md)

Per model x arm x prompt:
  answerable (test, 50): span in context (any), answered, abstained with span in context,
    overlap-cited (was "cited the right chunk"), contain-cited (of 49: q14748 has no fully
    containing structural chunk, so it is out for every arm; q14748 overlap-cited shown on its
    own), citation precision, empty answers,
    cross-PR borrowing = answered with >= 1 citation, all citations from other PRs
  no_reason test (5) and dev (5) separately: abstained / empty
  unanswerable answered: of 17 (no-reason test + dev, whole PR excluded, rk16129, rk9789) and of 15
    without nr9172 and nr13883 (P3: contextual clues documented in their question metadata)
  removed (whole PR excluded, 5): abstained / answered, cited PRs of answers
  removed_kept (answer removed, PR kept): case studies rk16129 and rk9789 only, not a rate
  mean distinct PRs in context, mean linked chunks
Abstention = score.abstained_strict (starts with the "Not found" sentence, nothing after); empty = nothing
left after removing citation ids (counted as a non-answer).
"""
import argparse
import csv
import re
from collections import defaultdict

from common import read_jsonl
from score import auto

ARM = {"pack-fixed-0-score": "F0", "pack-struct-0-score": "S0", "pack-struct-0-grouped": "S0-G",
       "pack-struct-0.25-grouped": "S-0.25", "packh-fixed-0-score": "H0"}
PROMPT = {"c": "v2", "c3": "v3"}
CITE = re.compile(r"PR(\d+)-c\d+")
PR_KEPT = ("rk16129", "rk9789")
CLUED = ("nr9172", "nr13883")                   # P3 sensitivity


def main(paths, out="results/summary_test_arms.csv"):
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    rows = []
    for path in paths:
        recs = read_jsonl(path)
        by = defaultdict(list)
        for r in recs:
            ctx, pk = r["condition"].split(":")
            by[(r["model"], ARM[ctx], PROMPT[pk])].append(r)
        for (model, arm, prompt), rs in sorted(by.items()):
            assert all(r["pack"] and r["pack"]["packer"].endswith("expand_and_pack") for r in rs)
            row = {"model": model, "arm": arm, "prompt": prompt}

            def sel(t, split=None, ids=None):
                return [r for r in rs if r["type"] == t and (split is None or r["split"] == split)
                        and (ids is None or r["id"] in ids)]
            ans = sel("answerable", "test")
            A = [(r, auto(r, qs[r["id"]])) for r in ans]
            answered = [(r, a) for r, a in A if not a["abstained"] and not a["empty_answer"]]
            row["span_in_ctx"] = sum(r["span_in_context"]["any"] for r in ans)
            row["answered"] = len(answered)
            row["abstained_with_span"] = sum(a["abstained"] and r["span_in_context"]["any"] for r, a in A)
            row["overlap_cited"] = sum(a["overlap_cited"] for _, a in A)
            row["contain_cited_of49"] = sum(bool(a["contain_cited"]) for r, a in A if r["id"] != "q14748")
            row["q14748_overlap_cited"] = sum(a["overlap_cited"] for r, a in A if r["id"] == "q14748")
            nc = sum(a["n_cites"] for _, a in A)
            row["cite_precision"] = round(sum(a["n_gold_cites"] for _, a in A) / nc, 2) if nc else None
            row["empty_answers"] = sum(a["empty_answer"] for _, a in A)
            row["cross_pr_borrowing"] = sum(
                1 for r, a in answered
                if (prs := {int(x) for x in CITE.findall(r["response"])}) and r["pr_number"] not in prs)
            for split in ("test", "dev"):
                nr = [(r, auto(r, qs[r["id"]])) for r in sel("no_reason", split)]
                row[f"no_reason_{split}_abstained"] = f"{sum(a['abstained'] for _, a in nr)}/{len(nr)}"
                row[f"no_reason_{split}_empty"] = sum(a["empty_answer"] for _, a in nr)
            # PR kept: case studies only (rk16129, rk9789); rk12342 and rk11459 dropped (23 Oct)
            for t, label, ids in (("removed", "removed_wholePR", None),
                                  ("removed_kept", "rk16129", {"rk16129"}),
                                  ("removed_kept", "rk9789", {"rk9789"})):
                rr = [(r, auto(r, qs[r["id"]])) for r in sel(t, ids=ids)]
                row[f"{label}_abstained"] = f"{sum(a['abstained'] for _, a in rr)}/{len(rr)}"
                row[f"{label}_answer_cites"] = "; ".join(
                    f"{r['id']}->" + ",".join(sorted(set(CITE.findall(r['response'])))) for r, a in rr
                    if not a["abstained"] and not a["empty_answer"])
            un = [(r, auto(r, qs[r["id"]])) for r in rs
                  if r["type"] in ("no_reason", "removed") or r["id"] in PR_KEPT]
            assert len(un) == 17
            ua = [r["id"] for r, a in un if not a["abstained"] and not a["empty_answer"]]
            row["unanswerable_answered_of17"] = len(ua)
            row["unanswerable_answered_of15"] = sum(i not in CLUED for i in ua)
            row["no_reason_test_abstained_excl_clued"] = (
                f"{sum(a['abstained'] for r, a in un if r['type'] == 'no_reason' and r['split'] == 'test' and r['id'] not in CLUED)}/3")
            row["mean_prs_in_ctx"] = round(sum(r["pack"]["n_prs"] for r in rs) / len(rs), 1)
            row["mean_linked"] = round(sum(r["pack"]["n_linked"] for r in rs) / len(rs), 1)
            row["mean_ctx_tokens"] = round(sum(r["pack"]["tokens"] for r in rs) / len(rs))
            row["n_calls"] = len(rs)
            row["ollama"] = ";".join(sorted({r["ollama_version"] for r in rs}))
            row["git_commit"] = ";".join(sorted({r["git_commit"] for r in rs}))
            rows.append(row)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", default="results/summary_test_arms.csv")
    a = ap.parse_args()
    main(a.paths, a.out)
