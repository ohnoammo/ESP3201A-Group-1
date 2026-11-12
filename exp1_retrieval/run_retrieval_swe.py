"""Experiment 1 on SWE-bench Verified (Django PRs): chunking (fixed vs structural) x
retrieval (BM25 / dense / hybrid). No LLM.

Query = the bug report (problem_statement; optional second set: first line only).
Correct answer = the fixing PR. Search pile = the PR pool downloaded by github_prs.py:
  pool B: per query, only PRs created within [bug date, bug date + window] (date filter,
          identical for every retriever); pool A: one shared pool, no filter.

Usage:
    # pilot: 5 dev tasks, small pool A (download it first: github_prs.py download --pool A
    #        --n-distractors 200)
    python run_retrieval_swe.py --split dev --max-tasks 5 --pool A --n-distractors 200 --tag _pilot
    # tuning grid on dev (50)
    python run_retrieval_swe.py --split dev --fixed-sizes 128 256 512 --overlap-fracs 0 0.15 \\
        --struct-caps 256 512 --k1s 0.9 1.2 1.5 --bs 0.5 0.75 0.9 --tag _dev
    python select_chunking.py results/swe_exp1_dev.json
    # untuned defaults on test (fixed 256/0, structural cap 512, k1 1.2, b 0.75)
    python run_retrieval_swe.py --split test --size-matched --tag _test_untuned

Metrics (metrics.py): MAIN PR-level Hit@5 / MRR@5; SECONDARY over the top-5 chunks:
chunk-level Hit/MRR and line-level Recall/Precision/F1 against the fixing PR's changed lines
(all files, plus "src_" = only files in SWE-bench's `patch`).
Breakdown: with vs without copied-text PRs. (No 1-file vs multi-file breakdown: too few
multi-file tasks; the share of single-source-file tasks is reported descriptively.)
Saved to results/swe_exp1<tag>.{json,csv} + _per_query.csv.
"""
import argparse
import os
import time

from qdrant_client import QdrantClient

from swebench_loader import load_swebench
from make_swe_split import load_split
from github_prs import load_pr, load_pool, pool_name, DAY
from pr_document import build_document, evidence_ranges, shares_ngram
from metrics import score_question_multidoc, pr_level
from sparse_retrieval import date_window_filter
from dense_retrieval import Qwen3Embedder, DEFAULT_MODEL, TASKS
from exp1_common import (RETRIEVERS, chunk_configs, cfg_fields, make_chunks,
                         build_retrievers, save_results)
from stats import bootstrap_ci
from relations import build_links, expand_and_pack, token_counter
import exp1_common

LINE_METRICS = ("recall", "precision", "f1", "hit", "mrr")
BUDGET_METRICS = ("budget_recall", "budget_precision", "budget_f1", "budget_hit",
                  "gold_in_budget", "budget_src_recall", "n_linked", "budget_chunks",
                  "budget_tokens_used")


def load_docs(repo, numbers):
    docs, missing = {}, []
    for n in numbers:
        pr = load_pr(repo, n)
        if pr is None or pr.get("not_found"):
            missing.append(n)
            continue
        d = build_document(pr)
        if d["text"].strip():
            docs[d["paper_id"]] = d
    if missing:
        print(f"WARNING: {len(missing)} pool PRs are not downloaded / not found; skipped")
    return docs


def select_tasks(args):
    tasks = load_swebench(args.repo)
    if args.split != "all":
        ids = set(load_split(args.split_file)[args.split])
        tasks = [t for t in tasks if t["instance_id"] in ids]
    return tasks[:args.max_tasks] if args.max_tasks else tasks


