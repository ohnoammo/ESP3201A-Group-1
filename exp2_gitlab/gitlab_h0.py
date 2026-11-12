"""Hybrid (H0) on the GitLab Runner "why" questions. Rule: tuning_rule_hybrid_13nov.md (committed 12a0314).

    python gitlab_h0.py retrieve          # Run 1: BM25 index (new local copy), hybrid top-100 for all 70,
                                          #        dense regression check, -> results/retrieval_why_gitlab.csv
    python gitlab_h0.py retrieval-tests   # Run 1: 6 tests (Django + GitLab) -> results/retrieval_why_tests.csv
    python gitlab_h0.py generate          # Run 2: exp2_gitlab_A2000/gen_H0.jsonl (70 rows), F0's settings
    python gitlab_h0.py score             # Run 2: MiniCheck gate on H0, counts, tests, blind sheet

Modelled on ESP3201A_Exp2/sympy_h0.py. Imports exp2_gitlab_scale (never its score or build) and
exp2_gitlab_baselines (scoring regexes, flags) without editing either. Needs nltk 3.10.3:
    PYTHONPATH=C:/Users/kwekt/ESP3201A_local/pylib_h0 python gitlab_h0.py ...
rank_bm25 is not installed; it is only used by sparse_retrieval.py --selftest, not by retrieval.
"""
import argparse
import csv
import hashlib
import json
import os
import sys

import exp2_gitlab_scale as E
import exp2_gitlab_baselines as B

CH = "fixed_s512_o77"
CHUNK_SET = "111084af"
BM25_DIR = "C:/Users/kwekt/ESP3201A_local/gitlab_h0_bm25"      # new local copy, not an Exp 1 folder
DENSE = os.path.join(E.OUT, f"candidates_{CH}.jsonl")           # F0's saved dense candidates
HYB = os.path.join(E.OUT, "candidates_fixed_s512_o77_k100_hybrid.jsonl")
RES = "results"
DJANGO_CSV = os.path.join("..", "exp2_django", "results", "retrieval_why_django.csv")
GITLAB_CSV = os.path.join(RES, "retrieval_why_gitlab.csv")
RRF_K, DEPTH, K1, BB = 60, 100, 1.2, 0.75
F0_SHA1, F0_DIGEST, F0_OLLAMA = "072bd24371", "0edcdef34593", "0.40.4"
RETRIEVER = "hybrid RRF k=60 depth 100: code BM25 (k1 1.2, b 0.75, question text) + F0's saved dense top-100"


def write_csv(path, rows, fields=None):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def by_id():
    chunks, info = E.chunk_set(CH)
    assert info["chunk_set"] == CHUNK_SET, info
    return chunks, {c["chunk_id"]: c for c in chunks}


def gold_rank(chunk_ids, pr):
    prs = list(dict.fromkeys(int(c.split("_")[0]) for c in chunk_ids))
    return prs.index(pr) + 1 if pr in prs else None


def span_any(q, cks):
    cov = E.covered(q["spans"], cks, q["pr_number"], E.pool_docs()[q["pr_number"]]["text"])
    return bool(cov) and any(cov)


