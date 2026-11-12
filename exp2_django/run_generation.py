"""Run the LLM under test on questions x conditions via Ollama, write one JSONL row per call.

    python run_generation.py --model qwen3:4b-instruct-2507-q4_K_M --select pilot --tag pilot \
        --conditions none:a oracle:b oracle:c

Condition = "<context>:<prompt>":
  context  none      no context
           oracle    all fixed 512/77 chunks of the question's own PR (no index needed)
           retrieved top-k chunks saved by eval_retrieval.py (Tier 2; from the group's retrieve.py via exp1_retriever.py), with the row's exclude_prs removed
           pack-<fixed|struct>-<alpha>-<score|grouped>  Exp 1 expand_and_pack, budget 2,560 (test arms)
           wpr-fixed  arm W-F (tuning_rule_wholepr.md): whole parent PRs of the fixed top-100 ranking,
                      packed in rank order into 2,560 (wholepr_fit.pack_whole), shown as [PR<n>] blocks
  prompt   a = prompts/a_no_retrieval.txt, b = b_standard_rag.txt, c = c_strict_grounded.txt

Every row records model + digest, prompt file + sha1, context condition, Ollama options, the
git commit and the machine/GPU, so a results file is self-describing. Runs are deterministic: temperature 0,
fixed seed, think=False, num_ctx set explicitly (Ollama's default would truncate silently).
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time

import requests

from common import chunks, read_jsonl, git_commit, git_dirty_files

OLLAMA = "http://localhost:11434"
PROMPTS = {"c3": "prompts/c_strict_grounded_v3_DRAFT.txt",
           "a": "prompts/a_no_retrieval.txt", "b": "prompts/b_standard_rag.txt",
           "c": "prompts/c_strict_grounded.txt"}
OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512}


def short_id(chunk_id):
    """'8930_fixed_s512_o77_3' -> 'PR8930-c3' (what the model sees and cites)."""
    pr, *_, i = chunk_id.split("_")
    return f"PR{pr}-c{i}"


def format_context(cks):
    return "\n\n".join(f"[{short_id(c['chunk_id'])}]\n{c['text']}" for c in cks)


def load_prompt(key):
    with open(PROMPTS[key], encoding="utf-8") as f:
        raw = f.read()
    system, user = raw.split("### USER\n")
    system = system.replace("### SYSTEM\n", "").strip()
    return {"system": system, "user": user.strip(), "file": PROMPTS[key],
            "sha1": hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]}


def model_digest(model):
    tags = requests.get(f"{OLLAMA}/api/tags", timeout=30).json()["models"]
    return next((m["digest"][:12] for m in tags if m["name"] == model), None)


def load_retrieved(k):
    """Top-k chunk ids saved by eval_retrieval.py (the exact chunks that were scored)."""
    path = f"results/retrieved_top{k}.jsonl"
    return path, {r["id"]: r["chunk_ids"] for r in read_jsonl(path)}


PACK_CHUNKING = {"fixed": "fixed_s512_o77", "struct": "struct_c256"}
PACK_BUDGET = 2560


def pack_context(row, ctx):
    """ctx = "pack-<fixed|struct>-<alpha>-<score|grouped>": Exp 1 relations.expand_and_pack with
    Exp 2 links (pack_exp1.py), budget 2,560. "grouped" = PRs ordered by their best chunk score,
    chunks within a PR in document order. removed_kept rows use the redacted index variant."""
    from pack_exp1 import build_context_exp1, build_context_redacted
    kind, ch, alpha, order = ctx.split("-")
    suffix = {"pack": "", "packh": "_hybrid"}[kind]    # packh = arm H0, hybrid candidates
    chunking, alpha = PACK_CHUNKING[ch], float(alpha)
    if row["type"] == "removed_kept":
        info = build_context_redacted(row["id"], alpha, PACK_BUDGET, row.get("exclude_prs") or [], chunking,
                                      cand_suffix=suffix)
    else:
        info = build_context_exp1(row["id"], alpha, PACK_BUDGET, row.get("exclude_prs") or [], chunking,
                                  cand_suffix=suffix)
    cks = info["chunks"]
    if order == "grouped":
        best = {}
        for c in cks:
            best[c["pr_number"]] = max(best.get(c["pr_number"], -1), c["score"])
        cks = sorted(cks, key=lambda c: (-best[c["pr_number"]], c["pr_number"], c["start"]))
    elif order != "score":
        raise ValueError(order)
    return cks, {"packer": "exp1 relations.expand_and_pack", "links": "exp2", "chunking": chunking,
                 "alpha": alpha, "order": order, "budget": PACK_BUDGET, "tokens": info["tokens"],
                 "tokenizer": info["tokenizer"], "n_linked": info["n_linked"], "n_prs": info["n_prs"],
                 "chunk_set": info["retriever_meta"]["chunk_set"]}


def wholepr_context(row, ctx):
    """ctx = "wpr-fixed": blocks {chunk_id, pr_number, start, end, text, kind} of arm W-F."""
    from wholepr_fit import candidates, pack_whole, redacted_text
    from common import doc
    assert ctx == "wpr-fixed", ctx
    red = row["type"] == "removed_kept"
    excl = {int(p) for p in (row.get("exclude_prs") or [])}
    ids = candidates("fixed_s512_o77", red)[row["id"]]
    ranked = list(dict.fromkeys(int(c.split("_")[0]) for c in ids if int(c.split("_")[0]) not in excl))

    def text_of(p):
        return (redacted_text(p) if red else None) or doc(p)["text"]
    blocks = []
    for p, kind, ntok, cut in pack_whole(ranked, text_of):
        t = text_of(p)[:cut] if cut else text_of(p)
        blocks.append({"chunk_id": f"{p}_wholepr" + (f"_cut{cut}" if cut else ""), "pr_number": p,
                       "start": 0, "end": len(t), "text": t, "kind": kind, "tokens": ntok})
    return blocks, {"packer": "wholepr_fit.pack_whole", "ranking": "fixed_s512_o77 top-100",
                    "budget": PACK_BUDGET, "tokens": sum(b["tokens"] for b in blocks),
                    "tokenizer": "Exp 1 chunking.count_tokens on whole pr_document text",
                    "n_prs": len(blocks), "rank1_truncated": any(b["kind"] == "truncated" for b in blocks),
                    "redacted": red}


def format_wholepr(blocks):
    return "\n\n".join(f"[PR{b['pr_number']}]\n{b['text']}" for b in blocks)


def machine():
    try:
        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version",
                                       "--format=csv,noheader"], text=True).strip()
    except Exception:
        gpu = "unknown"
    return {"host": platform.node(), "os": platform.platform(), "gpu": gpu}


def span_cov(row, cks):
    """{"any","all"}: answer spans fully covered by the union of context chunks (answerable)."""
    if row["type"] != "answerable" or not row.get("spans"):
        return None
    from eval_links import covered
    from common import doc
    cov = covered(row["spans"], cks, row["pr_number"], doc(row["pr_number"])["text"])
    return {"any": any(cov), "all": all(cov)}


def get_context(row, ctx, k, retrieved=None):
    if ctx == "none":
        return []
    if ctx == "oracle":
        return chunks(row["pr_number"])
    if ctx == "retrieved":
        ids = retrieved[row["id"]]
        by_id = {}
        for cid in ids:
            pr = int(cid.split("_")[0])
            by_id.update({c["chunk_id"]: c for c in chunks(pr)})
        return [by_id[cid] for cid in ids]
    raise ValueError(ctx)


def call(model, system, user):
    body = {"model": model, "think": False, "stream": False, "options": OPTIONS,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    t0 = time.time()
    r = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=600)
    r.raise_for_status()
    d = r.json()
    return d, time.time() - t0


def select(rows, how):
    if how == "all":
        return rows
    if how == "pilot":
        with open("pilot_ids.json", encoding="utf-8") as f:
            ids = json.load(f)["ids"]
        return [r for r in rows if r["id"] in ids]
    ids = set(how.split(","))
    return [r for r in rows if r["id"] in ids]


def main(a):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows console code page
    rows = select(read_jsonl(a.questions), a.select)
    if a.split:
        rows = [r for r in rows if r["split"] == a.split]
    if a.types:
        rows = [r for r in rows if r["type"] in a.types]
    retrieved, retrieved_file, rcfg = None, None, None
    if any(c.startswith("retrieved") for c in a.conditions):
        retrieved_file, retrieved = load_retrieved(a.k)
        with open("retrieval_config.json", encoding="utf-8") as f:
            rcfg = hashlib.sha1(json.dumps(json.load(f), sort_keys=True).encode()
                                ).hexdigest()[:10]
    if a.split == "test" or a.require_frozen:      # test runs must use the frozen prompts
        with open("prompts/FROZEN.json", encoding="utf-8") as f:
            frozen = json.load(f)["prompts"]
        for cond in a.conditions:
            key = cond.split(":")[1]
            if load_prompt(key)["sha1"] != frozen[key]["sha1"]:
                raise SystemExit(f"prompt {key} differs from prompts/FROZEN.json")
    commit, digest = git_commit(), model_digest(a.model)
    ollama_version = requests.get(f"{OLLAMA}/api/version", timeout=30).json().get("version")
    dirty_files = git_dirty_files()
    mach = machine()
    if digest is None:
        raise SystemExit(f"model {a.model} is not pulled in Ollama")
    os.makedirs("results", exist_ok=True)
    out_path = os.path.join("results", f"gen_{a.tag}.jsonl")
    done = set()
    if os.path.exists(out_path):                       # resume
        done = {(r["id"], r["condition"]) for r in read_jsonl(out_path)}
    print(f"{len(rows)} questions x {len(a.conditions)} conditions, model {a.model} "
          f"({digest}), commit {commit} -> {out_path}")
    with open(out_path, "a", encoding="utf-8") as out:
        for cond in a.conditions:
            ctx, pkey = cond.split(":")
            prompt = load_prompt(pkey)
            for r in rows:
                if (r["id"], cond) in done:
                    continue
                if ctx == "oracle" and r["type"] == "removed":
                    continue                      # oracle would hand over the removed answer
                pack_meta = None
                if ctx.startswith(("pack-", "packh-")):
                    cks, pack_meta = pack_context(r, ctx)
                elif ctx.startswith("wpr-"):
                    cks, pack_meta = wholepr_context(r, ctx)
                else:
                    cks = get_context(r, ctx, a.k, retrieved)
                wpr = ctx.startswith("wpr-")
                user = prompt["user"].format(question=r["question"],
                                             context=format_wholepr(cks) if wpr else format_context(cks))
                now = requests.get(f"{OLLAMA}/api/version", timeout=30).json().get("version")
                if now != ollama_version:              # Ollama auto-updated mid-run
                    raise SystemExit(f"Ollama changed {ollama_version} -> {now}; stopping so one "
                                     f"results file never mixes versions. Re-run to resume.")
                d, secs = call(a.model, prompt["system"], user)
                n_in = d.get("prompt_eval_count")
                rec = {"id": r["id"], "type": r["type"], "pr_number": r["pr_number"],
                       "condition": cond, "context": ctx, "prompt_key": pkey,
                       "prompt_file": prompt["file"], "prompt_sha1": prompt["sha1"],
                       "model": a.model, "model_digest": digest, "options": OPTIONS,
                       "ollama_version": ollama_version,
                       "think": False, "git_commit": commit, "git_dirty_files": dirty_files,
                       "context_chunk_ids": [c["chunk_id"] for c in cks],
                       "pack": pack_meta,
                       "span_in_context": span_cov(r, cks) if pack_meta else None,
                       "context_short_ids": [f"PR{c['pr_number']}" if wpr else short_id(c["chunk_id"])
                                             for c in cks],
                       "machine": mach,
                       "exclude_prs": r.get("exclude_prs") or [], "split": r.get("split"),
                       "retrieved_file": retrieved_file if ctx == "retrieved" else None,
                       "retrieval_config_sha1": rcfg if ctx == "retrieved" else None,
                       "prompt_eval_count": n_in, "eval_count": d.get("eval_count"),
                       "possibly_truncated": bool(n_in and n_in >= OPTIONS["num_ctx"] - 16),
                       "done_reason": d.get("done_reason"), "seconds": round(secs, 2),
                       "response": d["message"]["content"]}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                print(f"  {cond:<12}{r['id']:<10} in={n_in} out={d.get('eval_count')} "
                      f"{secs:.1f}s {rec['response'][:70]!r}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3:4b-instruct-2507-q4_K_M")
    ap.add_argument("--questions", default="questions.jsonl")
    ap.add_argument("--select", default="pilot", help="pilot | all | comma-separated ids")
    ap.add_argument("--split", choices=["dev", "test", "dev2"], default=None)
    ap.add_argument("--require-frozen", action="store_true",
                    help="refuse prompts that differ from prompts/FROZEN.json (test runs)")
    ap.add_argument("--types", nargs="*", default=None)
    ap.add_argument("--conditions", nargs="+", default=["none:a", "oracle:b", "oracle:c"])
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--tag", required=True)
    main(ap.parse_args())