def evaluate(fn, tasks, docs, query_set, k, depth, window_days, pool,
             alphas=(0.0,), links=None, chunk_by_id=None, budget=2560, ntok=None):
    """Score one search_fn on all tasks. Each query is searched ONCE; then, for every relation
    factor alpha, the ranking is expanded with linked chunks (relations.py) and packed into
    the token budget. Returns one per-query row per alpha. PR-level and top-k metrics come
    from the plain ranking (identical for every alpha); budget_* metrics from the packed
    chunks (what an LLM would receive)."""
    doc_lines = {pid: d["line_spans"] for pid, d in docs.items()}
    links, chunk_by_id, ntok = links or {}, chunk_by_id or {}, ntok or token_counter()
    out = []
    for t in tasks:
        gold = str(t["pr_number"])
        q = t["problem_statement"] if query_set == "full" else t["short_query"]
        bug_ts = min(t["created_ts"], docs[gold]["created_ts"] or t["created_ts"])
        flt = (date_window_filter(bug_ts, bug_ts + window_days * DAY)       # always holds gold
               if pool == "B" else None)
        ranked = fn(q, depth, flt)
        row = {"instance_id": t["instance_id"], "pr_number": t["pr_number"]}
        row |= pr_level(ranked, gold, k)
        ev = evidence_ranges(docs[gold])
        line = score_question_multidoc(doc_lines, {gold: ev}, ranked, k) if ev else {}
        row |= {m: line.get(m) for m in LINE_METRICS}
        src = evidence_ranges(docs[gold], set(t["patch_files"]))
        sline = score_question_multidoc(doc_lines, {gold: src}, ranked, k) if src else {}
        row |= {f"src_{m}": sline.get(m) for m in ("recall", "precision", "f1")}
        row["top_prs"] = " ".join(dict.fromkeys(c["paper_id"] for c in ranked))[:200]
        row["top5_distinct_prs"] = len({c["paper_id"] for c in ranked[:k]})
        for a in alphas:
            packed = expand_and_pack(ranked, a, links, chunk_by_id, budget, ntok)
            n = len(packed)
            bl = score_question_multidoc(doc_lines, {gold: ev}, packed, n) if ev and n else {}
            bs = score_question_multidoc(doc_lines, {gold: src}, packed, n) if src and n else {}
            out.append(row | {"alpha": a,
                              "budget_recall": bl.get("recall"),
                              "budget_precision": bl.get("precision"),
                              "budget_f1": bl.get("f1"), "budget_hit": bl.get("hit"),
                              "gold_in_budget": float(any(c["paper_id"] == gold for c in packed)),
                              "budget_src_recall": bs.get("recall"),
                              "n_linked": sum(c["linked"] for c in packed),
                              "budget_chunks": n,
                              "budget_tokens_used": sum(ntok(c["chunk_id"], c) for c in packed)})
    return out


def aggregate(rows, groups):
    """Mean of every metric per group, with bootstrap CIs for the PR-level metrics."""
    res = {}
    for g, keep in groups.items():
        sel = [r for r in rows if keep(r)]
        if not sel:
            continue
        m = {"n": len(sel)}
        for key in ("pr_hit", "pr_mrr", *LINE_METRICS, "src_recall", "src_precision", "src_f1",
                    "top5_distinct_prs", *BUDGET_METRICS):
            vals = [r[key] for r in sel if r.get(key) is not None]
            m[key] = sum(vals) / len(vals) if vals else None
        for key in ("pr_hit", "pr_mrr", "budget_recall"):
            vals = [r[key] for r in sel if r.get(key) is not None]
            m[f"{key}_ci"] = bootstrap_ci(vals) if vals else None
        res[g] = m
    return res


