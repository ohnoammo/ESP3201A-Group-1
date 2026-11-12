"""Exp 2 baselines on GitLab Runner (rule: tuning_rule_baselines.md). Exploratory; not in the Findings.

  python exp2_gitlab_baselines.py meta                  Ollama version, model digest, `ollama show` -> run_meta_baselines.json
  python exp2_gitlab_baselines.py generate --arm P0     resumable (append, skip done ids); arms P0, CB, F0_repro10, F0_rerun
  python exp2_gitlab_baselines.py repro                 10-question check: F0_repro10 vs stored F0, byte-identical answers
  python exp2_gitlab_baselines.py analyse               Task 1: counts, McNemar families, audit lists
  python exp2_gitlab_baselines.py gate                  Task 2: MiniCheck gate on F0 and P0 (GPU; resumable), then gatestats
  python exp2_gitlab_baselines.py gatestats             Task 2 tables from results/baselines_gate_rows.jsonl
  python exp2_gitlab_baselines.py carry                 Task 3: retrieval carry-through (CPU, existing files)
  python exp2_gitlab_baselines.py sheet                 blank blind correctness sheet + key (never read back)
  python exp2_gitlab_baselines.py figure                results/baselines_tradeoff.png
  python exp2_gitlab_baselines.py bundle                results/exp2_baselines_bundle.zip

Arms (all else as F0, read from gen_F0.jsonl and exp2_gitlab_scale.cmd_generate):
  P0  plain RAG: F0's context (rebuilt, asserted equal), system "You are a helpful assistant. Use the following
      context from GitLab Runner merge requests to answer the question.", user "{context}\\n\\nQuestion: {question}"
  CB  closed book: no context, system "You are a helpful assistant. Answer the question about the GitLab Runner
      project.", user "Question: {question}"
  F0_repro10 / F0_rerun  F0's own prompt and context, re-generated (sensitivity only; gen_F0.jsonl is never touched)
Imports exp2_gitlab_scale (never modified; its score/build are never called) and, for the gate,
ESP3201A_Exp2/faithfulness.py and gate_eval.py (imported, not copied).
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
import traceback

import exp2_gitlab_scale as E

OUT = E.OUT                                   # exp2_gitlab_A2000
RES = "results"
LOGS = os.path.join(RES, "logs")
KEYS = os.path.join(RES, "keys")
RUN_LOG = os.path.join(RES, "RUN_LOG.md")
META = os.path.join(OUT, "run_meta_baselines.json")
EXP2_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "exp2_django"))
CH = "fixed_s512_o77"

SYS_P0 = ("You are a helpful assistant. Use the following context from GitLab Runner merge requests "
          "to answer the question.")
SYS_CB = "You are a helpful assistant. Answer the question about the GitLab Runner project."
SYS_SHA1 = {"P0": "74880d5f88", "CB": "a61187ec8b"}
F0_DIGEST, F0_OLLAMA = "0edcdef34593", "0.40.4"
REPRO_IDS = ["nr1372", "nr1781", "nr3147", "nr3177", "nr3805", "nr4102", "nr4460", "nr5841", "q106", "q1063"]
GEN_ARMS = ("P0", "CB", "F0_repro10", "F0_rerun")
LENIENT = re.compile(r"not found in the provided|do(es)? not (state|mention|provide|explain|specify|contain|say)|"
                     r"no (information|reason|mention)|not (provided|mentioned|stated|specified)|"
                     r"cannot (be )?determine|unable to determine", re.I)
# sensitivity only (rule section 4, added after advisor check 1, before any generation): OR-ed with LENIENT
BROAD = re.compile(r"(does|do|did)( not|n['’]t)( \w+)? (state|mention|provide|explain|specify|contain|say|include|give)|"
                   r"(is|are|was|were)( not|n['’]t)( \w+)? (provided|mentioned|stated|specified|explained|given|documented)|"
                   r"no (specific |explicit |clear |direct |publicly available )?(information|reason|mention|explanation|details?)|"
                   r"(don['’]t|do not) have (access|information|specific|details)|"
                   r"(cannot|can['’]t|could not|couldn['’]t|unable to) (find|determine|confirm|identify)|not aware of", re.I)
DOUBTFUL = ("nr3177", "nr4460")
UNANS = ("no_reason", "removed")


def sha10(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_run(msg):
    with open(RUN_LOG, "a", encoding="utf-8") as f:
        f.write(f"- {now()} {msg}\n")


def git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return None


def gen_path(arm):
    return os.path.join(OUT, f"gen_{arm}.jsonl")


def questions():
    return E.read_jsonl(E.QUESTIONS)


def load_meta():
    if os.path.exists(META):
        with open(META, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_meta(m):
    with open(META, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- Ollama state
def ollama_state(model=E.MODEL):
    import requests
    version = requests.get(f"{E.OLLAMA}/api/version", timeout=30).json().get("version")
    tags = requests.get(f"{E.OLLAMA}/api/tags", timeout=30).json()["models"]
    digest = next((m["digest"][:12] for m in tags if m["name"] == model), None)
    show = requests.post(f"{E.OLLAMA}/api/show", json={"model": model}, timeout=60).json()
    show = {k: show.get(k) for k in ("parameters", "details", "modified_at", "capabilities")}
    return version, digest, show


def cmd_meta(a):
    version, digest, show = ollama_state()
    try:
        cli = subprocess.check_output(["ollama", "--version"], text=True, stderr=subprocess.STDOUT).strip()
    except Exception as e:
        cli = f"failed: {e}"
    import platform
    m = load_meta()
    m.update({
        "rule": "tuning_rule_baselines.md", "created": m.get("created", now()), "updated": now(),
        "git_commit_at_meta": git_head(),
        "ollama_version_api": version, "ollama_version_cli": cli, "model": E.MODEL, "model_digest": digest,
        "ollama_show": show,
        "f0_reference": {"ollama_version": F0_OLLAMA, "model_digest": F0_DIGEST,
                         "source": "all 70 rows of exp2_gitlab_A2000/gen_F0.jsonl agree"},
        "matches_f0": {"ollama_version": version == F0_OLLAMA, "model_digest": digest == F0_DIGEST},
        "request": {"endpoint": "/api/chat", "think": False, "stream": False, "options": E.OPTIONS,
                    "timeout_s": 900, "source": "exp2_gitlab_scale.cmd_generate + gen_F0.jsonl options"},
        "prompts": {
            "P0": {"system": SYS_P0, "system_sha1": sha10(SYS_P0), "user": "{context}\n\nQuestion: {question}",
                   "context": "F0's chunks (exp2_gitlab_scale.pack, asserted equal), exp2_gitlab_scale.format_context"},
            "CB": {"system": SYS_CB, "system_sha1": sha10(SYS_CB), "user": "Question: {question}", "context": None},
            "F0": {"prompt_sha1": E.sympy_prompt()["sha1"], "based_on": E.sympy_prompt()["based_on"]}},
        "machine": E.machine(), "python": platform.python_version()})
    save_meta(m)
    print(json.dumps({k: m[k] for k in ("ollama_version_api", "ollama_version_cli", "model_digest", "matches_f0")},
                     indent=1))


# ---------------------------------------------------------------- contexts (F0's, rebuilt and asserted)
def f0_contexts(qs):
    _, cands = E._candidates(CH)
    chunks, _ = E.chunk_set(CH)
    by_id = {c["chunk_id"]: c for c in chunks}
    f0 = {r["id"]: r for r in E.read_jsonl(gen_path("F0"))}
    out = {}
    for q in qs:
        cks = E.pack(cands[q["id"]]["chunk_ids"], by_id, "score", q["exclude_prs"], 0.0, {})
        if [c["chunk_id"] for c in cks] != f0[q["id"]]["context_chunk_ids"]:
            raise SystemExit(f"STOP: rebuilt context of {q['id']} differs from gen_F0.jsonl")
        if sum(c["tokens"] for c in cks) != f0[q["id"]]["context_tokens"]:
            raise SystemExit(f"STOP: rebuilt context tokens of {q['id']} differ from gen_F0.jsonl")
        out[q["id"]] = cks
    return out


def build_messages(arm, q, cks):
    if arm in ("F0_repro10", "F0_rerun"):
        p = E.sympy_prompt()
        user = p["user"].format(question=q["question"], context=E.format_context(cks))
        return p["system"], user, p["sha1"], p["based_on"]
    if arm == "P0":
        return SYS_P0, f"{E.format_context(cks)}\n\nQuestion: {q['question']}", sha10(SYS_P0), \
            "plain RAG baseline (tuning_rule_baselines.md); no citation or refusal rule"
    if arm == "CB":
        return SYS_CB, f"Question: {q['question']}", sha10(SYS_CB), \
            "closed-book baseline (tuning_rule_baselines.md); no context"
    raise ValueError(arm)


# ---------------------------------------------------------------- generate
def cmd_generate(a):
    import requests
    from tqdm import tqdm
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    arm, job = a.arm, f"gen_{a.arm}"
    os.makedirs(LOGS, exist_ok=True)
    for sfx in (".done", ".failed"):
        if os.path.exists(os.path.join(LOGS, job + sfx)):
            os.remove(os.path.join(LOGS, job + sfx))
    with open(os.path.join(LOGS, job + ".pid"), "w") as f:
        f.write(str(os.getpid()))
    logf = open(os.path.join(LOGS, job + ".log"), "a", encoding="utf-8")

    def say(msg):
        tqdm.write(msg)
        logf.write(f"{now()} {msg}\n")
        logf.flush()
    try:
        for k in ("P0", "CB"):
            assert sha10({"P0": SYS_P0, "CB": SYS_CB}[k]) == SYS_SHA1[k], f"{k} system text differs from the rule"
        assert E.sympy_prompt()["sha1"] == "072bd24371", "F0 prompt differs"
        qs = questions()
        if arm == "F0_repro10":
            qs = [q for q in qs if q["id"] in REPRO_IDS]
            assert len(qs) == 10
        docs = E.pool_docs()
        say(f"{job}: loading chunks and rebuilding F0 contexts ...")
        ctx = f0_contexts(qs)
        version, digest, _ = ollama_state(a.model)
        if digest is None:
            raise SystemExit(f"model {a.model} is not pulled")
        if version != F0_OLLAMA or digest != F0_DIGEST:
            say(f"NOTE: Ollama {version} / digest {digest} differ from F0's {F0_OLLAMA} / {F0_DIGEST}")
            log_run(f"NOTE {job}: Ollama {version} / digest {digest} differ from F0's {F0_OLLAMA} / {F0_DIGEST}")
        mach, commit = E.machine(), git_head()
        qprompt = E._candidates(CH)[0]["query_prompt"]
        path = gen_path(arm)
        if os.path.exists(path):                     # cut an unparsable last line (kill mid-write)
            with open(path, "rb") as f:
                raw = f.read()
            lines = raw.split(b"\n")
            tail = lines[-1] if lines[-1].strip() else (lines[-2] if len(lines) > 1 else b"")
            try:
                if tail.strip():
                    json.loads(tail.decode("utf-8"))
            except Exception:
                keep = raw[:raw.rstrip(b"\n").rfind(b"\n") + 1]
                with open(os.path.join(LOGS, job + ".quarantine"), "ab") as qf:
                    qf.write(raw[len(keep):] + b"\n")
                with open(path, "wb") as f:
                    f.write(keep)
                say(f"NOTE: cut an unparsable last line from {path} -> {job}.quarantine")
                log_run(f"NOTE {job}: cut an unparsable last line from {path} (saved to logs/{job}.quarantine)")
        done = {r["id"] for r in E.read_jsonl(path)} if os.path.exists(path) else set()
        todo = [q for q in qs if q["id"] not in done]
        say(f"{job}: {len(todo)} of {len(qs)} questions to generate -> {path} (commit {commit}, Ollama {version}, digest {digest})")
        m = load_meta()
        m.setdefault("jobs", {}).setdefault(job, []).append(
            {"start": now(), "git_commit": commit, "ollama_version": version, "model_digest": digest,
             "n_todo": len(todo), "n_total": len(qs)})
        save_meta(m)
        log_run(f"{job} started: {len(todo)}/{len(qs)} to do, commit {commit}, pid {os.getpid()}")
        t_start = time.time()
        bar = tqdm(todo, desc=job, unit="q", file=sys.stderr, dynamic_ncols=True, mininterval=0.5)
        with open(path, "a", encoding="utf-8") as out:
            for i, q in enumerate(bar, 1):
                cks = [] if arm == "CB" else ctx[q["id"]]
                system, user, psha, based = build_messages(arm, q, cks)
                body = {"model": a.model, "think": False, "stream": False, "options": E.OPTIONS,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
                t0 = time.time()
                r = requests.post(f"{E.OLLAMA}/api/chat", json=body, timeout=900)
                r.raise_for_status()
                d = r.json()
                n_in = d.get("prompt_eval_count")
                cov = (E.covered(q["spans"], cks, q["pr_number"], docs[q["pr_number"]]["text"])
                       if q["type"] == "answerable" else None)
                has_ctx = arm != "CB"
                rec = {"id": q["id"], "type": q["type"], "pr_number": q["pr_number"], "arm": arm,
                       "chunking": CH if has_ctx else None, "order": "score" if has_ctx else None,
                       "alpha": 0.0 if has_ctx else None, "budget": E.BUDGET if has_ctx else None,
                       "chunk_set": "111084af" if has_ctx else None,
                       "query_prompt": qprompt if has_ctx else None,
                       "prompt_sha1": psha, "prompt_based_on": based, "system_sha1": sha10(system),
                       "model": a.model, "model_digest": digest, "ollama_version": version,
                       "options": E.OPTIONS, "think": False, "machine": mach,
                       "context_chunk_ids": [c["chunk_id"] for c in cks],
                       "context_short_ids": [E.short_id(c["chunk_id"]) for c in cks],
                       "context_tokens": sum(c["tokens"] for c in cks),
                       "n_prs_in_context": len({c["pr_number"] for c in cks}),
                       "span_in_context": {"any": any(cov), "all": all(cov)} if cov else None,
                       "exclude_prs": q["exclude_prs"],
                       "prompt_eval_count": n_in, "eval_count": d.get("eval_count"),
                       "possibly_truncated": bool(n_in and n_in >= E.OPTIONS["num_ctx"] - 16),
                       "done_reason": d.get("done_reason"), "seconds": round(time.time() - t0, 2),
                       "git_commit": commit, "response": d["message"]["content"]}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                n_done = len(done) + i
                el = time.time() - t_start
                eta = el / i * (len(todo) - i) / 60
                with open(os.path.join(LOGS, job + ".progress"), "a", encoding="utf-8") as pf:
                    pf.write(f"{n_done}/{len(qs)} {now()} last={q['id']} {rec['seconds']:.1f}s eta={eta:.1f}min\n")
                bar.set_postfix_str(f"{q['id']} ETA {eta:.0f} min")
                say(f"  {arm:<10}{q['id']:<9} in={n_in} out={d.get('eval_count')} {rec['seconds']:.0f}s "
                    f"{rec['response'][:70]!r}")
        bar.close()
        n_rows = len(E.read_jsonl(path))
        m = load_meta()
        m["jobs"][job][-1].update({"end": now(), "n_rows_after": n_rows})
        save_meta(m)
        with open(os.path.join(LOGS, job + ".done"), "w", encoding="utf-8") as f:
            f.write(f"{now()} rows={n_rows}\n")
        say(f"{job}: DONE, {n_rows} rows in {path}")
        log_run(f"{job} finished: {n_rows} rows in {path}")
    except BaseException:
        tb = traceback.format_exc()
        with open(os.path.join(LOGS, job + ".failed"), "w", encoding="utf-8") as f:
            f.write(f"{now()}\n{tb}")
        say("FAILED\n" + tb)
        log_run(f"{job} FAILED: {tb.strip().splitlines()[-1]}")
        raise
    finally:
        logf.close()


# ---------------------------------------------------------------- reproducibility check
def cmd_repro(a):
    f0 = {r["id"]: r for r in E.read_jsonl(gen_path("F0"))}
    rows = []
    for r in E.read_jsonl(gen_path("F0_repro10")):
        old = f0[r["id"]]["response"]
        rows.append({"id": r["id"], "identical": r["response"] == old,
                     "same_context": r["context_chunk_ids"] == f0[r["id"]]["context_chunk_ids"],
                     "stored_first120": old[:120], "rerun_first120": r["response"][:120]})
    with open(os.path.join(RES, "baselines_repro10.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n = sum(x["identical"] for x in rows)
    print(f"{n}/{len(rows)} byte-identical; contexts identical {sum(x['same_context'] for x in rows)}/{len(rows)}")
    for x in rows:
        if not x["identical"]:
            print("  differs:", x["id"])


# ---------------------------------------------------------------- Task 1 scoring
def flags(r, q):
    x = E.auto(r, q, CH)
    refusal_lenient = x["empty_answer"] or bool(LENIENT.search(r["response"]))
    refusal_broad = refusal_lenient or bool(BROAD.search(r["response"]))
    return {"answered_lenient": not refusal_lenient, "answered_broad": not refusal_broad,
            "answered_strict": not x["abstained"] and not x["empty_answer"],
            "any_citation": x["n_cites"] > 0, "valid_citation": x["n_valid_cites"] > 0,
            "overlap_cited": bool(x["overlap_cited"]), "empty": x["empty_answer"]}


def load_gens(arms):
    out = {}
    for arm in arms:
        p = gen_path(arm)
        if os.path.exists(p):
            out[arm] = {r["id"]: r for r in E.read_jsonl(p)}
    return out


def write_csv(path, rows, fields=None):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)


def paired_test(qs, gx, gy, key, types, exclude=()):
    ids = [i for i in gx if i in gy and qs[i]["type"] in types and i not in exclude]
    fx = {i: flags(gx[i], qs[i])[key] for i in ids}
    fy = {i: flags(gy[i], qs[i])[key] for i in ids}
    b = sum(fx[i] and not fy[i] for i in ids)
    c = sum(fy[i] and not fx[i] for i in ids)
    return {"n": len(ids), "count_x": sum(fx.values()), "count_y": sum(fy.values()), "b_only_x": b,
            "c_only_y": c}


def cmd_analyse(a):
    import exp2_scale_stats as S
    qs = {q["id"]: q for q in questions()}
    gens = load_gens(("F0", "P0", "CB", "F0_rerun"))
    for arm in ("F0", "P0", "CB"):                   # Holm m is always 4: never run on a missing arm
        if arm not in gens:
            raise SystemExit(f"STOP: {gen_path(arm)} missing")
    # per-row flags and per-arm counts
    rows_out, counts = [], []
    for arm, g in gens.items():
        fl = {i: flags(r, qs[i]) for i, r in g.items()}
        for i, r in g.items():
            rows_out.append({"arm": arm, "id": i, "type": r["type"], **fl[i],
                             "span_in_context_any": bool(r["span_in_context"] and r["span_in_context"]["any"])})
        ans = [i for i in g if qs[i]["type"] == "answerable"]
        un = [i for i in g if qs[i]["type"] in UNANS]
        counts.append({
            "arm": arm, "n_rows": len(g), "n_answerable": len(ans), "n_unanswerable": len(un),
            "unanswerable_answered_lenient": sum(fl[i]["answered_lenient"] for i in un),
            "unanswerable_answered_strict": sum(fl[i]["answered_strict"] for i in un),
            "no_reason_answered_lenient": sum(fl[i]["answered_lenient"] for i in un if qs[i]["type"] == "no_reason"),
            "removed_answered_lenient": sum(fl[i]["answered_lenient"] for i in un if qs[i]["type"] == "removed"),
            "unanswerable_answered_lenient_excl_doubtful": sum(fl[i]["answered_lenient"] for i in un
                                                               if i not in DOUBTFUL),
            "answerable_answered_lenient": sum(fl[i]["answered_lenient"] for i in ans),
            "answerable_answered_strict": sum(fl[i]["answered_strict"] for i in ans),
            "unanswerable_answered_broad": sum(fl[i]["answered_broad"] for i in un),
            "answerable_answered_broad": sum(fl[i]["answered_broad"] for i in ans),
            "any_citation_of_answerable": sum(fl[i]["any_citation"] for i in ans),
            "valid_citation_of_answerable": sum(fl[i]["valid_citation"] for i in ans),
            "overlap_cited_of_answerable": sum(fl[i]["overlap_cited"] for i in ans),
            "empty_answers": sum(fl[i]["empty"] for i in g),
            "median_eval_tokens": sorted(r["eval_count"] or 0 for r in g.values())[len(g) // 2],
            "hit_num_predict": sum((r["eval_count"] or 0) >= E.OPTIONS["num_predict"] for r in g.values())})
    write_csv(os.path.join(RES, "baselines_rows.csv"), rows_out)
    write_csv(os.path.join(RES, "baselines_counts.csv"), counts)
    # tests
    tests = []

    def family(name, scoring, key, x_arm, comps, exclude=(), adjust=True):
        fam = []
        for y_arm in comps:
            if x_arm not in gens or y_arm not in gens:
                continue
            for outcome, types in (("unanswerable_answered", UNANS), ("answerable_answered", ("answerable",))):
                t = paired_test(qs, gens[x_arm], gens[y_arm], key, types, exclude)
                fam.append({"family": name, "scoring": scoring, "x": x_arm, "y": y_arm, "outcome": outcome,
                            **t, "p": S.mcnemar(t["b_only_x"], t["c_only_y"])})
        if adjust:
            assert len(fam) == 4, (name, len(fam))
        hs = S.holm([r["p"] for r in fam]) if adjust and fam else [""] * len(fam)
        for r, h in zip(fam, hs):
            r["holm"] = h
            r["excluded"] = ",".join(exclude)
        tests.extend(fam)
    family("primary (Holm over 4)", "lenient", "answered_lenient", "F0", ("P0", "CB"))
    family("secondary (Holm over 4)", "strict", "answered_strict", "F0", ("P0", "CB"))
    family("sensitivity: excl. nr3177, nr4460 (Holm over 4)", "lenient", "answered_lenient", "F0", ("P0", "CB"),
           exclude=DOUBTFUL)
    family("sensitivity: broad refusal regex (Holm over 4)", "broad", "answered_broad", "F0", ("P0", "CB"))
    if "F0_rerun" in gens:
        family("sensitivity: F0_rerun in place of F0 (unadjusted)", "lenient", "answered_lenient", "F0_rerun",
               ("P0", "CB"), adjust=False)
    write_csv(os.path.join(RES, "baselines_tests.csv"), tests)
    # audit lists
    audit, unl, broad = [], [], []
    for arm, g in gens.items():
        for i, r in g.items():
            f = flags(r, qs[i])
            if f["answered_lenient"] and not f["answered_broad"]:
                broad.append({"arm": arm, "id": i, "type": r["type"],
                              "matched": BROAD.search(r["response"]).group(0), "first200": r["response"][:200]})
            if f["answered_strict"] and not f["answered_lenient"]:
                m = LENIENT.search(r["response"])
                audit.append({"arm": arm, "id": i, "type": r["type"], "matched": m.group(0) if m else "(empty)",
                              "first200": r["response"][:200]})
            if r["type"] in UNANS and f["answered_lenient"]:
                unl.append({"arm": arm, "id": i, "type": r["type"], "first200": r["response"][:200]})
    write_csv(os.path.join(RES, "baselines_audit_lenient.csv"), audit,
              ["arm", "id", "type", "matched", "first200"])
    write_csv(os.path.join(RES, "baselines_unanswerable_answered.csv"), unl, ["arm", "id", "type", "first200"])
    write_csv(os.path.join(RES, "baselines_audit_broad.csv"), broad, ["arm", "id", "type", "matched", "first200"])
    # F0 rerun identity
    if "F0_rerun" in gens:
        same = sum(gens["F0_rerun"][i]["response"] == gens["F0"][i]["response"] for i in gens["F0_rerun"])
        print(f"F0_rerun: {same}/{len(gens['F0_rerun'])} byte-identical to stored F0")
    for c in counts:
        print(c)
    for t in tests:
        print({k: t[k] for k in ("family", "x", "y", "outcome", "n", "count_x", "count_y", "b_only_x", "c_only_y",
                                 "p", "holm")})
    print(f"audit (strict answered, lenient refusal): {len(audit)} rows; unanswerable answered (lenient): {len(unl)}")


# ---------------------------------------------------------------- provisional F0 labels (no keys/)
def f0_labels(qs):
    """{F0 id: label}, from correctness_sheet.csv via cmd_score's own blind-id order (rule section 7)."""
    sheet = {}
    with open(os.path.join(OUT, "correctness_sheet.csv"), encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            sheet[row["blind_id"]] = row
    gens = {arm: E.read_jsonl(gen_path(arm)) for arm in ("F0", "C1")}
    items = []
    for arm, recs in gens.items():
        for r in recs:
            x = E.auto(r, qs[r["id"]], CH)
            if r["type"] == "answerable" and not x["abstained"] and not x["empty_answer"] and r["id"] != "q5853":
                items.append((hashlib.sha256(f"42:{arm}:{r['id']}".encode()).hexdigest(), arm, r))
    items.sort(key=lambda t: t[0])
    labels, problems = {}, []
    for i, (_, arm, r) in enumerate(items, 1):
        bid = f"S{i:03d}"
        row = sheet.get(bid)
        ok = (row is not None and row["question"] == qs[r["id"]]["question"]
              and row["model_answer"] == E.strip_citations(r["response"]))
        if not ok:
            problems.append((bid, arm, r["id"]))
        elif arm == "F0":
            labels[r["id"]] = row["label"].strip().lower()
    f0q = next((r for r in gens["F0"] if r["id"] == "q5853"), None)
    c1q = next((r for r in gens["C1"] if r["id"] == "q5853"), None)
    if f0q is not None:
        t = E.strip_citations(f0q["response"])
        cand = [b for b in ("S086", "S087") if b in sheet and sheet[b]["model_answer"] == t
                and sheet[b]["question"] == qs["q5853"]["question"]]
        labs = {sheet[b]["label"].strip().lower() for b in cand}
        if c1q is not None and E.strip_citations(c1q["response"]) == t and len(labs) > 1:
            problems.append(("S086/S087", "F0", "q5853 ambiguous"))
        elif cand:
            labels["q5853"] = labs.pop()
        else:
            problems.append(("S086/S087", "F0", "q5853 not found"))
    n_used = len(items) + (2 if f0q is not None else 0)
    return labels, problems, {"sheet_rows": len(sheet), "rows_recomputed": n_used}


# ---------------------------------------------------------------- Task 2 gate
def cmd_gate(a):
    from tqdm import tqdm
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    job = "gate"
    os.makedirs(LOGS, exist_ok=True)
    for sfx in (".done", ".failed"):
        if os.path.exists(os.path.join(LOGS, job + sfx)):
            os.remove(os.path.join(LOGS, job + sfx))
    with open(os.path.join(LOGS, job + ".pid"), "w") as f:
        f.write(str(os.getpid()))
    try:
        qs_list = questions()
        qs = {q["id"]: q for q in qs_list}
        ctx = f0_contexts(qs_list)                 # before importing the Django modules
        gens = load_gens(("F0", "P0"))
        sys.path.append(EXP2_DIR)
        import faithfulness as FA
        import gate_eval as GE
        assert GE.THRESHOLD == 0.5
        path = os.path.join(RES, "baselines_gate_rows.jsonl")
        done = {(x["arm"], x["id"]) for x in E.read_jsonl(path)} if os.path.exists(path) else set()
        todo = [(arm, r) for arm in ("F0", "P0") if arm in gens for r in gens[arm].values()
                if flags(r, qs[r["id"]])["answered_strict"] and (arm, r["id"]) not in done]
        log_run(f"gate started: {len(todo)} rows to score (F0, P0 strict-answered), commit {git_head()}, "
                f"faithfulness from {FA.__file__}")
        mc = FA.MiniCheck()
        rev = getattr(mc.m.config, "_commit_hash", None) or ""
        tqdm.write(f"MiniCheck on {FA.DEV}, revision {rev}")
        if not (rev.startswith("96eafd01") and FA.DEV == "cuda"):
            raise SystemExit(f"SKIP Task 2: MiniCheck revision {rev!r} on {FA.DEV} (rule needs 96eafd01 on cuda)")
        with open(path, "a", encoding="utf-8") as out:
            for k, (arm, r) in enumerate(tqdm(todo, desc="gate", unit="row", file=sys.stderr, dynamic_ncols=True), 1):
                cks = ctx[r["id"]]
                assert [c["chunk_id"] for c in cks] == r["context_chunk_ids"], (arm, r["id"])
                cited = set(FA.CITE.findall(r["response"]))
                prem = [c["text"] for c in cks if E.short_id(c["chunk_id"]) in cited]
                sents = FA.sentences(r["response"])
                sc = [mc.score(prem, s) for s in sents] if prem else []
                mn = min(sc) if sc else None
                kept = GE.passes({"answered": True, "score": mn}, GE.THRESHOLD)
                rec = {"arm": arm, "id": r["id"], "type": r["type"], "n_cited_in_context": len(prem),
                       "n_sentences": len(sents), "minicheck_cited_min": mn, "kept": kept, "gated": not kept,
                       "model_revision": getattr(mc.m.config, "_commit_hash", None)}
                out.write(json.dumps(rec) + "\n")
                out.flush()
                with open(os.path.join(LOGS, job + ".progress"), "a", encoding="utf-8") as pf:
                    pf.write(f"{len(done) + k}/{len(done) + len(todo)} {now()} last={arm}:{r['id']}\n")
        with open(os.path.join(LOGS, job + ".done"), "w", encoding="utf-8") as f:
            f.write(f"{now()} rows={len(E.read_jsonl(path))}\n")
        log_run(f"gate finished: {len(E.read_jsonl(path))} rows in {path}")
    except BaseException:
        tb = traceback.format_exc()
        with open(os.path.join(LOGS, job + ".failed"), "w", encoding="utf-8") as f:
            f.write(f"{now()}\n{tb}")
        log_run(f"gate FAILED: {tb.strip().splitlines()[-1]}")
        raise
    cmd_gatestats(a)


def cmd_gatestats(a):
    import exp2_scale_stats as S
    qs = {q["id"]: q for q in questions()}
    gens = load_gens(("F0", "P0"))
    rows = {(x["arm"], x["id"]): x for x in E.read_jsonl(os.path.join(RES, "baselines_gate_rows.jsonl"))}
    labels, problems, info = f0_labels(qs)
    table, tests = [], []
    for arm, g in gens.items():
        for scoring, key in (("lenient", "answered_lenient"), ("strict", "answered_strict")):
            fl = {i: flags(r, qs[i]) for i, r in g.items()}
            missing = [i for i in g if fl[i]["answered_strict"] and (arm, i) not in rows]
            if missing:
                raise SystemExit(f"{arm}: no gate score for {missing}")
            kept = {i: fl[i][key] and rows[(arm, i)]["kept"] if fl[i]["answered_strict"] else False for i in g}
            ans = [i for i in g if qs[i]["type"] == "answerable"]
            un = [i for i in g if qs[i]["type"] in UNANS]
            row = {"arm": arm, "scoring": scoring,
                   "unanswerable_answered_before": sum(fl[i][key] for i in un),
                   "unanswerable_answered_after": sum(kept[i] for i in un),
                   "answerable_answered_before": sum(fl[i][key] for i in ans),
                   "answerable_answered_after": sum(kept[i] for i in ans),
                   "answered_no_valid_cited_premise": sum(fl[i][key] and rows[(arm, i)]["minicheck_cited_min"] is None
                                                          for i in g if fl[i]["answered_strict"])}
            if arm == "F0":
                row["correct_before_provisional"] = sum(fl[i][key] and labels.get(i) == "correct" for i in ans)
                row["correct_after_provisional"] = sum(kept[i] and labels.get(i) == "correct" for i in ans)
                row["answered_answerable_without_label"] = sum(fl[i][key] and i not in labels for i in ans)
            table.append(row)
            if scoring == "lenient":
                for outcome, ids in (("unanswerable_answered", un), ("answerable_answered", ans)):
                    b = sum(fl[i][key] and not kept[i] for i in ids)
                    c = sum(kept[i] and not fl[i][key] for i in ids)
                    tests.append({"arm": arm, "outcome": outcome, "n": len(ids), "no_gate": sum(fl[i][key] for i in ids),
                                  "gate": sum(kept[i] for i in ids), "b_only_no_gate": b, "c_only_gate": c,
                                  "p": S.mcnemar(b, c), "label": "exploratory"})
    for t, h in zip(tests, S.holm([t["p"] for t in tests])):
        t["holm_reference"] = h
    write_csv(os.path.join(RES, "baselines_gate.csv"), table)
    write_csv(os.path.join(RES, "baselines_gate_tests.csv"), tests)
    # cross-check against the stored F0 gate (copied code, same revision)
    stored = {x["id"]: x for x in E.read_jsonl(os.path.join(OUT, "gate_F0.jsonl"))}
    mism = [(i, stored[i]["gated"], rows[("F0", i)]["gated"]) for i in stored if ("F0", i) in rows
            and stored[i]["gated"] != rows[("F0", i)]["gated"]]
    diffs = [abs((stored[i]["minicheck_cited_min"] or 0) - (rows[("F0", i)]["minicheck_cited_min"] or 0))
             for i in stored if ("F0", i) in rows]
    check = {"stored_rows": len(stored), "compared": len(diffs), "gate_decision_mismatches": mism,
             "max_abs_score_diff": max(diffs) if diffs else None,
             "label_mapping": {"f0_labels_found": len(labels), "problems": problems, **info}}
    with open(os.path.join(RES, "baselines_gate_crosscheck.json"), "w", encoding="utf-8") as f:
        json.dump(check, f, indent=1)
    for r in table:
        print(r)
    for t in tests:
        print(t)
    print(json.dumps(check))


# ---------------------------------------------------------------- Task 3
def gold_rank(cand, pr):
    prs = list(dict.fromkeys(int(c.split("_")[0]) for c in cand["chunk_ids"]))
    return prs.index(pr) + 1 if pr in prs else None


def cmd_carry(a):
    qs = {q["id"]: q for q in questions()}
    f0 = {r["id"]: r for r in E.read_jsonl(gen_path("F0"))}
    _, cands = E._candidates(CH)
    labels, problems, info = f0_labels(qs)
    ans = [i for i in f0 if qs[i]["type"] == "answerable"]
    per = []
    for i in ans:
        r, fl = f0[i], flags(f0[i], qs[i])
        rank = gold_rank(cands[i], qs[i]["pr_number"])
        per.append({"id": i, "span_in_context": bool(r["span_in_context"] and r["span_in_context"]["any"]),
                    "gold_rank": rank, **{k: fl[k] for k in ("answered_strict", "answered_lenient", "overlap_cited")},
                    "label_provisional": labels.get(i) if fl["answered_strict"] else "",
                    "correct": fl["answered_strict"] and labels.get(i) == "correct"})
    groups = [("span_in_context", "in context", lambda x: x["span_in_context"]),
              ("span_in_context", "not in context", lambda x: not x["span_in_context"]),
              ("gold_rank", "top 5", lambda x: x["gold_rank"] is not None and x["gold_rank"] <= 5),
              ("gold_rank", "lower or absent", lambda x: x["gold_rank"] is None or x["gold_rank"] > 5),
              ("gold_rank_fine", "rank 1", lambda x: x["gold_rank"] == 1),
              ("gold_rank_fine", "rank 2-5", lambda x: x["gold_rank"] is not None and 2 <= x["gold_rank"] <= 5),
              ("gold_rank_fine", "lower or absent", lambda x: x["gold_rank"] is None or x["gold_rank"] > 5),
              ("all", "all answerables", lambda x: True)]
    table = []
    for by, name, f in groups:
        g = [x for x in per if f(x)]
        table.append({"split": by, "group": name, "n": len(g),
                      "answered_strict": sum(x["answered_strict"] for x in g),
                      "answered_lenient": sum(x["answered_lenient"] for x in g),
                      "overlap_cited": sum(x["overlap_cited"] for x in g),
                      "correct_provisional": sum(x["correct"] for x in g),
                      "partial_provisional": sum(x["label_provisional"] == "partial" for x in g),
                      "wrong_provisional": sum(x["label_provisional"] == "wrong" for x in g),
                      "answered_unlabelled": sum(x["answered_strict"] and not x["label_provisional"] for x in g),
                      "ids": " ".join(x["id"] for x in g) if len(g) <= 6 else ""})
    write_csv(os.path.join(RES, "baselines_carry.csv"), table)
    write_csv(os.path.join(RES, "baselines_carry_rows.csv"), per)
    # Django: copy the cited rows verbatim, no recomputation
    dj = []
    with open(os.path.join(EXP2_DIR, "results", "stats_test_arms.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["model"] == "4b-instruct" and row["A"] == "F0/v3" and row["B"] == "S0/v3":
                dj.append({"source": "ESP3201A_Exp2/results/stats_test_arms.csv", **row})
    with open(os.path.join(RES, "baselines_django_extract.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "row"])
        for row in dj:
            w.writerow([row["source"], json.dumps({k: v for k, v in row.items() if k != "source"})])
        with open(os.path.join(EXP2_DIR, "results", "pr_length_tertiles.csv"), encoding="utf-8") as g:
            for line in g.read().splitlines():
                w.writerow(["ESP3201A_Exp2/results/pr_length_tertiles.csv", line])
    for t in table:
        print(t)
    print("label mapping:", len(labels), "F0 labels;", "problems:", problems, info)


# ---------------------------------------------------------------- blank sheet
def cmd_sheet(a):
    qs = {q["id"]: q for q in questions()}
    gens = load_gens(("F0", "P0", "CB"))
    assert set(gens) == {"F0", "P0", "CB"}, f"missing arms: {set(gens)}"
    groups = {}
    for arm in ("F0", "P0", "CB"):
        for i, r in gens[arm].items():
            if qs[i]["type"] == "answerable" and flags(r, qs[i])["answered_strict"]:
                groups.setdefault((i, E.strip_citations(r["response"])), []).append({"arm": arm, "id": i})
    items = sorted(groups.items(), key=lambda kv: kv[0])
    random.Random(42).shuffle(items)
    rows, key = [], {}
    for n, ((i, text), who) in enumerate(items, 1):
        bid = f"BL{n:03d}"
        q = qs[i]
        rows.append([bid, q["question"], q["answer"], " || ".join(q["quotes"]), text, "", ""])
        key[bid] = who
    cols = ["blind_id", "question", "gold_answer", "gold_quotes", "model_answer", "label", "reason"]
    path = os.path.join(RES, "baselines_blind_sheet_blank.csv")
    if os.path.exists(path):
        raise SystemExit(f"{path} exists: not overwritten")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    os.makedirs(KEYS, exist_ok=True)
    with open(os.path.join(KEYS, "baselines_blind_key.json"), "w", encoding="utf-8") as f:
        json.dump(key, f, indent=1)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
        wb = Workbook()
        ws = wb.active
        ws.title = "sheet"
        ws.append(cols)
        for r in rows:
            ws.append(r)
        for c in ws[1]:
            c.font = Font(bold=True)
        for col, width in zip("ABCDEFG", (9, 45, 45, 45, 70, 10, 40)):
            ws.column_dimensions[col].width = width
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        wb.save(path.replace(".csv", ".xlsx"))
        xl = "and .xlsx"
    except Exception as e:
        xl = f"(.xlsx failed: {e})"
    per_arm = {arm: sum(1 for who in key.values() for w in who if w["arm"] == arm) for arm in ("F0", "P0", "CB")}
    print(f"{len(rows)} distinct answers -> {path} {xl}; answers per arm {per_arm}; "
          f"rows shared by 2+ arms {sum(len(w) > 1 for w in key.values())}; key -> {KEYS}/ (do not open)")


# ---------------------------------------------------------------- figure
def cmd_figure(a):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with open(os.path.join(RES, "baselines_counts.csv"), encoding="utf-8") as f:
        cnt = {r["arm"]: r for r in csv.DictReader(f)}
    gate = {}
    gp = os.path.join(RES, "baselines_gate.csv")
    if os.path.exists(gp):
        with open(gp, encoding="utf-8") as f:
            gate = {(r["arm"], r["scoring"]): r for r in csv.DictReader(f)}
    arms = [("CB", "CB\nclosed book"), ("P0", "P0\nplain RAG"), ("F0", "F0\ngrounded v3")]
    vals = [(lab, int(cnt[k]["unanswerable_answered_lenient"]), int(cnt[k]["answerable_answered_lenient"]))
            for k, lab in arms if k in cnt]
    if ("F0", "lenient") in gate:
        g = gate[("F0", "lenient")]
        vals.append(("F0 + gate\nMiniCheck 0.5", int(g["unanswerable_answered_after"]),
                     int(g["answerable_answered_after"])))
    INK, MUTED, BG, ORANGE, GREEN = "#52514e", "#8a8984", "#fcfcfb", "#eb6834", "#1baf7a"
    plt.rcParams.update({"font.size": 10, "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK,
                         "ytick.color": MUTED, "axes.edgecolor": MUTED})
    fig, ax = plt.subplots(figsize=(11.5, 5.2), facecolor=BG)
    ax.set_facecolor(BG)
    w, gap = 0.36, 0.02                                   # grouped bars, 2% surface gap between the pair
    series = [(1, 18, ORANGE, "Unanswerable questions answered (of 18), lower is better", -1),
              (2, 52, GREEN, "Answerable questions answered (of 52), higher is better (answered is not correct)", 1)]
    for k, n, col, lab, side in series:
        xs = [i + side * (w / 2 + gap / 2) for i in range(len(vals))]
        hs = [100 * v[k] / n for v in vals]
        ax.bar(xs, hs, width=w, color=col, label=lab, zorder=2)
        for x, h, v in zip(xs, hs, vals):
            ax.text(x, h + 1.2, f"{v[k]}/{n}", ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_xticks(range(len(vals)), [v[0] for v in vals])
    ax.set_ylim(0, 112)
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("% of questions in the set")
    ax.grid(axis="y", color="#e6e5e1", linewidth=0.8, zorder=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.13), ncol=1, frameon=False, fontsize=9.5)
    ax.set_title("Exp 2 baselines on GitLab Runner (4B, 70 questions, lenient refusal scoring): the grounded prompt "
                 "answers fewer\nunanswerable questions than plain RAG or closed book; F0 + gate (exploratory): 5 to 2",
                 loc="left", fontsize=11.5, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "baselines_tradeoff.png"), dpi=200, facecolor=BG)
    print("figure ->", os.path.join(RES, "baselines_tradeoff.png"), vals)


# ---------------------------------------------------------------- bundle
def cmd_bundle(a):
    import zipfile
    zp = os.path.join(RES, "exp2_baselines_bundle.zip")
    files = []
    for root, dirs, fs in os.walk(RES):
        dirs[:] = [d for d in dirs if d != "keys"]
        for f in fs:
            p = os.path.join(root, f)
            if os.path.abspath(p) != os.path.abspath(zp):
                files.append(p)
    files += [gen_path(arm) for arm in ("P0", "CB", "F0_repro10", "F0_rerun") if os.path.exists(gen_path(arm))]
    files += [META, "tuning_rule_baselines.md", "exp2_gitlab_baselines.py"]
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            assert "keys" not in os.path.normpath(p).split(os.sep), p
            z.write(p, p)
    print(f"{len(files)} files -> {zp}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["meta", "generate", "repro", "analyse", "gate", "gatestats", "carry",
                                        "sheet", "figure", "bundle"])
    ap.add_argument("--arm", choices=GEN_ARMS)
    ap.add_argument("--model", default=E.MODEL)
    a = ap.parse_args()
    if a.command == "generate" and not a.arm:
        ap.error("generate needs --arm")
    {"meta": cmd_meta, "generate": cmd_generate, "repro": cmd_repro, "analyse": cmd_analyse, "gate": cmd_gate,
     "gatestats": cmd_gatestats, "carry": cmd_carry, "sheet": cmd_sheet, "figure": cmd_figure,
     "bundle": cmd_bundle}[a.command](a)
