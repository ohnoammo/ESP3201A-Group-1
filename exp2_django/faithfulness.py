"""Faithfulness of answered answerable rows (test arms) with MiniCheck-Flan-T5-Large and
HHEM-2.1-Open (cross-check). Premises: (1) the chunks the answer cites, (2) the full context.

    python faithfulness.py      # -> results/faithfulness_test_arms.jsonl (resumes; ~1.5-2 h on GPU)
    python faithfulness.py --check results/old.jsonl --n 30 --out results/x.jsonl
                                # rescore the first n rows listed in another output file
    python faithfulness.py --set unanswerable      # -> results/faithfulness_unanswerable.jsonl
                                # answered rows on no-reason (test, dev), whole PR excluded and
                                # PR kept (rk16129, rk9789), for the gate (tuning_rule_gate.md)
    python faithfulness.py --arm h0 [--set unanswerable]
                                # arm H0 (tuning_rule_hybrid.md) -> results/faithfulness_H0{,_unanswerable}.jsonl

Claim units: the answer with citation markers removed (chunk ids, [n] tags; code such as `row[0]`
  is kept) split into sentences; fragments under 3 words are dropped.
MiniCheck (lytang/MiniCheck-Flan-T5-Large): input "premise: <doc> hypothesis: <claim>", score =
  P(token "1") vs "0" at the first decoder step. Windows (both premises; 23 Oct): whole chunks in
  context order, greedily packed to <= 400 words, each window starting with the previous window's
  last chunk (one-chunk overlap) when that still fits; a chunk over 400 words gets its own
  400-word sub-windows with a 100-word overlap. A sentence's score is its max over windows.
HHEM-2.1-Open (vectara/hallucination_evaluation_model): model.predict([(premise, hypothesis)]),
  premise = the chunks joined, passed whole (the model card states no fixed context limit).
Row scores: min over sentences ("all supported") and mean; supported = score >= 0.5.
Contexts are rebuilt with run_generation.pack_context (deterministic, same as generation).
"""
import argparse
import json
import os
import re
import statistics as st

import torch
from tqdm import tqdm

from common import git_commit, read_jsonl
from run_generation import pack_context, short_id
from score import auto

FILES = ["results/gen_test_arms_4b-instruct.jsonl", "results/gen_test_arms_8b.jsonl"]
OUT = {"answerable": "results/faithfulness_test_arms.jsonl",
       "unanswerable": "results/faithfulness_unanswerable.jsonl"}
FILES_H0 = ["results/gen_test_arm_H0_4b-instruct.jsonl", "results/gen_test_arm_H0_8b.jsonl"]
OUT_H0 = {"answerable": "results/faithfulness_H0.jsonl", "unanswerable": "results/faithfulness_H0_unanswerable.jsonl"}
PR_KEPT = ("rk16129", "rk9789")                             # case studies (HANDOVER, 23 Oct)
CITE = re.compile(r"\[?(PR\d+-c\d+)\]?")
CITES = re.compile(r"\[\s*PR\d+-c\d+(?:\s*[,;]\s*PR\d+-c\d+)*\s*\]")   # [PR1-c2, PR3-c4]
NTAG = re.compile(r"(?<![\w`\]])\[\d+(?:\s*,\s*\d+)*\](?!`)")     # [1], [2, 3]; not row[0] or `[0]`
MIN_WORDS = 3
WIN = 400
SUB_OVERLAP = 100
DEV = "cuda" if torch.cuda.is_available() else "cpu"


def sentences(t):
    t = NTAG.sub("", CITE.sub("", CITES.sub("", t)))
    t = re.sub(r"[ \t]+([.,;:!?])", r"\1", re.sub(r"[ \t]+", " ", t)).strip()
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t)
            if len(re.findall(r"\w+", s)) >= MIN_WORDS] or [t]


def windows(texts, n=WIN, overlap=SUB_OVERLAP):
    """Chunk texts (context order) -> window strings, see module docstring."""
    out, cur, cur_n = [], [], 0
    for t in texts:
        k = len(t.split())
        if k > n:                                           # long chunk: own sub-windows
            if cur:
                out.append(cur)
            w = t.split()
            out += [[" ".join(w[i:i + n])] for i in range(0, k - overlap, n - overlap)]
            cur, cur_n = [], 0
        elif cur_n + k <= n:
            cur, cur_n = cur + [t], cur_n + k
        else:
            out.append(cur)
            last = len(cur[-1].split())
            cur, cur_n = ([cur[-1], t], last + k) if last + k <= n else ([t], k)
    if cur:
        out.append(cur)
    return ["\n\n".join(w) for w in out] or [""]


