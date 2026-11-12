"""Queue a (analysis only, no generation): gold-PR length and whole-PR fit in 2,560 for a proposed arm W.

    python wholepr_fit.py      # -> results/wholepr_fit.json, results/wholepr_fit_per_question.csv

(1) Gold-PR length, Exp 1 units (chunking.count_tokens on the whole pr_document text), for the 60 test
    gold PRs: 50 answerable + 5 no-reason test + 5 removed (whole PR excluded). The removed questions
    reuse answerable PRs, so the distinct count is also given.
(2) Whole-PR packing (proposed arm W, small-to-big): the saved top-100 ranked chunks of each question and
    chunking (fixed_s512_o77, struct_c256) -> parent PRs in first-appearance order, the row's exclude_prs
    removed (as in the frozen arms). Pack whole PR documents in rank order into 2,560 Exp 1 units,
    skipping any that don't fit; if the rank-1 PR alone exceeds 2,560 it is truncated to the first 2,560
    units and nothing else fits. Per chunking: PRs packed (median, range), gold PR packed whole /
    truncated at rank 1 / skipped / not retrieved, gold span in context (whole: yes; truncated: the
    span ends inside the kept text), compared with span_in_context of the frozen arms.
    Rows: 60 test questions (removed rows: gold PR excluded by design, reported apart) and, for the
    context-length check only, the 17 unanswerables (5 no-reason dev; rk16129 and rk9789 use the redacted
    index and documents, as in the frozen arms).
(3) Context length in Qwen tokens: system + user message (prompt v2 and v3) with W blocks rendered as
    "[PR<n>]\\n<text>" joined by blank lines, wrapped in the Qwen chat format, counted with the
    Qwen3-Embedding-0.6B tokenizer (Qwen3 vocabulary; local HF cache). Checked against Ollama's
    prompt_eval_count on 16 frozen-arm rows rebuilt with run_generation.pack_context.
"""
import csv
import json
import os
import statistics as st

from transformers import AutoTokenizer

from common import doc, read_jsonl
from chunking import TOKEN, count_tokens          # Exp 1, on sys.path via common
from pack_exp1 import REDACTED_COPY
from pr_document import build_document           # Exp 1
from run_generation import format_context, load_prompt, pack_context
from stats_arms import ARM, FILES

BUDGET = 2560
CHUNKINGS = {"fixed": "fixed_s512_o77", "structural": "struct_c256"}
ARM_CHUNKING = {"F0": "fixed", "S0": "structural", "S0-G": "structural", "S-0.25": "structural"}
PROMPTS = {"v2": "c", "v3": "c3"}
TOKENIZER = "Qwen/Qwen3-Embedding-0.6B"


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def summary(v):
    return {"n": len(v), "median": st.median(v), "p90": pct(v, 0.9), "max": max(v),
            "over_512": sum(x > 512 for x in v), "over_2560": sum(x > 2560 for x in v)}


_red = {}


def redacted_text(n):
    if n not in _red:
        p = os.path.join(REDACTED_COPY, "prs", "django_django", f"{n}.json")
        with open(p, encoding="utf-8") as f:
            raw = f.read()
        _red[n] = build_document(json.loads(raw))["text"] if "redacted_for_exp2" in raw else None
    return _red[n]


def candidates(chunking, redacted):
    path = f"results/candidates_{chunking}_k100{'_redacted' if redacted else ''}.jsonl"
    rows = read_jsonl(path)
    return {r["id"]: r["chunk_ids"] for r in rows[1:]}


def pack_whole(ranked, text_of):
    """ranked: parent PRs in first-appearance order. -> [(pr, 'whole'|'truncated', tokens, cut_char)]."""
    out, used = [], 0
    for i, pr in enumerate(ranked):
        t = count_tokens(text_of(pr))
        if i == 0 and t > BUDGET:
            toks = list(TOKEN.finditer(text_of(pr)))
            return [(pr, "truncated", BUDGET, toks[BUDGET - 1].end())]
        if used + t <= BUDGET:
            out.append((pr, "whole", t, None))
            used += t
    return out