def main(args):
    tasks = select_tasks(args)
    pname = pool_name(args.pool, args.window_days, args.n_distractors)
    pool = load_pool(args.repo, pname)
    docs = load_docs(args.repo, pool["numbers"])
    kept = [t for t in tasks if str(t["pr_number"]) in docs]
    if len(kept) < len(tasks):
        print(f"WARNING: {len(tasks) - len(kept)} tasks dropped: fixing PR not downloaded")
    tasks = kept
    doc_list = [docs[k] for k in sorted(docs, key=int)]
    print(f"{len(tasks)} tasks ({args.split}), pool {pname}: {len(doc_list)} PRs")

    # copied-text check (bug report vs its fixing PR)
    copy_counts = {n: sum(shares_ngram(t["problem_statement"], docs[str(t["pr_number"])]["text"], n)
                          for t in tasks) for n in sorted(set(args.copy_ns) | {args.copy_n})}
    copied = {t["instance_id"] for t in tasks
              if shares_ngram(t["problem_statement"], docs[str(t["pr_number"])]["text"],
                              args.copy_n)}
    print(f"Copied-text check: fixing PRs sharing >= n words with their bug report: "
          + ", ".join(f"n={n}: {c}" for n, c in copy_counts.items()))

    client = QdrantClient(path=args.qdrant_path)
    exp1_common.REBUILD_INDEXES = args.rebuild_indexes
    embedder = None
    if {"dense", "hybrid"} & set(args.retrievers):
        slug = args.model.split("/")[-1].lower()
        embedder = Qwen3Embedder(args.model, task=TASKS["swe"], device=args.device,
                                 batch_size=args.batch_size,
                                 cache_path=os.path.join("emb_cache", f"{slug}_swe.npz"))
        embedder.embed_queries([t["problem_statement"] for t in tasks]
                               + [t["short_query"] for t in tasks])

    cfgs = chunk_configs(args.fixed_sizes, args.overlap_fracs, args.struct_caps, args.chunkers)
    cfgs.sort(key=lambda c: c["method"] != "structural")        # structural first
    # No 1-file vs multi-file breakdown: too few multi-file tasks (django test: 22/181) for a
    # reliable comparison. Reported descriptively instead (n_single_source_file in meta).
    groups = {"all": lambda r: True,
              "not_copied": lambda r: not r["copied"],
              "copied": lambda r: r["copied"]}
    n_single = sum(len(t["patch_files"]) == 1 for t in tasks)
    print(f"Tasks changing a single source file (SWE-bench patch): {n_single}/{len(tasks)} "
          f"({n_single / max(1, len(tasks)):.0%})")
    rows, per_query, done, dense_texts = [], [], set(), set()
    i = 0
    while i < len(cfgs):
        cfg = cfgs[i]
        i += 1
        if cfg["name"] in done:
            continue
        done.add(cfg["name"])
        chunks, info = make_chunks(doc_list, cfg, "swe")
        dense_texts.update(c["text"] for c in chunks)       # identical texts embed once
        if args.size_matched and cfg["method"] == "structural":       # add matched fixed run
            size = round(info["avg_tokens"])
            extra = {"name": f"fixed_s{size}_o0", "method": "fixed", "size": size,
                     "overlap": 0, "size_matched_to": cfg["name"]}
            if extra["name"] not in done:
                cfgs.append(extra)
        links = build_links(chunks, docs, kinds=("code",))     # Exp 1: links only add code
        chunk_by_id = {c["chunk_id"]: c for c in chunks}
        ntok = token_counter()
        method_alphas = args.fixed_alphas if cfg["method"] == "fixed" else args.struct_alphas
        alphas = method_alphas if method_alphas is not None else args.alphas
        bm25_grid = [(k1, b) for k1 in args.k1s for b in args.bs]
        per_method = args.fixed_k1b if cfg["method"] == "fixed" else args.struct_k1b
        if per_method:                                   # tuned k1/b for this chunking method
            bm25_grid = [tuple(per_method)]
        for gi, (k1, b) in enumerate(bm25_grid):
            rets = [r for r in args.retrievers if r != "dense" or gi == 0]   # dense: once
            fns = build_retrievers(client, "swe", cfg["name"], chunks, rets, embedder,
                                   k1=k1, b=b, bm25_kind=args.bm25,
                                   chunk_set=info["chunk_set"],
                                   rrf_depth=args.depth, rrf_k=args.rrf_k)
            for name, fn in fns.items():
                r_alphas = alphas
                tuned = args.alpha_map.get((cfg["method"], name))
                if tuned is not None:                  # per-retriever tuned alpha (+ alpha 0)
                    r_alphas = sorted({0.0, tuned})
                for qs in args.query_sets:
                    t0 = time.time()
                    pq = evaluate(fn, tasks, docs, qs, args.k, args.depth, args.window_days,
                                  args.pool, r_alphas, links, chunk_by_id, args.budget_tokens,
                                  ntok)
                    base = {"chunking": cfg["name"], "retriever": name, "query_set": qs,
                            "k": args.k, "k1": k1 if name != "dense" else None,
                            "b": b if name != "dense" else None,
                            "budget": args.budget_tokens,
                            "size_matched_to": cfg.get("size_matched_to")} | cfg_fields(cfg)
                    n_src = {t["instance_id"]: len(t["patch_files"]) for t in tasks}
                    for r in pq:
                        r["n_files"] = docs[str(r["pr_number"])]["n_files"]   # whole PR
                        r["n_source_files"] = n_src[r["instance_id"]]          # SWE patch
                        r["copied"] = r["instance_id"] in copied
                    per_query += [base | r for r in pq]
                    for a in r_alphas:
                        for g, m in aggregate([r for r in pq if r["alpha"] == a], groups).items():
                            rows.append(base | {"alpha": a, "group": g} | m | info
                                        | {"search_seconds": time.time() - t0})
                        s = next(r for r in rows[::-1] if r["group"] == "all")
                        print(f"  {cfg['name']:<16}{name:<7}{qs:<6}k1={k1} b={b} alpha={a:<5}"
                              f" PR Hit@{args.k}={s['pr_hit']:.3f} PR MRR@{args.k}={s['pr_mrr']:.3f}"
                              f"  budget Recall={(s['budget_recall'] or 0):.3f}"
                              f" Prec={(s['budget_precision'] or 0):.3f}"
                              f" linked={(s['n_linked'] or 0):.1f}/{(s['budget_chunks'] or 0):.1f}")

    print(f"\nSWE-bench {args.repo} ({len(tasks)} tasks, {args.split}), pool {pname}, k={args.k}")
    print(f"Budget metrics: what an LLM would receive = top chunks (plus linked chunks when "
          f"alpha > 0) packed into {args.budget_tokens} tokens")
    print(f"{'chunking':<18}{'retriever':<9}{'query':<7}{'alpha':<6}{'group':<12}{'n':>4}"
          f"{'PR Hit':>8}{'PR MRR':>8}{'bud Rec':>8}{'bud Prec':>9}{'gold in':>8}"
          f"{'linked':>7}{'tokens':>8}")
    for r in rows:
        f = lambda v: f"{v:.3f}" if v is not None else "  -  "
        print(f"{r['chunking']:<18}{r['retriever']:<9}{r['query_set']:<7}{r['alpha']:<6}"
              f"{r['group']:<12}{r['n']:>4}{f(r['pr_hit']):>8}{f(r['pr_mrr']):>8}"
              f"{f(r['budget_recall']):>8}{f(r['budget_precision']):>9}"
              f"{f(r['gold_in_budget']):>8}{(r['n_linked'] or 0):>7.1f}{r['avg_tokens']:>8.0f}")

    est_h = len(dense_texts) / args.embed_rate / 3600
    print(f"\nDense embedding estimate for these chunk settings: {len(dense_texts):,} unique chunks"
          f" -> ~{est_h:.1f} h at {args.embed_rate} chunks/s (cached chunks are not re-embedded)")
    meta = {"repo": args.repo, "split": args.split, "n_tasks": len(tasks), "pool": pname,
            "unique_chunks_to_embed": len(dense_texts), "embed_estimate_hours": est_h,
            "pool_size": len(doc_list), "window_days": args.window_days if args.pool == "B" else None,
            "pool_filter": {k: pool.get(k) for k in ("max_files", "max_tokens", "n_excluded",
                                                      "n_not_found", "fixing_over_limits")},
            "n_single_source_file": n_single,
            "k": args.k, "depth": args.depth, "bm25_tokenizer": args.bm25,
            "model": args.model if embedder else None,
            "instruction": embedder.query_prompt if embedder else None,
            "rrf_k": args.rrf_k, "budget_tokens": args.budget_tokens,
            "relation_links": "code only (description->hunks, review thread->its hunk, "
                              "hunk->other hunks; fixed: neighbour chunks)",
            "copy_n": args.copy_n, "copy_counts": copy_counts,
            "n_copied": len(copied),
            "new_embed_seconds": embedder.embed_seconds if embedder else None,
            "truncated_chunks": embedder.n_truncated if embedder else None,
            "truncated_queries": embedder.n_truncated_queries if embedder else None,
            "note": "BM25 IDF is computed over the whole collection, not each filtered pool"}
    save_results(rows, os.path.join("results", f"swe_exp1{args.tag}"), meta, per_query)
    return rows


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="django/django")
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--split-file", default="swe_split_ids.json")
    ap.add_argument("--max-tasks", type=int, default=None)
    ap.add_argument("--pool", choices=["A", "B", "H"], default="B",
                    help="A = random distractors, H = hard (look-alike, same module), B = date windows")
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--n-distractors", type=int, default=2000)
    ap.add_argument("--query-sets", nargs="+", default=["full"], choices=["full", "short"])
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--depth", type=int, default=100, help="chunks retrieved per query")
    ap.add_argument("--retrievers", nargs="+", default=list(RETRIEVERS), choices=RETRIEVERS)
    ap.add_argument("--chunkers", nargs="+", default=["fixed", "structural"],
                    choices=["fixed", "structural"])
    ap.add_argument("--fixed-sizes", nargs="+", type=int, default=[256], help="tokens")
    ap.add_argument("--overlap-fracs", nargs="+", type=float, default=[0.0],
                    help="fixed overlap as a fraction of the size, e.g. 0 0.15")
    ap.add_argument("--struct-caps", nargs="+", type=int, default=[512], help="tokens")
    ap.add_argument("--size-matched", action="store_true",
                    help="also run fixed chunks sized to the structural chunks' average")
    ap.add_argument("--k1s", nargs="+", type=float, default=[1.2])
    ap.add_argument("--bs", nargs="+", type=float, default=[0.75])
    ap.add_argument("--fixed-k1b", nargs=2, type=float, default=None, metavar=("K1", "B"),
                    help="BM25 k1 b for fixed chunks (overrides --k1s/--bs; from tuning)")
    ap.add_argument("--struct-k1b", nargs=2, type=float, default=None, metavar=("K1", "B"),
                    help="BM25 k1 b for structural chunks (overrides --k1s/--bs)")
    ap.add_argument("--bm25", choices=["code", "fastembed"], default="code",
                    help="BM25 tokenizer: code-aware (default) or FastEmbed Qdrant/bm25")
    ap.add_argument("--budget-tokens", type=int, default=2560,
                    help="token budget for what an LLM receives (= 5 x fixed-512 chunks)")
    ap.add_argument("--alphas", nargs="+", type=float, default=[0.0],
                    help="relation factor(s): 0 = no links; e.g. 0 0.25 0.5 1 for tuning")
    ap.add_argument("--fixed-alphas", nargs="+", type=float, default=None,
                    help="relation factor(s) for fixed chunks (overrides --alphas)")
    ap.add_argument("--struct-alphas", nargs="+", type=float, default=None,
                    help="relation factor(s) for structural chunks (overrides --alphas)")
    ap.add_argument("--alpha-map", nargs="+", default=[], metavar="METHOD.RETRIEVER=ALPHA",
                    help="tuned alpha per chunking method + retriever, e.g. fixed.dense=0.5 "
                         "structural.bm25=0 (each is run next to alpha 0)")
    ap.add_argument("--copy-n", type=int, default=10)
    ap.add_argument("--copy-ns", nargs="+", type=int, default=[8, 10, 12],
                    help="also count copied-text PRs at these n (reported in meta)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--device", default=None, help="cuda / cpu (default: auto)")
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--embed-rate", type=float, default=4.0,
                    help="chunks/s for the dense time estimate (~4 on an RTX 3050 Ti laptop)")
    ap.add_argument("--rrf-k", type=int, default=60)
    ap.add_argument("--qdrant-path", default="qdrant_exp1")
    ap.add_argument("--rebuild-indexes", action="store_true",
                    help="rebuild Qdrant collections even if a complete one already exists")
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)
    amap = {}
    for item in a.alpha_map:                         # "fixed.dense=0.5" -> {("fixed","dense"): 0.5}
        key, val = item.split("=")
        method, ret = key.split(".")
        amap[(method, ret)] = float(val)
    a.alpha_map = amap
    return a


if __name__ == "__main__":
    main(parse_args())