# ---------------------------------------------------------------- Run 1: retrieve
def cmd_retrieve(a):
    from qdrant_client import QdrantClient, models
    from exp1_common import build_retrievers
    from dense_retrieval import rrf_fuse
    qs = E.read_jsonl(E.QUESTIONS)
    assert len(qs) == 70
    chunks, cid = by_id()
    dmeta, dense = E._candidates(CH)
    assert dmeta["chunk_set"] == CHUNK_SET
    f0 = {r["id"]: r for r in E.read_jsonl(B.gen_path("F0"))}
    # regression check: dense contexts rebuilt from F0's saved candidates must equal gen_F0.jsonl, all 70
    bad = []
    for q in qs:
        cks = E.pack(dense[q["id"]]["chunk_ids"], cid, "score", q["exclude_prs"], 0.0, {})
        if ([c["chunk_id"] for c in cks] != f0[q["id"]]["context_chunk_ids"]
                or sum(c["tokens"] for c in cks) != f0[q["id"]]["context_tokens"]):
            bad.append(q["id"])
    print(f"dense regression check: {70 - len(bad)}/70 contexts equal gen_F0.jsonl; differ: {bad}")
    if bad:
        raise SystemExit("STOP: rebuilt dense contexts differ from F0 (rule: any difference stops the run)")
    os.makedirs(BM25_DIR, exist_ok=True)
    client = QdrantClient(path=os.path.join(BM25_DIR, "qdrant_bm25"))
    fns = build_retrievers(client, "gitlab_h0", CH, chunks, ["bm25"], None, k1=K1, b=BB, bm25_kind="code",
                           rrf_depth=DEPTH, rrf_k=RRF_K, chunk_set=CHUNK_SET)
    rows = []
    for q in qs:
        flt = None
        if q["exclude_prs"]:
            flt = models.Filter(must_not=[models.FieldCondition(
                key="pr_number", match=models.MatchAny(any=[int(n) for n in q["exclude_prs"]]))])
        bm = fns["bm25"](q["question"], DEPTH, flt)
        assert not any(int(h["pr_number"]) in {int(n) for n in q["exclude_prs"]} for h in bm), q["id"]
        dn = [{"chunk_id": c} for c in dense[q["id"]]["chunk_ids"][:DEPTH]]
        hits = rrf_fuse([bm, dn], k=100, rrf_k=RRF_K)       # same order as make_hybrid_search([bm25, dense])
        rows.append({"id": q["id"], "chunk_ids": [h["chunk_id"] for h in hits], "scores": [h["score"] for h in hits],
                     "bm25_top100": [h["chunk_id"] for h in bm]})
    meta = {"retriever": RETRIEVER, "chunking": CH, "chunk_set": CHUNK_SET, "query_prompt": dmeta["query_prompt"],
            "dense_source": DENSE, "bm25_index": BM25_DIR, "rule": "tuning_rule_hybrid_13nov.md",
            "git_commit": B.git_head(), "dense_regression_check": "70/70 contexts equal gen_F0.jsonl"}
    E.write_jsonl(HYB, [{"_meta": meta}] + rows)
    print(f"{len(rows)} questions -> {HYB}")
    hyb = {r["id"]: r for r in rows}
    out = []
    for q in qs:
        if q["type"] != "answerable":
            continue
        row = {"repo": "gitlab-runner", "id": q["id"], "pr_number": q["pr_number"]}
        for name, cand in (("dense", dense[q["id"]]["chunk_ids"]), ("hybrid", hyb[q["id"]]["chunk_ids"])):
            rank = gold_rank(cand, q["pr_number"])
            cks = E.pack(cand, cid, "score", q["exclude_prs"], 0.0, {})
            row[f"{name}_gold_rank"] = rank
            row[f"{name}_hit5"] = int(rank is not None and rank <= 5)
            row[f"{name}_rr5"] = round(1 / rank, 6) if rank is not None and rank <= 5 else 0.0
            row[f"{name}_span"] = int(span_any(q, cks))
        assert row["dense_span"] == int(f0[q["id"]]["span_in_context"]["any"]), q["id"]
        row["identical_context"] = int(
            [c["chunk_id"] for c in E.pack(hyb[q["id"]]["chunk_ids"], cid, "score", q["exclude_prs"], 0.0, {})]
            == f0[q["id"]]["context_chunk_ids"])
        row["git_commit"] = meta["git_commit"]
        out.append(row)
    assert len(out) == 52
    write_csv(GITLAB_CSV, out)
    for name in ("dense", "hybrid"):
        print(name, {k: round(sum(r[f"{name}_{k}"] for r in out), 3) for k in ("hit5", "rr5", "span")})
    print(f"52 answerables -> {GITLAB_CSV}")


