"""Failure-analysis examples by fixed rule (queue c).

    python failure_examples.py      # -> results/failure_examples.json

Rows: both test-arm gen files, 2 models x 4 arms x 2 prompts x 67 questions = 1,072 (50 answerable test +
17 unanswerable; rk11459 and rk12342, dropped 23 Oct, are left out).
Answered = not abstained (score.abstained_strict) and not empty. Answerable = answerable test (50 per cell).
Rule categories:
  retrieval miss   answerable, gold PR not in context, answered (any Codex label)
  wrong chunk      answerable, gold PR in context, answered, >= 1 citation, no cited chunk overlaps a
                   gold span, Codex label wrong
  same-ticket      answered, cites a PR that shares a ticket with the question's PR
                   (common.same_ticket_prs over pool A, ticket ids from PR titles)
  bare citation    >= 1 citation and fewer than 3 words after removing citations and brackets
  over-abstention  answerable, abstained, answer span in context
  borrowing        (count only) answered, >= 1 citation, none from the question's PR
Alyssa-tag categories (invented reason, what-as-why, borrowing): rows parsed from
judgements/gate_pass_sample_alyssa.md, main tag = first word of the tag line.
Selection, per category in table order: sort candidates by (model, arm in F0/S0/S0-G/S-0.25 order,
prompt, question id) and take the first whose question id is not already used in the table. If every
candidate's question is already used (bare citation: only nr9172), the first candidate is shown and
marked as a repeat (owner, 1 Nov). Retrieval miss also reports abstained rows with the gold PR absent.
"""
import json
import re

from common import git_commit, pool_numbers, read_jsonl, same_ticket_prs
from score import CITE, auto
from stats_arms import ARM, FILES
from stats_correctness import load_labels

ORDER = ["F0", "S0", "S0-G", "S-0.25"]
PROMPT = {"c": "v2", "c3": "v3"}
TABLE = ["retrieval miss", "wrong chunk", "same-ticket", "invented reason", "what-as-why", "borrowing",
         "bare citation", "over-abstention"]
TAG = {"invented": "invented reason", "what-as-why": "what-as-why", "borrowed": "borrowing"}
HEAD = re.compile(r"^### (\S+) #(\d): (\S+) \((\S+), (v\d), (\w+)\)")
DROPPED = ("rk11459", "rk12342")


def words(resp):
    return len(re.findall(r"\w+", CITE.sub("", resp).replace("[", "").replace("]", "")))


def cited_prs(resp):
    return sorted({int(a) for a, _ in CITE.findall(resp)})


def alyssa_rows():
    rows, cur = [], None
    with open("judgements/gate_pass_sample_alyssa.md", encoding="utf-8") as f:
        for line in f:
            m = HEAD.match(line)
            if m:
                cur = {"model": m[1], "sample_no": int(m[2]), "id": m[3], "arm": m[4], "prompt": m[5],
                       "split": m[6]}
                rows.append(cur)
            elif cur and re.match(r"\*\*Tag(ged)?:\*\*", line):
                cur["tag"] = line.split(":**", 1)[1].strip()
                cur["category"] = TAG[cur["tag"].split()[0]]
    return rows


