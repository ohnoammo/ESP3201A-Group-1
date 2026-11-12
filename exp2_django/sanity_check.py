"""Sanity check of parameters and methods across Exp 2 (re-runnable).

    python sanity_check.py      # -> results/sanity_check.json; prints PASS/FAIL per check
"""
import hashlib
import json
import os

import requests

from common import read_jsonl, pool_numbers, same_ticket_prs, doc, git_commit
from run_generation import OPTIONS, PROMPTS, load_prompt

checks = []


def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": detail})


def main():
    pool = pool_numbers()
    test = read_jsonl("questions.jsonl")
    dev2 = read_jsonl("questions_dev2.jsonl")
    rk = read_jsonl("questions_removed_kept.jsonl") if os.path.exists("questions_removed_kept.jsonl") else []
    pool_meta = json.load(open(os.path.join(os.path.dirname(os.path.dirname(__file__)) if False else
                                            "C:/Users/kwekt/ESP3201A_local/exp1_copy/prs/django_django",
                                            "_pool_A2000.json")))
    check("pool A is the new same-ticket-filtered pool", pool_meta.get("drop_same_ticket") is True
          and len(pool) == 2231, f"{len(pool)} PRs, n_same_ticket={pool_meta.get('n_same_ticket')}")
    # splits
    ids = [q["id"] for q in test + dev2]
    check("question ids unique across test/dev/dev2", len(ids) == len(set(ids)))
    tprs = {q["pr_number"] for q in test if q["split"] == "test"}
    dprs = {q["pr_number"] for q in test if q["split"] == "dev"}
    d2prs = {q["pr_number"] for q in dev2}
    check("no PR shared between test, dev and dev2", not (tprs & dprs) and not (tprs & d2prs)
          and not (dprs & d2prs))
    tick = [q["id"] for q in dev2 if set(same_ticket_prs(q["pr_number"], pool)) & (tprs | {p for q2 in test for p in q2["exclude_prs"]})]
    check("no dev2 PR shares a Trac ticket with test material", not tick, str(tick))
    check("all question PRs in pool", all(q["pr_number"] in pool for q in test + dev2))
    check("all exclude_prs in pool", all(p in pool for q in test + rk for p in q["exclude_prs"]))
    # quotes / spans
    bad = [q["id"] for q in test + dev2 if q["type"] == "answerable"
           and any(doc(q["pr_number"])["text"][a:b] != t for (a, b), t in zip(q["spans"], q["quotes"]))]
    check("every quote equals the PR text at its span", not bad, str(bad))
    check("every answerable has >= 1 supporting chunk (fixed)",
          all(q.get("gold_chunks") or q.get("gold_chunks_fixed_s512_o77") for q in test + dev2 if q["type"] == "answerable"))
    check("no copy flags", not [q["id"] for q in test + dev2 if q.get("copy_flag")])
    # prompts
    frozen = json.load(open("prompts/FROZEN.json"))["prompts"]
    check("prompts a/b/c match FROZEN.json", all(load_prompt(k)["sha1"] == frozen[k]["sha1"] for k in ("a", "b", "c")))
    # generation options
    check("Ollama options deterministic + num_ctx explicit", OPTIONS["temperature"] == 0 and
          OPTIONS["seed"] == 42 and OPTIONS["num_ctx"] == 8192, json.dumps(OPTIONS))
    try:
        v = requests.get("http://localhost:11434/api/version", timeout=5).json()["version"]
    except Exception:
        v = "not running"
    check("Ollama version 0.40.4", v == "0.40.4", v)
    # retrieval config
    cfg = json.load(open("retrieval_config.json"))
    check("retrieval: dense Qwen3-Embedding-0.6B, pinned revision, why-instruction",
          cfg["embedding_model"] == "Qwen/Qwen3-Embedding-0.6B" and cfg["embedding_model_revision"].startswith("97b0c614")
          and cfg["query_instruction"].startswith("Given a question about why"))
    for suf in ("", "_dev2"):
        for ch, h in (("fixed_s512_o77", "311d0480"), ("struct_c256", "0611be80")):
            p = f"results/candidates_{ch}_k100{suf}.jsonl"
            ok = os.path.exists(p) and read_jsonl(p)[0]["_meta"]["chunk_set"] == h
            check(f"candidates{suf} {ch} on new-pool chunk set {h}", ok)
    # packing
    from pack_exp1 import relations
    check("packing = Exp 1 relations.expand_and_pack (rank scoring)", relations.RRF_K == 0)
    # tuning rule committed
    check("dev2 tuning rule file exists", os.path.exists("tuning_rule_dev2.md"))
    out = {"git_commit": git_commit(), "checks": checks,
           "passed": sum(c["ok"] for c in checks), "total": len(checks)}
    with open("results/sanity_check.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    for c in checks:
        print(("PASS " if c["ok"] else "FAIL ") + c["check"] + (f"  [{c['detail']}]" if c["detail"] and not c["ok"] else ""))
    print(f"{out['passed']}/{out['total']} passed")


if __name__ == "__main__":
    main()