# ---------------------------------------------------------------- Run 1: tests
def cmd_retrieval_tests(a):
    import numpy as np
    import exp2_scale_stats as S
    tests = []
    for repo, path, label in (("django", DJANGO_CSV, "post hoc"), ("gitlab-runner", GITLAB_CSV, "exploratory")):
        rows = read_csv(path)
        n = len(rows)
        assert n == (50 if repo == "django" else 52), (repo, n)
        for outcome in ("hit5", "span"):
            d = [int(r[f"dense_{outcome}"]) for r in rows]
            h = [int(r[f"hybrid_{outcome}"]) for r in rows]
            b = sum(y and not x for x, y in zip(d, h))
            c = sum(x and not y for x, y in zip(d, h))
            tests.append({"repo": repo, "status": label, "outcome": outcome, "n": n, "dense": sum(d), "hybrid": sum(h),
                          "b_only_hybrid": b, "c_only_dense": c, "test": "exact McNemar, two-sided",
                          "p": S.mcnemar(b, c), "diff_mean": round((sum(h) - sum(d)) / n, 4),
                          "ids_only_hybrid": " ".join(r["id"] for r, x, y in zip(rows, d, h) if y and not x),
                          "ids_only_dense": " ".join(r["id"] for r, x, y in zip(rows, d, h) if x and not y)})
        dd = np.array([float(r["dense_rr5"]) for r in rows])
        hh = np.array([float(r["hybrid_rr5"]) for r in rows])
        diff = hh - dd
        obs = diff.mean()
        signs = np.random.default_rng(0).choice([-1.0, 1.0], size=(10000, n))
        perm = (signs * diff).mean(axis=1)
        p = (1 + int(np.sum(np.abs(perm) >= abs(obs) - 1e-12))) / (1 + 10000)
        rng = np.random.default_rng(0)
        boot = np.array([diff[rng.integers(0, n, n)].mean() for _ in range(1000)])
        lo, hi = np.percentile(boot, [2.5, 97.5])
        tests.append({"repo": repo, "status": label, "outcome": "mrr5", "n": n, "dense": round(dd.mean(), 4),
                      "hybrid": round(hh.mean(), 4), "b_only_hybrid": int((diff > 0).sum()),
                      "c_only_dense": int((diff < 0).sum()),
                      "test": "paired sign-flip permutation, 10,000, seed 0; bootstrap 1,000, seed 0", "p": p,
                      "diff_mean": round(float(obs), 4), "ci95_lo": round(float(lo), 4), "ci95_hi": round(float(hi), 4),
                      "ids_only_hybrid": " ".join(r["id"] for r, x in zip(rows, diff) if x > 0),
                      "ids_only_dense": " ".join(r["id"] for r, x in zip(rows, diff) if x < 0)})
    assert len(tests) == 6
    for t, hp in zip(tests, S.holm([t["p"] for t in tests])):
        t["holm_p"] = hp
        t["family"] = "retrieval-why 6"
    fields = ["family", "repo", "status", "outcome", "n", "dense", "hybrid", "diff_mean", "ci95_lo", "ci95_hi",
              "b_only_hybrid", "c_only_dense", "test", "p", "holm_p", "ids_only_hybrid", "ids_only_dense"]
    write_csv(os.path.join(RES, "retrieval_why_tests.csv"), tests, fields)
    for t in tests:
        print({k: t.get(k) for k in fields[:15]})