def sort_key(x):
    return (x["model"], ORDER.index(x["arm"]), x["prompt"], x["id"])


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    labels = load_labels("judging/codex_labels.csv")
    pool = pool_numbers()
    ticket_mates = {}
    rows = []
    for model, path in FILES.items():
        for r in read_jsonl(path):
            if r["id"] in DROPPED:
                continue
            q = qs[r["id"]]
            a = auto(r, q)
            ctx, pk = r["condition"].split(":")
            answerable = r["type"] == "answerable" and q["split"] == "test"
            n = r["pr_number"]
            if n not in ticket_mates:
                ticket_mates[n] = set(same_ticket_prs(n, pool))
            prs_ctx = {int(s.split("-")[0][2:]) for s in r["context_short_ids"]}
            cites = cited_prs(r["response"])
            rows.append({"model": model, "arm": ARM[ctx], "prompt": PROMPT[pk], "id": r["id"], "type": r["type"],
                         "split": q["split"], "answerable": answerable, "pr": n,
                         "answered": not a["abstained"] and not a["empty_answer"], "abstained": a["abstained"],
                         "gold_pr_in_ctx": n in prs_ctx, "span_in_ctx": bool((r["span_in_context"] or {}).get("any")),
                         "n_cites": a["n_cites"], "n_gold_cites": a["n_gold_cites"], "cited_prs": cites,
                         "same_ticket_cited": sorted(set(cites) & ticket_mates[n]), "words": words(r["response"]),
                         "label": labels.get((path, r["id"], r["condition"])), "response": r["response"]})
    assert len(rows) == 1072
    ans = [x for x in rows if x["answerable"]]
    rule = {
        "retrieval miss": ([x for x in ans if not x["gold_pr_in_ctx"] and x["answered"]],
                           [x for x in ans if not x["gold_pr_in_ctx"]], "answerable rows with gold PR not in context"),
        "wrong chunk": ([x for x in ans if x["gold_pr_in_ctx"] and x["answered"] and x["n_cites"]
                         and not x["n_gold_cites"] and x["label"] == "wrong"],
                        [x for x in ans if x["gold_pr_in_ctx"] and x["answered"]],
                        "answered answerable rows with gold PR in context"),
        "same-ticket": ([x for x in rows if x["answered"] and x["same_ticket_cited"]],
                        [x for x in rows if x["answered"]], "answered rows (answerable + 17 unanswerable)"),
        "bare citation": ([x for x in rows if x["n_cites"] and x["words"] < 3], rows, "all rows"),
        "over-abstention": ([x for x in ans if x["abstained"] and x["span_in_ctx"]],
                            [x for x in ans if x["span_in_ctx"]], "answerable rows with answer span in context"),
    }
    borrow = [x for x in rows if x["answered"] and x["n_cites"] and x["pr"] not in x["cited_prs"]]
    borrow_den = [x for x in rows if x["answered"] and x["n_cites"]]
    tagged = alyssa_rows()
    assert len(tagged) == 10
    used, out = set(), []
    for cat in TABLE:
        if cat in rule:
            cand, den, den_name = rule[cat]
            source = "rule-selected"
        else:
            cand = [t for t in tagged if t["category"] == cat]
            source = "Alyssa tag"
        pick = next((x for x in sorted(cand, key=sort_key) if x["id"] not in used), None)
        repeat = pick is None and bool(cand)
        if repeat:
            pick = sorted(cand, key=sort_key)[0]
        if pick:
            used.add(pick["id"])
        entry = {"category": cat, "source": source, "n_candidates": len(cand), "repeat_of_used_question": repeat,
                 "example": pick and {k: v for k, v in pick.items()},
                 "candidate_ids": sorted({x["id"] for x in cand})}
        if cat in rule:
            entry["count"] = f"{len(cand)} / {len(den)} {den_name}"
            if cat == "retrieval miss":
                ab = [x for x in den if x["abstained"]]
                entry["count_other_side"] = f"abstained {len(ab)} / {len(den)} {den_name}"
        elif cat == "borrowing":
            entry["count"] = (f"tagged {len(cand)} / 10 sample rows; by rule {len(borrow)} / {len(borrow_den)} "
                              f"answered rows with >= 1 citation cite no chunk of the question's PR")
        else:
            entry["count"] = (f"{len(cand)} rows in Alyssa's 10-row gate-pass sample (nr10075 is "
                              f"{sum(t['id'] == 'nr10075' for t in tagged)} of the 10); not countable by rule")
        out.append(entry)
    sp = [x for x in rule["over-abstention"][0] if x["id"] == "q16824"]
    res = {"table": out, "q16824_over_abstention_rows": len(sp),
           "pr_with_ticket_mates_in_pool": sorted(n for n, s in ticket_mates.items() if s),
           "git_commit": git_commit()}
    with open("results/failure_examples.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    for e in out:
        x = e["example"] or {}
        print(f"{e['category']:16} {e['source']:13} cand={e['n_candidates']:4} pick={x.get('id')} "
              f"{x.get('model')} {x.get('arm')} {x.get('prompt')}{' (repeat)' if e['repeat_of_used_question'] else ''} "
              f"| {e['count']} {e.get('count_other_side', '')}")
    print("q16824 over-abstention rows:", len(sp), "| PRs with same-ticket mates in pool:",
          res["pr_with_ticket_mates_in_pool"])


if __name__ == "__main__":
    main()