class MiniCheck:
    def __init__(self):
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        name = "lytang/MiniCheck-Flan-T5-Large"
        self.tok = AutoTokenizer.from_pretrained(name)
        self.m = AutoModelForSeq2SeqLM.from_pretrained(name).to(DEV).eval()
        # "1" is one token ("▁1"); "0" is two ("▁", "0"), so step 1 is "▁" vs "▁1"
        self.ids = [self.tok("0", add_special_tokens=False).input_ids[0],
                    self.tok("1", add_special_tokens=False).input_ids[0]]

    @torch.no_grad()
    def score(self, chunks, claim):
        best = 0.0
        for win in windows(chunks):
            enc = self.tok(f"premise: {win} hypothesis: {claim}", return_tensors="pt",
                           truncation=True, max_length=1024).to(DEV)
            dec = torch.full((1, 1), self.m.config.decoder_start_token_id, device=DEV)
            logits = self.m(**enc, decoder_input_ids=dec).logits[0, -1, self.ids]
            best = max(best, torch.softmax(logits, -1)[1].item())
        return best


class HHEM:
    def __init__(self):
        from transformers import AutoModelForSequenceClassification
        self.m = AutoModelForSequenceClassification.from_pretrained(
            "vectara/hallucination_evaluation_model", trust_remote_code=True).to(DEV).eval()

    @torch.no_grad()
    def score(self, chunks, claim):
        return float(self.m.predict([("\n\n".join(chunks), claim)])[0])


def main(args):
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    mc, hh = MiniCheck(), None
    try:
        hh = HHEM()
    except Exception as e:                                  # report, don't hide
        print(f"HHEM failed to load: {type(e).__name__}: {e}")
    todo = []
    for path in (FILES_H0 if args.arm == "h0" else FILES):
        for r in read_jsonl(path):
            q = qs[r["id"]]
            if args.set == "answerable" and (r["type"] != "answerable" or q["split"] != "test"):
                continue
            if args.set == "unanswerable" and not (r["type"] in ("no_reason", "removed") or
                                                   r["id"] in PR_KEPT):
                continue
            a = auto(r, q)
            if not (a["abstained"] or a["empty_answer"]):
                todo.append((path, r, q))
    out_path = args.out or (OUT_H0 if args.arm == "h0" else OUT)[args.set]
    print(f"{len(todo)} rows to score ({args.set})")
    if args.check:
        keys = [(x["file"], x["id"], x["condition"]) for x in read_jsonl(args.check)][:args.n]
        by = {(t[0], t[1]["id"], t[1]["condition"]): t for t in todo}
        todo = [by[k] for k in keys]
    if os.path.exists(out_path):                           # resume
        done = {(x["file"], x["id"], x["condition"]) for x in read_jsonl(out_path)}
        todo = [t for t in todo if (t[0], t[1]["id"], t[1]["condition"]) not in done]
    commit, n = git_commit(), 0
    with open(out_path, "a", encoding="utf-8") as f:
        for path, r, q in tqdm(todo, mininterval=10):
            cks, _ = pack_context(q, r["condition"].split(":")[0])
            assert [c["chunk_id"] for c in cks] == r["context_chunk_ids"], (r["id"], r["condition"])
            cited = set(CITE.findall(r["response"]))
            cited_chunks = [c["text"] for c in cks if short_id(c["chunk_id"]) in cited]
            full_chunks = [c["text"] for c in cks]
            sents = sentences(r["response"])
            rec = {"file": path, "id": r["id"], "condition": r["condition"], "model": r["model"],
                   "n_sentences": len(sents), "n_cited": len(cited), "git_commit": commit}
            for prem_name, prem in (("cited", cited_chunks), ("full", full_chunks)):
                for jn, judge in (("minicheck", mc), ("hhem", hh)):
                    if judge is None or (prem_name == "cited" and not prem):
                        rec[f"{jn}_{prem_name}_min"] = rec[f"{jn}_{prem_name}_mean"] = None
                        continue
                    s = [judge.score(prem, x) for x in sents]
                    rec[f"{jn}_{prem_name}_min"], rec[f"{jn}_{prem_name}_mean"] = min(s), st.mean(s)
            f.write(json.dumps(rec) + "\n")
            f.flush()
            n += 1
    print(f"{n} rows scored")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=list(OUT), default="answerable")
    ap.add_argument("--arm", choices=["frozen", "h0"], default="frozen")
    ap.add_argument("--out", help="default: by --set")
    ap.add_argument("--check", help="output file whose first --n rows are rescored")
    ap.add_argument("--n", type=int, default=30)
    main(ap.parse_args())