# ---------------------------------------------------------------- Run 2: generate
def cmd_generate(a):
    import requests
    p = E.sympy_prompt()
    assert p["sha1"] == F0_SHA1, p["sha1"]
    version = requests.get(f"{E.OLLAMA}/api/version", timeout=30).json().get("version")
    tags = requests.get(f"{E.OLLAMA}/api/tags", timeout=30).json()["models"]
    digest = next((m["digest"][:12] for m in tags if m["name"] == E.MODEL), None)
    print(f"Ollama {version}, {E.MODEL} digest {digest}")
    if (version, digest) != (F0_OLLAMA, F0_DIGEST):
        raise SystemExit("STOP: Ollama version or model digest differs from F0")
    rows = E.read_jsonl(HYB)
    meta, hyb = rows[0]["_meta"], {r["id"]: r for r in rows[1:]}
    assert len(hyb) == 70
    E.ARMS["H0"] = E.ARMS["F0"]
    E.ARM_ALPHA["H0"] = 0.0
    E._candidates = lambda ch: (meta, hyb)      # only H0 is generated in this process
    E.cmd_generate(argparse.Namespace(arms=["H0"], model=E.MODEL))
    out = E.read_jsonl(B.gen_path("H0"))
    print(f"gen_H0.jsonl: {len(out)} rows")


# ---------------------------------------------------------------- Run 2: score
def h0_contexts(qs, cid):
    hyb = {r["id"]: r for r in E.read_jsonl(HYB)[1:]}
    return {q["id"]: E.pack(hyb[q["id"]]["chunk_ids"], cid, "score", q["exclude_prs"], 0.0, {}) for q in qs}


def run_gate(qs_list, gens, ctx):
    """MiniCheck gate on H0 strict-answered rows; same code path as exp2_gitlab_baselines.cmd_gate."""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    qs = {q["id"]: q for q in qs_list}
    path = os.path.join(RES, "h0_gitlab_gate_rows.jsonl")
    done = {x["id"] for x in E.read_jsonl(path)} if os.path.exists(path) else set()
    todo = [r for r in gens["H0"].values() if B.flags(r, qs[r["id"]])["answered_strict"] and r["id"] not in done]
    if todo:
        sys.path.append(B.EXP2_DIR)
        import faithfulness as FA
        import gate_eval as GE
        assert GE.THRESHOLD == 0.5
        mc = FA.MiniCheck()
        rev = getattr(mc.m.config, "_commit_hash", None) or ""
        print(f"MiniCheck on {FA.DEV}, revision {rev}; {len(todo)} rows")
        if not (rev.startswith("96eafd01") and FA.DEV == "cuda"):
            raise SystemExit(f"gate skipped: MiniCheck revision {rev!r} on {FA.DEV}")
        with open(path, "a", encoding="utf-8") as out:
            for r in todo:
                cks = ctx[r["id"]]
                assert [c["chunk_id"] for c in cks] == r["context_chunk_ids"], r["id"]
                cited = set(FA.CITE.findall(r["response"]))
                prem = [c["text"] for c in cks if E.short_id(c["chunk_id"]) in cited]
                sents = FA.sentences(r["response"])
                sc = [mc.score(prem, s) for s in sents] if prem else []
                mn = min(sc) if sc else None
                kept = GE.passes({"answered": True, "score": mn}, GE.THRESHOLD)
                out.write(json.dumps({"arm": "H0", "id": r["id"], "type": r["type"], "n_cited_in_context": len(prem),
                                      "n_sentences": len(sents), "minicheck_cited_min": mn, "kept": kept,
                                      "gated": not kept, "model_revision": rev}) + "\n")
                out.flush()
    return {x["id"]: x for x in E.read_jsonl(path)}


