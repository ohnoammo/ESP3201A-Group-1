"""Failure sample for James: no-reason rows that pass the faithfulness gate (MiniCheck cited min
>= 0.5), 5 per model, drawn with random.Random(42) from the sorted candidate list. No labels.

    python gate_pass_sample.py      # -> judging/gate_pass_sample.md
"""
import random

from common import read_jsonl
from faithfulness import CITE, sentences
from gate_eval import THRESHOLD
from run_generation import pack_context, short_id
from stats_arms import ARM, FILES

PER_MODEL, SEED, WORDS = 5, 42, 80
PROMPT = {"c": "v2", "c3": "v3"}


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    faith = {(x["file"], x["id"], x["condition"]): x for x in read_jsonl("results/faithfulness_unanswerable.jsonl")}
    rng = random.Random(SEED)
    out = ["# Gate-pass sample: no-reason rows with MiniCheck cited min >= 0.5",
           "", f"{PER_MODEL} per model, random.Random({SEED}) over the sorted candidates "
           f"(`gate_pass_sample.py`). Every question here has no stated reason in its PR, so any "
           f"answer is unsupported. Cited chunks are cut to their first {WORDS} words.", ""]
    for model, path in FILES.items():
        gen = {(path, r["id"], r["condition"]): r for r in read_jsonl(path)}
        cand = sorted(k for k, f in faith.items() if k[0] == path and qs[k[1]]["type"] == "no_reason"
                      and f["minicheck_cited_min"] is not None and f["minicheck_cited_min"] >= THRESHOLD)
        pick = rng.sample(cand, PER_MODEL)
        out += [f"## {model} ({len(cand)} candidates)", ""]
        for n, k in enumerate(pick, 1):
            r, f, q = gen[k], faith[k], qs[k[1]]
            ctx, pk = r["condition"].split(":")
            cks, _ = pack_context(q, ctx)
            cited = set(CITE.findall(r["response"]))
            out += [f"### {model} #{n}: {k[1]} ({ARM[ctx]}, {PROMPT[pk]}, {q['split']})", "",
                    f"**Question:** {q['question']}", "",
                    f"**Answer:** {r['response'].strip()}", "",
                    f"**MiniCheck cited min:** {f['minicheck_cited_min']:.3f}  "
                    f"**HHEM cited min:** {f['hhem_cited_min']:.3f}  (claim sentences: {len(sentences(r['response']))})", ""]
            for c in cks:
                if short_id(c["chunk_id"]) in cited:
                    w = c["text"].split()
                    out += [f"**{short_id(c['chunk_id'])}** ({len(w)} words):", "",
                            "> " + " ".join(w[:WORDS]) + (" ..." if len(w) > WORDS else ""), ""]
    with open("judging/gate_pass_sample.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