def chat_tokens(tok, system, user):
    text = (f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n")
    return len(tok(text, add_special_tokens=False)["input_ids"])


def main():
    qs = read_jsonl("questions_test_arms.jsonl")
    test60 = [q for q in qs if q["split"] == "test" and q["type"] in ("answerable", "no_reason", "removed")]
    unans17 = [q for q in qs if (q["type"] == "no_reason") or q["type"] == "removed"
               or q["id"] in ("rk16129", "rk9789")]
    assert len(test60) == 60 and len(unans17) == 17
    L = {}
    for q in test60:
        n = int(q["pr_number"])
        L.setdefault(n, count_tokens(doc(n)["text"]))
    lengths = {"60 questions (rows)": summary([L[int(q["pr_number"])] for q in test60]),
               "distinct gold PRs": summary(sorted({int(q["pr_number"]): L[int(q["pr_number"])]
                                                     for q in test60}.values())),
               "50 answerable": summary([L[int(q["pr_number"])] for q in test60 if q["type"] == "answerable"])}

    # frozen-arm span_in_context (answerable test), identical across models -> checked
    span = {}
    for model, path in FILES.items():
        for r in read_jsonl(path):
            if r["type"] == "answerable" and r["split"] == "test":
                k = (ARM[r["condition"].split(":")[0]], r["condition"].split(":")[1], r["id"])
                v = r["span_in_context"]["any"]
                assert span.setdefault(k, v) == v, k
    frozen = {arm: sum(v for (a, p, _), v in span.items() if a == arm and p == "c")
              for arm in ARM_CHUNKING}

    tok = AutoTokenizer.from_pretrained(TOKENIZER, local_files_only=True)
    prompts = {p: load_prompt(k) for p, k in PROMPTS.items()}
    per_q, fit, ctx_max = [], {}, {"tokens": 0}
    for cname, chunking in CHUNKINGS.items():
        cand, cand_red = candidates(chunking, False), candidates(chunking, True)
        stat = {"prs_packed": [], "gold": {"whole": 0, "truncated_rank1": 0, "skipped": 0, "not_retrieved": 0},
                "gold_span_in_context": 0, "gold_rank_hist": {}}
        removed = {"prs_packed": [], "gold_packed": 0}
        nr_test = {"whole": 0, "truncated_rank1": 0, "skipped": 0, "not_retrieved": 0}
        for q in test60 + [q for q in unans17 if q not in test60]:
            n, red = int(q["pr_number"]), q["type"] == "removed_kept"
            excl = {int(p) for p in (q.get("exclude_prs") or [])}
            ids = (cand_red if red else cand)[q["id"]]
            ranked = list(dict.fromkeys(int(c.split("_")[0]) for c in ids if int(c.split("_")[0]) not in excl))

            def text_of(p):
                return (redacted_text(p) if red else None) or doc(p)["text"]
            packed = pack_whole(ranked, text_of)
            got = {p: (kind, cut) for p, kind, _, cut in packed}
            if n in got:
                status = "whole" if got[n][0] == "whole" else "truncated_rank1"
            else:
                status = "skipped" if n in ranked else "not_retrieved"
            user_v = {p: pr["user"].format(question=q["question"], context="\n\n".join(
                f"[PR{p_}]\n{text_of(p_)[:cut] if cut else text_of(p_)}" for p_, _, _, cut in packed))
                for p, pr in prompts.items()}
            qt = {p: chat_tokens(tok, prompts[p]["system"], u) for p, u in user_v.items()}
            for p, t in qt.items():
                if t > ctx_max["tokens"]:
                    ctx_max = {"tokens": t, "id": q["id"], "chunking": cname, "prompt": p,
                               "exp1_units": sum(x[2] for x in packed), "n_prs": len(packed)}
            in_ctx = None
            if q["type"] == "answerable":
                spans = json.loads(q["spans"]) if isinstance(q["spans"], str) else q["spans"]
                in_ctx = status == "whole" or (status == "truncated_rank1"
                                               and any(e <= got[n][1] for _, e in spans))
                stat["prs_packed"].append(len(packed))
                stat["gold"][status] += 1
                stat["gold_span_in_context"] += in_ctx
                if n in ranked:
                    r = ranked.index(n) + 1
                    b = "1" if r == 1 else "2-3" if r <= 3 else "4-10" if r <= 10 else ">10"
                    stat["gold_rank_hist"][b] = stat["gold_rank_hist"].get(b, 0) + 1
            elif q["type"] == "removed":
                removed["prs_packed"].append(len(packed))
                removed["gold_packed"] += n in got
            elif q["type"] == "no_reason" and q["split"] == "test":
                nr_test[status] += 1
            per_q.append({"chunking": cname, "id": q["id"], "type": q["type"], "split": q["split"],
                          "gold_pr": n, "gold_tokens": count_tokens(text_of(n)), "gold_rank_pr": (ranked.index(n) + 1) if n in ranked else None,
                          "n_ranked_prs": len(ranked), "n_packed": len(packed), "packed_tokens": sum(x[2] for x in packed),
                          "gold_status": status, "gold_span_in_context": in_ctx,
                          "qwen_tokens_v2": qt["v2"], "qwen_tokens_v3": qt["v3"],
                          "packed": " ".join(f"{p}:{k[0]}" for p, k, *_ in packed)})
        pp = stat["prs_packed"]
        fit[cname] = {"answerable_50": {"prs_packed_median": st.median(pp), "prs_packed_range": [min(pp), max(pp)],
                                        "gold": stat["gold"], "gold_span_in_context_W": stat["gold_span_in_context"],
                                        "gold_pr_rank_among_ranked_prs": stat["gold_rank_hist"],
                                        "frozen_span_in_context": {a: frozen[a] for a, c in ARM_CHUNKING.items() if c == cname}},
                      "no_reason_test_5": nr_test,
                      "removed_5": {"prs_packed_median": st.median(removed["prs_packed"]),
                                    "gold_packed": removed["gold_packed"]}}

    # tokenizer check against Ollama's prompt_eval_count on rebuilt frozen-arm prompts
    check = []
    qmap = {q["id"]: q for q in qs}
    for model, path in FILES.items():
        rows = [r for r in read_jsonl(path) if r["type"] == "answerable"][:400:50]
        for r in rows:
            cks, _ = pack_context(qmap[r["id"]], r["context"])
            assert [c["chunk_id"] for c in cks] == r["context_chunk_ids"]
            pr = load_prompt(r["prompt_key"])
            t = chat_tokens(tok, pr["system"], pr["user"].format(question=qmap[r["id"]]["question"],
                                                                   context=format_context(cks)))
            check.append({"model": model, "id": r["id"], "condition": r["condition"], "ours": t,
                          "ollama": r["prompt_eval_count"], "diff": r["prompt_eval_count"] - t})
    out = {"gold_pr_lengths_exp1_units": lengths, "fit": fit, "max_context_qwen_tokens": ctx_max,
           "num_ctx": 8192, "tokenizer": TOKENIZER, "tokenizer_check_vs_ollama": check}
    with open("results/wholepr_fit.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    with open("results/wholepr_fit_per_question.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(per_q[0]))
        w.writeheader()
        w.writerows(per_q)
    print(json.dumps({k: v for k, v in out.items() if k != "tokenizer_check_vs_ollama"}, indent=1))
    print("tokenizer check (ollama - ours):", sorted({c["diff"] for c in check}))


if __name__ == "__main__":
    main()