def cmd_score(a):
    import exp2_scale_stats as S
    qs_list = E.read_jsonl(E.QUESTIONS)
    qs = {q["id"]: q for q in qs_list}
    _, cid = by_id()
    ctx = h0_contexts(qs_list, cid)
    gens = B.load_gens(("F0", "H0"))
    assert len(gens["F0"]) == 70 and len(gens["H0"]) == 70, {k: len(v) for k, v in gens.items()}
    for i, r in gens["H0"].items():
        assert [c["chunk_id"] for c in ctx[i]] == r["context_chunk_ids"], i
        assert r["prompt_sha1"] == F0_SHA1 and r["model_digest"] == F0_DIGEST and r["ollama_version"] == F0_OLLAMA
    fl = {arm: {i: B.flags(r, qs[i]) for i, r in g.items()} for arm, g in gens.items()}
    ans = [i for i in gens["F0"] if qs[i]["type"] == "answerable"]
    un = [i for i in gens["F0"] if qs[i]["type"] in B.UNANS]
    un16 = [i for i in un if i not in B.DOUBTFUL]
    assert (len(ans), len(un), len(un16)) == (52, 18, 16)
    same_ctx = [i for i in gens["F0"] if gens["F0"][i]["context_chunk_ids"] == gens["H0"][i]["context_chunk_ids"]]
    same_ctx_diff_answer = [i for i in same_ctx if gens["F0"][i]["response"] != gens["H0"][i]["response"]]
    gate = run_gate(qs_list, gens, ctx)
    f0_gate = {x["id"]: x for x in E.read_jsonl(os.path.join(RES, "baselines_gate_rows.jsonl")) if x["arm"] == "F0"}

    def kept(arm, i, key):
        g = gate if arm == "H0" else f0_gate
        return fl[arm][i][key] and fl[arm][i]["answered_strict"] and g[i]["kept"]

    counts = []
    for arm in ("F0", "H0"):
        f, g = fl[arm], gens[arm]
        counts.append({
            "arm": arm, "n_rows": len(g),
            "unanswerable_answered_lenient_of18": sum(f[i]["answered_lenient"] for i in un),
            "unanswerable_answered_lenient_excl_doubtful_of16": sum(f[i]["answered_lenient"] for i in un16),
            "unanswerable_answered_strict_of18": sum(f[i]["answered_strict"] for i in un),
            "no_reason_answered_lenient_of8": sum(f[i]["answered_lenient"] for i in un if qs[i]["type"] == "no_reason"),
            "removed_answered_lenient_of10": sum(f[i]["answered_lenient"] for i in un if qs[i]["type"] == "removed"),
            "answerable_answered_lenient_of52": sum(f[i]["answered_lenient"] for i in ans),
            "answerable_answered_strict_of52": sum(f[i]["answered_strict"] for i in ans),
            "overlap_cited_of52": sum(f[i]["overlap_cited"] for i in ans),
            "span_in_context_of52": sum(bool(g[i]["span_in_context"] and g[i]["span_in_context"]["any"]) for i in ans),
            "empty_answers": sum(f[i]["empty"] for i in g),
            "identical_context_with_other_arm_of70": len(same_ctx),
            "identical_context_but_different_answer": len(same_ctx_diff_answer),
            "gate_unanswerable_answered_after_of18": sum(kept(arm, i, "answered_lenient") for i in un),
            "gate_answerable_answered_after_of52": sum(kept(arm, i, "answered_lenient") for i in ans),
            "gate_source": "results/h0_gitlab_gate_rows.jsonl" if arm == "H0" else "results/baselines_gate_rows.jsonl (12 Nov)"})
    write_csv(os.path.join(RES, "h0_gitlab_counts.csv"), counts)

    tests = []

    def family(name, key, outcomes, adjust):
        fam = []
        for outcome, ids in outcomes:
            b = sum(fl["H0"][i][key] and not fl["F0"][i][key] for i in ids)
            c = sum(fl["F0"][i][key] and not fl["H0"][i][key] for i in ids)
            fam.append({"family": name, "scoring": key, "outcome": outcome, "n": len(ids),
                        "F0": sum(fl["F0"][i][key] for i in ids), "H0": sum(fl["H0"][i][key] for i in ids),
                        "b_only_H0": b, "c_only_F0": c, "p": S.mcnemar(b, c),
                        "min_attainable_p": S.mcnemar(b + c, 0),
                        "ids_only_H0": " ".join(i for i in ids if fl["H0"][i][key] and not fl["F0"][i][key]),
                        "ids_only_F0": " ".join(i for i in ids if fl["F0"][i][key] and not fl["H0"][i][key])})
        hs = S.holm([t["p"] for t in fam]) if adjust else [""] * len(fam)
        for t, h in zip(fam, hs):
            t["holm_p"] = h
        tests.extend(fam)
    family("hybrid-gitlab 2 (primary, Holm over 2)", "answered_lenient",
           [("unanswerable_answered", un), ("answerable_answered", ans)], True)
    family("secondary: strict (own Holm over 2)", "answered_strict",
           [("unanswerable_answered", un), ("answerable_answered", ans)], True)
    family("sensitivity: excl. nr3177, nr4460 (unadjusted)", "answered_lenient",
           [("unanswerable_answered", un16)], False)
    family("descriptive: overlap-cited (no test claimed)", "overlap_cited", [("overlap_cited", ans)], False)
    write_csv(os.path.join(RES, "h0_gitlab_tests.csv"), tests)

    gate_rows = []
    for arm in ("F0", "H0"):
        g = gate if arm == "H0" else f0_gate
        for scoring, key in (("lenient", "answered_lenient"), ("strict", "answered_strict")):
            gate_rows.append({"arm": arm, "scoring": scoring,
                              "unanswerable_answered_before": sum(fl[arm][i][key] for i in un),
                              "unanswerable_answered_after": sum(kept(arm, i, key) for i in un),
                              "answerable_answered_before": sum(fl[arm][i][key] for i in ans),
                              "answerable_answered_after": sum(kept(arm, i, key) for i in ans),
                              "answered_no_valid_cited_premise": sum(fl[arm][i][key] and g[i]["minicheck_cited_min"] is None
                                                                     for i in g),
                              "unanswerable_kept_ids": " ".join(i for i in un if kept(arm, i, key)),
                              "note": "counts only" if arm == "H0" else "reference: 12 Nov baselines gate rows"})
    write_csv(os.path.join(RES, "h0_gitlab_gate.csv"), gate_rows)

    # blind sheet: H0 answered (strict, a superset of lenient) answerables whose stripped text differs from F0's
    items = []
    for i in ans:
        r = gens["H0"][i]
        if fl["H0"][i]["answered_strict"] and E.strip_citations(r["response"]) != E.strip_citations(gens["F0"][i]["response"]):
            items.append((hashlib.sha256(f"h0-gitlab-13nov:{i}".encode()).hexdigest(), r))
    items.sort(key=lambda t: t[0])
    key, sheet = {}, []
    for n, (_, r) in enumerate(items, 1):
        bid, q = f"HG{n:03d}", qs[r["id"]]
        key[bid] = {"arm": "H0", "id": r["id"]}
        sheet.append([bid, q["question"], q["answer"], " || ".join(q["quotes"]), E.strip_citations(r["response"]), "", ""])
    os.makedirs(B.KEYS, exist_ok=True)
    with open(os.path.join(B.KEYS, "h0_gitlab_blind_key.json"), "w", encoding="utf-8") as f:
        json.dump(key, f, indent=1)
    with open(os.path.join(RES, "h0_gitlab_blind_sheet_blank.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["blind_id", "question", "gold_answer", "gold_quotes", "model_answer", "label", "reason"])
        w.writerows(sheet)

    for c in counts:
        print(c)
    for t in tests:
        print({k: t[k] for k in ("family", "outcome", "n", "F0", "H0", "b_only_H0", "c_only_F0", "p", "holm_p",
                                 "ids_only_H0", "ids_only_F0")})
    for g in gate_rows:
        print(g)
    print(f"identical contexts {len(same_ctx)}/70; of those, different answer: {same_ctx_diff_answer}")
    print(f"blind sheet: {len(sheet)} rows -> results/h0_gitlab_blind_sheet_blank.csv (key in results/keys/)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["retrieve", "retrieval-tests", "generate", "score"])
    args = ap.parse_args()
    {"retrieve": cmd_retrieve, "retrieval-tests": cmd_retrieval_tests, "generate": cmd_generate,
     "score": cmd_score}[args.cmd](args)
