r"""codex_steer.py: ACTIVATION STEERING on the 70 human-checked GitLab Runner questions (Codex build).

What this is: activation steering (contrastive activation addition). A fixed vector, the mean
difference between the model's activations on a wanted and an unwanted answer, is added to the
residual stream of one decoder layer while the frozen model generates. NO WEIGHTS CHANGE. This is
NOT reinforcement learning and NOT fine-tuning, and nothing here should be described as either.

Protocol as implemented: codex_rule.md. Choices the protocol leaves open: design_choices.md.
Problems found in the protocol: protocol_issues.md. James's runbook: README_CODEX_FOR_JAMES.md.

Run from anywhere. --repo is James's gitlab_runner_copy (default: the folder above this file's
folder, so put this folder inside the repo as codex_steering\). Outputs go to --out (default
codex_steering\out). Every GPU step appends row by row and skips rows already done (resumable).

  CPU  preflight  versions, CUDA build, VRAM, Ollama, input hashes, git state, model download
  CPU  prepare    prompts, folds, pairs, ratio subsets, pair flags. Stops unless every rebuilt
                  F0 context equals gen_F0.jsonl, and unless its outputs equal any shipped copy
  GPU  smoke      same greedy output twice; hook changes it; hook removal restores it
  GPU  vectors    per-pair activations (decoder layers 14/20/25), then fold x ratio vectors
  GPU  baseline   the same HF model, unsteered, on the 70 main prompts
  GPU  select     inner grid per fold x ratio on training MRs only; picks one setting each
  GPU  test       each held-out question answered with its own fold's chosen setting
  CPU  stats      exact McNemar, one Holm family of 9; --labels adds correctness (unadjusted)
  CPU  blind      blind correctness sheet (answers only) + separate keys/ file
  CPU  report     codex_report.md
  GPU  sweep      optional, descriptive only: the full grid on all 70 (out-of-fold vectors)
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "Qwen/Qwen3-4B-Instruct-2507"
MODEL_N_LAYERS, MODEL_HIDDEN = 36, 2560
LAYERS = [14, 20, 25]                  # 0-based index into model.model.layers (see design_choices.md)
PREFER_LAYER = 20                      # tie-break: layer closest to this
STRENGTHS = [0.5, 1.0, 2.0]
MAX_NEW = 512
RATIOS = {"40:60": (2, 3), "50:50": (1, 1), "60:40": (3, 2)}   # refusal : grounding pairs
N_FOLDS = 5
N_INNER_ANSWERABLE = 14
DEGEN_MAX_SHARE = Fraction(1, 10)      # drop a setting with MORE than 10% degenerate outputs
REPEAT_N, REPEAT_MIN = 4, 6            # a 4-word run occurring 6+ times -> degenerate
CHUNKING = "fixed_s512_o77"
SALT = "codex"                         # salt of every deterministic SHA-256 order
EXPECTED_COUNTS = {"answerable": 52, "no_reason": 8, "removed": 10}
WHAT_AS_WHY = 'Because the merge request "{title}" made this change. [{cite}]'


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def hkey(tag, s):
    return hashlib.sha256(f"{SALT}-{tag}:{s}".encode("utf-8")).hexdigest()


CODE_SHA = sha256_file(os.path.abspath(__file__))[:12]


# ------------------------------------------------------------------ small IO helpers
def rjsonl(path):
    """Read a JSONL file; a half-written last line (run killed mid-write) is skipped."""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i >= len(lines) - 2:
                print(f"  note: skipped a half-written last line in {os.path.basename(path)}")
            else:
                raise
    return rows


def rjson(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def jsonl_text(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def json_text(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def outp(a, *names):
    return os.path.join(a.out, *names)


def put(a, name, text, bom=False):
    """Write a deterministic output. If a copy already exists (e.g. the one shipped from Clifton's
    PC), it must be identical (line endings ignored); otherwise stop, unless --overwrite."""
    path = outp(a, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = ("﻿" if bom else "") + text
    if os.path.exists(path) and not a.overwrite:
        with open(path, encoding="utf-8", newline="") as f:
            old = f.read()
        if old.replace("\r\n", "\n") == body.replace("\r\n", "\n"):
            print(f"  {name}: identical to the existing copy (sha256 {sha256_bytes(body.encode())[:12]})")
            return
        raise SystemExit(f"STOP: {name} differs from the copy already in {a.out}. The inputs or the code "
                         f"differ from the reference run. Do not continue; send this log to Clifton. "
                         f"(--overwrite replaces it.)")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    os.replace(tmp, path)
    print(f"  {name}: written (sha256 {sha256_bytes(body.encode())[:12]})")


class Appender:
    """Append-only JSONL store keyed by row["key"]; flushes and fsyncs every row."""

    def __init__(self, path):
        self.path = path
        if os.path.exists(path) and os.path.getsize(path):
            with open(path, "rb") as f:
                data = f.read()
            if not data.endswith(b"\n"):                   # drop a half-written last line
                cut = data.rfind(b"\n") + 1
                print(f"  note: removed a half-written last line ({len(data) - cut} bytes) from "
                      f"{os.path.basename(path)}")
                with open(path, "r+b") as f:
                    f.truncate(cut)
        self.rows = {r["key"]: r for r in rjsonl(path)}

    def __contains__(self, key):
        return key in self.rows

    _f, _n = None, 0

    def add(self, row):
        """Each row is flushed at once (survives a crash of Python); fsync every 20 rows (survives
        a power cut up to the last 20). One open handle: re-opening per row is slow under
        antivirus / OneDrive."""
        if self._f is None:
            self._f = open(self.path, "a", encoding="utf-8", newline="")
        self._f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._f.flush()
        self._n += 1
        if self._n % 20 == 0:
            os.fsync(self._f.fileno())
        self.rows[row["key"]] = row

    def __del__(self):
        try:
            if self._f is not None:
                self._f.flush()
                os.fsync(self._f.fileno())
                self._f.close()
        except Exception:
            pass


class Tee:
    def __init__(self, stream, path):
        self.stream, self.f = stream, open(path, "a", encoding="utf-8")

    def write(self, s):
        self.stream.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        self.stream.flush()
        self.f.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


# ------------------------------------------------------------------ the Exp 2 script (imported)
def find_repo(arg):
    parent = os.path.dirname(HERE)
    cands = [arg] if arg else [parent, os.path.join(parent, "TX addtions", "TX addtions", "gitlab_runner_copy")]
    for c in cands:
        if c and os.path.exists(os.path.join(c, "exp2_gitlab_scale.py")):
            return os.path.abspath(c)
    raise SystemExit(f"Cannot find gitlab_runner_copy (looked for exp2_gitlab_scale.py in {cands}); "
                     f"pass --repo <path>")


_E = None


def exp2(a):
    """Import exp2_gitlab_scale from James's repo (its paths are relative, so cwd = repo)."""
    global _E
    if _E is None:
        sys.dont_write_bytecode = True                   # never write __pycache__ into the repo
        os.chdir(a.repo)
        if a.repo not in sys.path:
            sys.path.insert(0, a.repo)
        import exp2_gitlab_scale as E
        _E = E
    return _E


def questions(a):
    E = exp2(a)
    return {q["id"]: q for q in E.read_jsonl(E.QUESTIONS)}


def git_state(repo):
    try:
        head = subprocess.check_output(["git", "-C", repo, "rev-parse", "--short", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.check_output(["git", "-C", repo, "status", "--porcelain"], text=True,
                                        stderr=subprocess.DEVNULL).strip().splitlines()
        return {"head": head, "n_uncommitted": len(dirty)}
    except Exception:
        return {"head": None, "n_uncommitted": None}


# ------------------------------------------------------------------ scoring helpers
def outcomes(E, response, prompt_row, q):
    """Exp 2 score.py on one response (strict abstention; hedged counts as answered)."""
    x = E.auto({"response": response, "context_short_ids": prompt_row["context_short_ids"]}, q, CHUNKING)
    return {"abstained": x["abstained"], "hedged": x["hedged"], "empty": x["empty_answer"],
            "answered": (not x["abstained"]) and (not x["empty_answer"]),
            "overlap_cited": x["overlap_cited"], "contain_cited": x["contain_cited"],
            "n_cites": x["n_cites"], "n_valid_cites": x["n_valid_cites"]}


def degenerate(text, hit_max):
    """Reasons an output is degenerate: no letters, hit the token cap, or one 4-word run
    (lower-cased \\w+ words, anywhere in the text) occurring 6 or more times."""
    why = []
    if not re.search(r"[^\W\d_]", text):
        why.append("no_letters")
    if hit_max:
        why.append("hit_max_tokens")
    w = re.findall(r"\w+", text.lower())
    grams = Counter(tuple(w[i:i + REPEAT_N]) for i in range(len(w) - REPEAT_N + 1))
    if grams and max(grams.values()) >= REPEAT_MIN:
        why.append(f"repeat{REPEAT_N}x{max(grams.values())}")
    return why


def mcnemar_exact(b, c):
    """Two-sided exact McNemar p: binomial(b + c, 0.5), doubled smaller tail, capped at 1."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    m, out, run = len(ps), [None] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i]))
        out[i] = run
    return out


# ================================================================== preflight
HASHED = ["exp2_gitlab_scale.py", "relations.py", "chunking.py", "exp1_common.py", "pr_document.py",
          "github_prs.py", "swebench_loader.py", "sparse_retrieval.py", "dense_retrieval.py",
          "exp2_gitlab_A2000/questions.jsonl", "exp2_gitlab_A2000/candidates_fixed_s512_o77.jsonl",
          "exp2_gitlab_A2000/gen_F0.jsonl", "chunks/swe_fixed_s512_o77_2231docs_111084af.json",
          "prs/gitlab-org_gitlab-runner/_pool_A2000.json"]


def input_hashes(repo):
    out = {}
    for rel in HASHED:
        p = os.path.join(repo, *rel.split("/"))
        out[rel] = sha256_file(p) if os.path.exists(p) else None
    pool = os.path.join(repo, "prs", "gitlab-org_gitlab-runner", "_pool_A2000.json")
    if os.path.exists(pool):
        lines = []
        for n in sorted(int(x) for x in rjson(pool)["numbers"]):
            p = os.path.join(repo, "prs", "gitlab-org_gitlab-runner", f"{n}.json")
            lines.append(f"{n} {sha256_file(p) if os.path.exists(p) else 'MISSING'}\n")
        out["prs/gitlab-org_gitlab-runner/<pool MR files, combined>"] = sha256_bytes("".join(lines).encode())
    return out


def cmd_make_hashes(a):
    """Clifton's PC only: record the expected input hashes from the Latest copy."""
    h = input_hashes(a.repo)
    missing = [k for k, v in h.items() if v is None]
    if missing:
        raise SystemExit(f"missing inputs: {missing}")
    with open(os.path.join(HERE, "expected_hashes.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json_text({"made_from": a.repo, "files": h}))
    print(f"{len(h)} hashes -> {os.path.join(HERE, 'expected_hashes.json')}")


def cmd_preflight(a):
    ok, warn = [], []

    def fail(msg):
        ok.append(msg)
        print("  FAIL  " + msg)

    print(f"python {sys.version.split()[0]} on {platform.platform()}; code sha {CODE_SHA}")
    print(f"repo {a.repo}\nout  {a.out}")
    # --- input hashes
    exp_path = os.path.join(HERE, "expected_hashes.json")
    if not os.path.exists(exp_path):
        fail("expected_hashes.json is missing from the codex_steering folder")
    else:
        expected = rjson(exp_path)["files"]
        got = input_hashes(a.repo)
        bad = [k for k in expected if got.get(k) != expected[k]]
        for k in expected:
            print(f"  {'ok  ' if k not in bad else 'DIFF'}  {k}  {(got.get(k) or 'MISSING')[:16]}")
        if bad:
            fail(f"{len(bad)} input file(s) differ from Clifton's Latest copy: {bad}")
    # --- git
    g = git_state(a.repo)
    print(f"  git HEAD {g['head']}, {g['n_uncommitted']} uncommitted path(s)")
    if g["n_uncommitted"]:
        warn.append("the repo has uncommitted changes: commit before the run (the runbook does this)")
    # --- python packages
    try:
        import torch
        import transformers
        import numpy
        print(f"  torch {torch.__version__} (CUDA build {torch.version.cuda}), transformers "
              f"{transformers.__version__}, numpy {numpy.__version__}")
        tv = tuple(int(x) for x in re.findall(r"\d+", transformers.__version__)[:2])
        if tv < (4, 51):
            fail("transformers is older than 4.51 (no Qwen3): python -m pip install -U transformers")
    except ImportError as e:
        fail(f"missing package ({e}): python -m pip install torch transformers numpy huggingface_hub "
             f"(torch from https://download.pytorch.org/whl/cu128)")
        torch = None
    fix = ("python -m pip install --upgrade --force-reinstall torch "
           "--index-url https://download.pytorch.org/whl/cu128")
    if torch is not None and not a.cpu_ok:
        if not torch.cuda.is_available():
            fail(f"torch cannot see a CUDA GPU (CUDA build: {torch.version.cuda}). Fix: {fix}")
        else:
            name = torch.cuda.get_device_name(0)
            cap = torch.cuda.get_device_capability(0)
            arch = torch.cuda.get_arch_list()
            print(f"  GPU {name}, compute capability {cap[0]}.{cap[1]}, torch arch list {arch}")
            cuda_v = tuple(int(x) for x in (torch.version.cuda or "0.0").split(".")[:2])
            if cap >= (12, 0) and (cuda_v < (12, 8) or not any(x.startswith("sm_12") for x in arch)):
                fail(f"this torch build ({torch.version.cuda}) has no kernels for an RTX 50xx "
                     f"(sm_{cap[0]}{cap[1]}). Fix: {fix}")
            else:
                try:
                    x = torch.ones(4, device="cuda", dtype=torch.bfloat16) @ torch.ones(4, device="cuda",
                                                                                      dtype=torch.bfloat16)
                    assert float(x) == 4.0
                    print("  bf16 matmul on the GPU: ok")
                except Exception as e:
                    fail(f"a bf16 test on the GPU failed ({e}). Fix: {fix}")
                free, total = torch.cuda.mem_get_info()
                print(f"  VRAM free {free / 2**30:.1f} of {total / 2**30:.1f} GiB")
                if free < 10.5 * 2**30:
                    fail("less than 10.5 GiB VRAM free. Quit Ollama (tray icon -> Quit Ollama) and any "
                         "other GPU program, then re-run")
    # --- Ollama
    try:
        tl = subprocess.check_output(["tasklist"], text=True, stderr=subprocess.DEVNULL) \
            if os.name == "nt" else subprocess.check_output(["ps", "-A"], text=True)
        if "ollama" in tl.lower():
            warn.append("Ollama is running: quit it before the GPU steps (it holds GPU memory)")
    except Exception:
        pass
    # --- disk
    hf_home = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    os.makedirs(hf_home, exist_ok=True)
    free_gb = shutil.disk_usage(hf_home).free / 2**30
    print(f"  disk free at {hf_home}: {free_gb:.0f} GiB")
    # --- model download (the only network use) + revision
    if not ok and not a.no_download:
        try:
            from huggingface_hub import snapshot_download
            if free_gb < 10:
                warn.append("under 10 GiB free for the model (about 8 GB)")
            print(f"  downloading / checking {a.model} (about 8 GB the first time) ...")
            path = snapshot_download(a.model, revision=a.revision,
                                     allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model",
                                                     "*.jinja", "merges.txt", "vocab.json"])
            rev = os.path.basename(os.path.normpath(path))
            os.makedirs(a.out, exist_ok=True)
            with open(outp(a, "model_revision.json"), "w", encoding="utf-8", newline="\n") as f:
                f.write(json_text({"model": a.model, "revision": rev, "path": path}))
            print(f"  model {a.model} revision {rev} -> out/model_revision.json")
        except Exception as e:
            fail(f"model download failed: {e}")
    for w in warn:
        print("  WARN  " + w)
    if ok:
        print(f"\nPREFLIGHT FAILED ({len(ok)} problem(s)); fix them and run preflight again.")
        sys.exit(2)
    print("\nPREFLIGHT OK")


# ================================================================== prepare (CPU)
STOP = set("the a an and or of to in for on with by is are was were be been it its this that these "
           "those as at from not no but if so do does did into than then can could should would will "
           "also only why what which when how was there their they them has have had when use used "
           "using via more less new".split())
REASON_MARK = re.compile(r"\b(because|so that|in order to|to avoid|to prevent|to allow|to support|"
                         r"to enable|to make sure|to ensure|due to|since)\b", re.I)


def cwords(t):
    return {w for w in re.findall(r"[a-z0-9]+", (t or "").lower()) if len(w) > 2 and w not in STOP}


def clean_title(t):
    t = re.sub(r"^\s*(draft|wip)\s*:\s*", "", (t or "").strip(), flags=re.I).strip()
    return t.rstrip(" .")


def interleave(items, tag):
    """Deterministic order of one family's pairs: each `how` group sorted by SHA-256 of the
    question id, then merged by position fraction (i + 1/2) / n, so any prefix keeps the groups'
    proportions (ties: `how` name order)."""
    groups = defaultdict(list)
    for p in items:
        groups[p["how"]].append(p)
    keyed = []
    for gi, how in enumerate(sorted(groups)):
        g = sorted(groups[how], key=lambda p: hkey(tag, p["id"]))
        for i, p in enumerate(g):
            keyed.append((Fraction(2 * i + 1, 2 * len(g)), gi, p))
    keyed.sort(key=lambda t: (t[0], t[1]))
    return [p for _, _, p in keyed]


def cmd_prepare(a):
    E = exp2(a)
    from github_prs import load_pr
    qs = E.read_jsonl(E.QUESTIONS)
    qd = {q["id"]: q for q in qs}
    types = Counter(q["type"] for q in qs)
    if dict(types) != EXPECTED_COUNTS:
        raise SystemExit(f"STOP: question counts {dict(types)} != {EXPECTED_COUNTS}")
    meta, cands = E._candidates(CHUNKING)
    chunks, info = E.chunk_set(CHUNKING)
    by_id = {c["chunk_id"]: c for c in chunks}
    docs = E.pool_docs()
    f0 = {r["id"]: r for r in E.read_jsonl(os.path.join(E.OUT, "gen_F0.jsonl"))}
    pr = E.sympy_prompt()
    problems = []
    if set(f0) != set(qd):
        problems.append("gen_F0.jsonl ids differ from questions.jsonl")
    for r in f0.values():
        for k, v in (("arm", "F0"), ("alpha", 0.0), ("budget", E.BUDGET), ("chunking", CHUNKING),
                     ("order", "score"), ("prompt_sha1", pr["sha1"]), ("chunk_set", info["chunk_set"])):
            if r.get(k) != v:
                problems.append(f"{r['id']}: gen_F0 {k}={r.get(k)!r}, expected {v!r}")
    if meta.get("k") != 100 or meta.get("chunking") != CHUNKING:
        problems.append(f"candidates meta {meta}")
    if problems:
        raise SystemExit("STOP: stored F0 run does not match the setting:\n  " + "\n  ".join(problems[:20]))

    def build(q, kind, excl):
        cks = E.pack(cands[q["id"]]["chunk_ids"], by_id, "score", excl, 0.0, None)
        user = pr["user"].format(question=q["question"], context=E.format_context(cks))
        cov = (E.covered(q["spans"], cks, q["pr_number"], docs[q["pr_number"]]["text"])
               if q["type"] == "answerable" else None)
        return {"key": f"{kind}:{q['id']}", "id": q["id"], "kind": kind, "type": q["type"],
                "pr_number": q["pr_number"], "question": q["question"], "exclude_prs": sorted(set(excl)),
                "context_chunk_ids": [c["chunk_id"] for c in cks],
                "context_short_ids": [E.short_id(c["chunk_id"]) for c in cks],
                "context_prs": list(dict.fromkeys(c["pr_number"] for c in cks)),
                "context_tokens": sum(c["tokens"] for c in cks),
                "span_in_context": {"any": any(cov), "all": all(cov)} if cov else None,
                "prompt_sha1": pr["sha1"], "system": pr["system"], "user": user,
                "user_sha256": sha256_bytes(user.encode("utf-8"))}

    prompts, mismatch = [], []
    for q in qs:
        row = build(q, "main", q["exclude_prs"])
        if row["context_chunk_ids"] != f0[q["id"]]["context_chunk_ids"] or \
                row["context_short_ids"] != f0[q["id"]]["context_short_ids"] or \
                row["span_in_context"] != f0[q["id"]]["span_in_context"]:
            mismatch.append(q["id"])
        prompts.append(row)
    if mismatch:
        raise SystemExit(f"STOP: {len(mismatch)} rebuilt main contexts differ from gen_F0.jsonl: {mismatch}")
    print(f"all {len(prompts)} rebuilt main contexts equal gen_F0.jsonl (chunk ids, short ids, span flags)")
    twin_excl = {}
    for q in qs:
        if q["type"] != "answerable":
            continue
        excl = [q["pr_number"]] + list(q.get("quote_elsewhere") or []) + list(q["exclude_prs"])
        twin_excl[q["id"]] = sorted(set(excl))
        row = build(q, "twin", excl)
        assert q["pr_number"] not in row["context_prs"]
        prompts.append(row)
    P = {p["key"]: p for p in prompts}

    # ---------------- pairs
    NF = E.NOT_FOUND_SENTENCE
    title = {}

    def mr_title(n):
        if n not in title:
            title[n] = (load_pr(E.REPO, n) or {}).get("title") or ""
        return title[n]

    def what_as_why(n, cite):
        return WHAT_AS_WHY.format(title=clean_title(mr_title(n)), cite=cite)

    def with_cite(answer, cite):
        return f"{answer.rstrip()} [{cite}]"

    pairs = []
    for q in qs:                                         # refusal: unanswerables (18)
        if q["type"] == "answerable":
            continue
        p = P[f"main:{q['id']}"]
        stored = f0[q["id"]]["response"].strip()
        answered = (not E.abstained_strict(stored)) and bool(re.search(r"\w", E.CITE.sub("", stored)))
        if answered:
            rej, src, cite = stored, "stored_F0_answer", None
        else:
            own = [s for s, n in zip(p["context_short_ids"], [int(c.split("_")[0]) for c in p["context_chunk_ids"]])
                   if n == q["pr_number"]]
            cite = own[0] if own else p["context_short_ids"][0]
            rej, src = what_as_why(q["pr_number"], cite), "what_as_why_title"
        pairs.append({"pair_id": f"unans:{q['id']}", "id": q["id"], "type": q["type"], "family": "refusal",
                      "how": "unans", "rejected_source": src, "prompt_key": p["key"],
                      "chosen": NF, "rejected": rej, "cite_chosen": None, "cite_rejected": cite})
    for q in qs:                                         # refusal: twins (52)
        if q["type"] != "answerable":
            continue
        p = P[f"twin:{q['id']}"]
        cite = p["context_short_ids"][0]
        pairs.append({"pair_id": f"twin:{q['id']}", "id": q["id"], "type": q["type"], "family": "refusal",
                      "how": "twin", "rejected_source": "gold_answer_top_twin_chunk", "prompt_key": p["key"],
                      "chosen": NF, "rejected": with_cite(q["answer"], cite),
                      "cite_chosen": None, "cite_rejected": cite})
    gold_cite = {}
    for q in qs:                                         # grounding (span in context)
        p = P[f"main:{q['id']}"]
        if q["type"] != "answerable" or not (p["span_in_context"] and p["span_in_context"]["any"]):
            continue
        ctx = p["context_chunk_ids"]
        contain = [c for c in ctx if c in set(q["gold_chunks_" + CHUNKING])]
        overlap = [c for c in ctx if c in set(q["overlap_chunks_" + CHUNKING])]
        cid = (contain or overlap)[0]
        cite = E.short_id(cid)
        gold_cite[q["id"]] = {"cite": cite, "contains_quote": bool(contain)}
        chosen = with_cite(q["answer"], cite)
        pairs.append({"pair_id": f"g_nf:{q['id']}", "id": q["id"], "type": q["type"], "family": "grounding",
                      "how": "g_nf", "rejected_source": "not_found_sentence", "prompt_key": p["key"],
                      "chosen": chosen, "rejected": NF, "cite_chosen": cite, "cite_rejected": None})
        pairs.append({"pair_id": f"g_what:{q['id']}", "id": q["id"], "type": q["type"], "family": "grounding",
                      "how": "g_what", "rejected_source": "what_as_why_title", "prompt_key": p["key"],
                      "chosen": chosen, "rejected": what_as_why(q["pr_number"], cite),
                      "cite_chosen": cite, "cite_rejected": cite})

    # ---------------- folds: stratified, deterministic round-robin continuing across strata
    def stratum(q):
        if q["type"] == "answerable":
            s = P[f"main:{q['id']}"]["span_in_context"]
            return "answerable_span" if s and s["any"] else "answerable_nospan"
        return q["type"]
    strata = ["answerable_span", "answerable_nospan", "no_reason", "removed"]
    folds, ptr = {str(k): [] for k in range(N_FOLDS)}, 0
    for s in strata:
        ids = sorted((q["id"] for q in qs if stratum(q) == s), key=lambda i: hkey("fold", i))
        for i in ids:
            folds[str(ptr % N_FOLDS)].append(i)
            ptr += 1
    fold_of = {i: int(k) for k, ids in folds.items() for i in ids}

    # ---------------- ratio subsets and inner sets
    subsets, inner = {}, {}
    for k in range(N_FOLDS):
        train = [p for p in pairs if fold_of[p["id"]] != k]
        R = interleave([p for p in train if p["family"] == "refusal"], "order")
        G = interleave([p for p in train if p["family"] == "grounding"], "order")
        subsets[str(k)] = {"n_training_refusal": len(R), "n_training_grounding": len(G)}
        for name, (ar, ag) in RATIOS.items():
            m = min(len(R) // ar, len(G) // ag)
            subsets[str(k)][name] = {"n_refusal": m * ar, "n_grounding": m * ag,
                                     "refusal": [p["pair_id"] for p in R[:m * ar]],
                                     "grounding": [p["pair_id"] for p in G[:m * ag]]}
        tr = [q for q in qs if fold_of[q["id"]] != k]
        un = sorted((q["id"] for q in tr if q["type"] != "answerable"), key=lambda i: hkey("inner", i))
        an = sorted((q["id"] for q in tr if stratum(q) == "answerable_span"), key=lambda i: hkey("inner", i))
        inner[str(k)] = {"unanswerable": un, "answerable": an[:N_INNER_ANSWERABLE]}

    # ---------------- pair flags (automatic; flagged pairs are kept, never edited)
    flags = []

    def flag(pair_id, name, detail):
        flags.append({"pair_id": pair_id, "flag": name, "detail": detail})
    gold_words = {q["id"]: cwords(q["answer"] if q["type"] == "answerable" else q.get("gold_answer_if_present"))
                  for q in qs}
    by_pr_q = defaultdict(list)
    for q in qs:
        by_pr_q[q["pr_number"]].append(q["id"])
    for pa in pairs:
        q, p = qd[pa["id"]], P[pa["prompt_key"]]
        ctx_texts = [(int(c.split("_")[0]), by_id[c]["text"]) for c in p["context_chunk_ids"]]
        if pa["how"] == "twin" or (pa["how"] == "unans" and q["type"] == "removed"):
            for qt in q["quotes"]:
                runs = [(n, E.longest_shared_run(qt, t)) for n, t in ctx_texts if n != q["pr_number"]]
                n_best, best = max(runs, key=lambda x: x[1]) if runs else (None, 0)
                if best >= 8 or (best >= 5 and best == len(E.words(qt))):
                    flag(pa["pair_id"], "reason_quote_in_other_mr",
                         f"a gold quote shares a {best}-word run with MR {n_best} in this context, so "
                         f"'Not found' may be wrong")
                    break
        if pa["how"] == "twin":
            for n in p["context_prs"]:
                for other in by_pr_q.get(n, []):
                    gw, ow = gold_words[q["id"]], gold_words[other]
                    if other != q["id"] and gw and ow and len(gw & ow) / len(gw | ow) >= 0.3:
                        flag(pa["pair_id"], "similar_question_mr_in_context",
                             f"MR {n} (question {other}) is in the twin context and its gold answer shares "
                             f"{len(gw & ow)}/{len(gw | ow)} content words with this one")
            ctx_words = cwords(" ".join(t for _, t in ctx_texts))
            gw = gold_words[q["id"]]
            if gw and len(gw & ctx_words) / len(gw) >= 0.8:
                flag(pa["pair_id"], "answer_words_in_twin_context",
                     f"{len(gw & ctx_words)}/{len(gw)} of the gold answer's content words occur in the twin "
                     f"context (weak signal)")
        if pa["rejected_source"] == "what_as_why_title":
            t = mr_title(q["pr_number"])
            gold = q["answer"] if q["type"] == "answerable" else (q.get("gold_answer_if_present") or "")
            shared = sorted((cwords(t) & cwords(gold)) - cwords(q["question"]))
            if REASON_MARK.search(t):
                flag(pa["pair_id"], "title_states_reason",
                     f"the MR title contains a reason marker: {t!r}")
            elif len(shared) >= 2:
                flag(pa["pair_id"], "title_overlaps_gold_reason",
                     f"the title shares {len(shared)} content words with the gold answer that are not in the "
                     f"question {shared}: {t!r}")
        if pa["rejected_source"] == "stored_F0_answer":
            if E.hedged(pa["rejected"]):
                flag(pa["pair_id"], "rejected_is_hedged",
                     "the stored F0 answer also contains 'Not found', so it is partly a refusal")
            own = {f"PR{q['pr_number']}-c"}
            if any(c.startswith(tuple(own)) for c in re.findall(r"PR\d+-c\d+", pa["rejected"])):
                flag(pa["pair_id"], "stored_answer_cites_own_mr",
                     "the stored F0 answer cites the question's own MR: the no-reason label rests on a "
                     "human judgement that this text is not the reason")
        if pa["family"] == "grounding":
            s = p["span_in_context"]
            if not gold_cite[q["id"]]["contains_quote"]:
                flag(pa["pair_id"], "cited_chunk_overlaps_only",
                     "no context chunk fully contains a gold quote; the chosen answer cites an overlapping chunk")
            if s and not s["all"]:
                flag(pa["pair_id"], "span_partly_in_context",
                     "only some of the gold quotes are fully inside the context")
    flag_tests = {
        "reason_quote_in_other_mr": "twin and removed pairs: a gold quote shares >= 8 consecutive words (or all "
                                    "of a quote of >= 5 words) with a context chunk from another MR",
        "similar_question_mr_in_context": "twin pairs: another of the 70 questions' MR is in the twin context and "
                                          "the two gold answers have content-word Jaccard >= 0.3",
        "answer_words_in_twin_context": "twin pairs: >= 80% of the gold answer's content words occur somewhere "
                                        "in the twin context (weak, lexical)",
        "title_states_reason": "WHAT-as-WHY pairs: the MR title contains a reason marker (because, so that, "
                               "to avoid, to prevent, to allow, to support, to enable, to ensure, due to, since...)",
        "title_overlaps_gold_reason": "WHAT-as-WHY pairs: the title shares >= 2 content words with the gold "
                                      "answer that do not occur in the question (topic words removed)",
        "rejected_is_hedged": "stored-F0 rejections that contain 'Not found' plus other text",
        "stored_answer_cites_own_mr": "stored-F0 rejections that cite the question's own MR",
        "cited_chunk_overlaps_only": "grounding pairs whose cited gold chunk only overlaps (does not contain) a quote",
        "span_partly_in_context": "grounding pairs where span_in_context.any is true but .all is false",
    }

    # ---------------- write
    print("writing prepare outputs:")
    put(a, "prompts.jsonl", jsonl_text(prompts))
    put(a, "folds.json", json_text(folds))
    put(a, "inner_sets.json", json_text(inner))
    put(a, "pairs.jsonl", jsonl_text(pairs))
    put(a, "ratio_subsets.json", json_text(subsets))
    put(a, "pair_flags.json", json_text({"tests": flag_tests, "flags": flags,
                                         "note": "Flags are automatic and informational; no flagged pair "
                                                 "is removed or edited (pairs are built by script only)."}))
    fam = Counter((p["family"], p["how"], p["rejected_source"]) for p in pairs)
    summary = {
        "contexts_equal_gen_F0": True, "n_main": sum(p["kind"] == "main" for p in prompts),
        "n_twin": sum(p["kind"] == "twin" for p in prompts),
        "answerable_span_in_context_any": sum(1 for p in prompts if p["kind"] == "main" and p["span_in_context"]
                                              and p["span_in_context"]["any"]),
        "answerable_span_in_context_all": sum(1 for p in prompts if p["kind"] == "main" and p["span_in_context"]
                                              and p["span_in_context"]["all"]),
        "twin_exclusions_beyond_own_mr": {i: e for i, e in twin_excl.items() if len(e) > 1},
        "fold_sizes": {k: {"total": len(v), **dict(Counter(stratum(qd[i]) for i in v))} for k, v in folds.items()},
        "pairs": {f"{f}/{h}/{s}": n for (f, h, s), n in sorted(fam.items())},
        "pairs_by_family": dict(Counter(p["family"] for p in pairs)),
        "ratio_subset_sizes": {k: {r: [v[r]["n_refusal"], v[r]["n_grounding"]] for r in RATIOS}
                               for k, v in subsets.items()},
        "inner_sizes": {k: [len(v["unanswerable"]), len(v["answerable"])] for k, v in inner.items()},
        "flags": dict(Counter(f["flag"] for f in flags)),
        "n_flagged_pairs": len({f["pair_id"] for f in flags}),
        "what_as_why_template": WHAT_AS_WHY,
        "chunk_set": info["chunk_set"], "prompt_sha1": pr["sha1"], "budget": E.BUDGET,
    }
    put(a, "prepare_summary.json", json_text(summary))
    print(json.dumps({k: summary[k] for k in ("answerable_span_in_context_any", "answerable_span_in_context_all",
                                              "fold_sizes", "pairs", "ratio_subset_sizes", "flags")}, indent=1))
    print("PREPARE OK")


# ================================================================== the model (GPU steps)
class LM:
    def __init__(self, a):
        import torch
        import transformers
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self.torch = torch
        self.dev = a.device or ("cuda" if torch.cuda.is_available() else "cpu")
        if self.dev != "cuda" and a.model == MODEL and not a.device:
            raise SystemExit("STOP: no CUDA GPU visible to torch. Run preflight and follow its fix.")
        dtype = getattr(torch, a.dtype)
        rev = a.revision
        if rev is None and os.path.exists(outp(a, "model_revision.json")):
            r = rjson(outp(a, "model_revision.json"))
            rev = r["revision"] if r["model"] == a.model else None
        if a.model == MODEL and rev is None:
            raise SystemExit("STOP: no recorded model revision. Run preflight first.")
        kw = {"revision": rev} if rev else {}
        tv = tuple(int(x) for x in re.findall(r"\d+", transformers.__version__)[:2])
        dkey = "dtype" if tv >= (4, 56) else "torch_dtype"
        print(f"loading {a.model} rev {rev} as {a.dtype} on {self.dev} ...")
        t0 = time.time()
        self.tok = AutoTokenizer.from_pretrained(a.model, **kw)
        self.m = AutoModelForCausalLM.from_pretrained(a.model, **{dkey: dtype}, **kw).to(self.dev).eval()
        if next(self.m.parameters()).dtype != dtype:
            raise SystemExit(f"STOP: model loaded as {next(self.m.parameters()).dtype}, not {a.dtype}")
        self.revision = getattr(self.m.config, "_commit_hash", None) or rev
        if rev and self.revision and self.revision != rev:
            raise SystemExit(f"STOP: loaded revision {self.revision} != recorded {rev}")
        self.layers = self.m.model.layers
        if a.model == MODEL and (len(self.layers) != MODEL_N_LAYERS or self.m.config.hidden_size != MODEL_HIDDEN):
            raise SystemExit("STOP: unexpected model shape")
        eos = self.m.generation_config.eos_token_id
        self.eos = set(eos if isinstance(eos, (list, tuple)) else [eos]) | {self.tok.eos_token_id}
        self.pad = self.tok.pad_token_id if self.tok.pad_token_id is not None else sorted(self.eos)[0]
        self.info = {"model": a.model, "revision": self.revision, "dtype": a.dtype, "device": self.dev,
                     "torch": torch.__version__, "transformers": transformers.__version__,
                     "code_sha": CODE_SHA, "git": git_state(a.repo),
                     "gpu": torch.cuda.get_device_name(0) if self.dev == "cuda" else None}
        print(f"  loaded in {time.time() - t0:.0f}s; {len(self.layers)} decoder layers, hidden "
              f"{self.m.config.hidden_size}")

    def encode(self, system, user):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        text = self.tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        return self.tok(text, add_special_tokens=False).input_ids

    def steer_hook(self, delta32):
        """Adds delta to the decoder layer's output: at the LAST prompt position during prefill
        (the first forward call) and at the single new position of every decode call."""
        torch, state = self.torch, {"calls": 0}

        def hook(module, inputs, output):
            h = output[0] if isinstance(output, tuple) else output
            if state["calls"] == 0:
                h2 = h.clone()
                h2[:, -1, :] = (h[:, -1, :].float() + delta32).to(h.dtype)
            else:
                if h.shape[1] != 1:
                    raise RuntimeError(f"decode call with {h.shape[1]} positions (expected 1)")
                h2 = (h.float() + delta32).to(h.dtype)
            state["calls"] += 1
            return (h2,) + tuple(output[1:]) if isinstance(output, tuple) else h2
        return hook, state

    def generate(self, system, user, layer=None, vec=None, strength=0.0, max_new=MAX_NEW):
        torch = self.torch
        ids = self.encode(system, user)
        x = torch.tensor([ids], device=self.dev)
        handle, state = None, None
        if strength and vec is not None:
            delta = torch.as_tensor(vec, dtype=torch.float32, device=self.dev) * float(strength)
            hook, state = self.steer_hook(delta)
            handle = self.layers[layer].register_forward_hook(hook)
        t0 = time.time()
        try:
            with torch.inference_mode():
                out = self.m.generate(input_ids=x, attention_mask=torch.ones_like(x), max_new_tokens=max_new,
                                      do_sample=False, temperature=None, top_p=None, top_k=None,
                                      pad_token_id=self.pad, use_cache=True)
        finally:
            if handle is not None:
                handle.remove()
        new = out[0, len(ids):].tolist()
        eos = bool(new) and new[-1] in self.eos
        if state is not None and state["calls"] != len(new):
            raise RuntimeError(f"hook ran {state['calls']} times for {len(new)} new tokens")
        return {"response": self.tok.decode(new, skip_special_tokens=True), "n_prompt_tokens": len(ids),
                "n_new_tokens": len(new), "eos": eos, "hit_max": len(new) >= max_new and not eos,
                "seconds": round(time.time() - t0, 2)}

    def acts(self, system, user, response, layers):
        """Mean over the RESPONSE token positions of each layer's output (teacher forcing, no
        hook on the residual stream, no cache). Returns {layer: (mean vector, mean token norm)}."""
        torch = self.torch
        p = self.encode(system, user)
        r = self.tok(response, add_special_tokens=False).input_ids
        x = torch.tensor([p + r], device=self.dev)
        cap, top = {}, max(layers)

        class _Done(Exception):
            pass

        def mk(L):
            def hook(module, inputs, output):
                h = output[0] if isinstance(output, tuple) else output
                cap[L] = h[0, len(p):, :].float()
                if L == top:
                    raise _Done
            return hook
        hs = [self.layers[L].register_forward_hook(mk(L)) for L in layers]
        try:
            with torch.inference_mode():
                try:
                    self.m.model(input_ids=x, use_cache=False)
                except _Done:
                    pass
        finally:
            for h in hs:
                h.remove()
        return {L: (cap[L].mean(0).cpu().numpy(), float(cap[L].norm(dim=-1).mean())) for L in layers}, len(p), len(r)

    def n_hooks(self):
        return sum(len(l._forward_hooks) for l in self.layers)


def load_lm(a):
    return LM(a)


# ================================================================== smoke (GPU)
def cmd_smoke(a):
    import numpy as np
    prompts = {p["key"]: p for p in rjsonl(outp(a, "prompts.jsonl"))}
    mains = [p for p in prompts.values() if p["kind"] == "main"]
    pick = [sorted((p for p in mains if p["type"] == "answerable"), key=lambda p: hkey("smoke", p["id"]))[0],
            sorted((p for p in mains if p["type"] != "answerable"), key=lambda p: hkey("smoke", p["id"]))[0]]
    lm = load_lm(a)
    torch = lm.torch
    L = a.layers[len(a.layers) // 2]
    res, fails = {"layer": L, "prompts": [p["key"] for p in pick], "checks": {}}, []

    def check(name, cond, detail=""):
        res["checks"][name] = bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'}  {name} {detail}")
        if not cond:
            fails.append(name)
    max_new = a.max_new
    # response-token mask: prompt ids + response ids must be a prefix of the full conversation
    for resp in ["Not found in the provided PRs", "Because of a reason. [PR1-c0]"]:
        p = pick[0]
        ids_p = lm.encode(p["system"], p["user"])
        ids_r = lm.tok(resp, add_special_tokens=False).input_ids
        msgs = [{"role": "system", "content": p["system"]}, {"role": "user", "content": p["user"]},
                {"role": "assistant", "content": resp}]
        full = lm.tok(lm.tok.apply_chat_template(msgs, tokenize=False), add_special_tokens=False).input_ids
        check(f"response mask matches the chat template [{resp[:12]!r}]",
              full[:len(ids_p) + len(ids_r)] == ids_p + ids_r)
    gens = {}
    for p in pick:
        g1 = lm.generate(p["system"], p["user"], max_new=max_new)
        g2 = lm.generate(p["system"], p["user"], max_new=max_new)
        gens[p["key"]] = g1
        print(f"  {p['key']}: {g1['n_prompt_tokens']} prompt tokens, {g1['n_new_tokens']} new, {g1['seconds']}s: "
              f"{g1['response'][:90]!r}")
        check(f"greedy output identical twice [{p['key']}]", g1["response"] == g2["response"])
    # a fixed random direction, scaled to 4x the typical residual norm at the last prompt position
    acts, _, _ = lm.acts(pick[0]["system"], pick[0]["user"], " Not", [L])
    norm = acts[L][1]
    g = torch.Generator().manual_seed(0)
    v = torch.randn(lm.m.config.hidden_size, generator=g)
    v = (v / v.norm() * 4 * norm).numpy()
    res["random_vector_norm"] = float(np.linalg.norm(v))
    changed = []
    for p in pick:
        s = lm.generate(p["system"], p["user"], layer=L, vec=v, strength=1.0, max_new=max_new)
        changed.append(s["response"] != gens[p["key"]]["response"])
        print(f"  steered {p['key']}: {s['response'][:90]!r}")
    check("hook changes the output", any(changed), f"({sum(changed)}/{len(changed)} prompts changed)")
    check("no hook left on any layer after steering", lm.n_hooks() == 0)
    for p in pick:
        r = lm.generate(p["system"], p["user"], max_new=max_new)
        check(f"removing the hook restores the unsteered output [{p['key']}]",
              r["response"] == gens[p["key"]]["response"])
    z = lm.generate(pick[0]["system"], pick[0]["user"], layer=L, vec=v * 0.0, strength=1.0, max_new=max_new)
    check("a zero vector through the hook gives the unsteered output",
          z["response"] == gens[pick[0]["key"]]["response"])
    # prefill: only the last prompt position is changed
    ids = torch.tensor([lm.encode(pick[0]["system"], pick[0]["user"])], device=lm.dev)
    with torch.inference_mode():
        h0 = lm.m.model(input_ids=ids, use_cache=False).last_hidden_state[0, -2:].float()
        hook, _ = lm.steer_hook(torch.as_tensor(v, dtype=torch.float32, device=lm.dev))
        hd = lm.layers[L].register_forward_hook(hook)
        try:
            h1 = lm.m.model(input_ids=ids, use_cache=False).last_hidden_state[0, -2:].float()
        finally:
            hd.remove()
    check("prefill: position before the last is untouched", torch.equal(h0[0], h1[0]))
    check("prefill: last prompt position is changed", not torch.equal(h0[1], h1[1]))
    # timing estimate
    secs = [x["seconds"] for x in gens.values()]
    toks = [x["n_new_tokens"] for x in gens.values()]
    res["seconds_per_answer"] = secs
    res["new_tokens"] = toks
    if a.device != "cpu" and lm.dev == "cuda":
        res["peak_vram_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
        print(f"  peak VRAM {res['peak_vram_gib']} GiB")
    per = sum(secs) / len(secs)
    n_inner = len(RATIOS) * N_FOLDS * 28 * len(a.layers) * len(STRENGTHS)
    est = (n_inner + 70 + 3 * 70) * per + 164 * 2 * 0.5
    res["estimated_main_hours"] = round(est / 3600, 1)
    print(f"  about {per:.1f}s per answer -> main stage roughly {est / 3600:.1f} h "
          f"(longer if steering makes long or looping answers)")
    res["run"] = lm.info
    with open(outp(a, "smoke.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json_text(res))
    if fails:
        print(f"\nSMOKE FAILED: {fails}")
        sys.exit(3)
    print("\nSMOKE OK")


# ================================================================== vectors (GPU, then CPU)
def safe(pid):
    return pid.replace(":", "_")


def cmd_vectors(a):
    import numpy as np
    pairs = rjsonl(outp(a, "pairs.jsonl"))
    prompts = {p["key"]: p for p in rjsonl(outp(a, "prompts.jsonl"))}
    adir = outp(a, "acts")
    os.makedirs(adir, exist_ok=True)
    todo = [p for p in pairs if not os.path.exists(os.path.join(adir, safe(p["pair_id"]) + ".npz"))]
    print(f"{len(pairs) - len(todo)} pairs already have activations; {len(todo)} to do")
    if todo:
        lm = load_lm(a)
        for i, p in enumerate(todo, 1):
            pr = prompts[p["prompt_key"]]
            t0 = time.time()
            c, n_p, n_c = lm.acts(pr["system"], pr["user"], p["chosen"], a.layers)
            r, _, n_r = lm.acts(pr["system"], pr["user"], p["rejected"], a.layers)
            arrs = {}
            for L in a.layers:
                arrs[f"chosen_{L}"], arrs[f"rejected_{L}"] = c[L][0], r[L][0]
                arrs[f"norm_chosen_{L}"], arrs[f"norm_rejected_{L}"] = np.float32(c[L][1]), np.float32(r[L][1])
            arrs["meta"] = np.array(json.dumps({"pair_id": p["pair_id"], "n_prompt": n_p, "n_chosen": n_c,
                                                "n_rejected": n_r, "layers": a.layers, "run": lm.info}))
            tmp = os.path.join(adir, safe(p["pair_id"]) + ".tmp.npz")
            np.savez(tmp, **arrs)
            os.replace(tmp, os.path.join(adir, safe(p["pair_id"]) + ".npz"))
            print(f"  [{i}/{len(todo)}] {p['pair_id']:<16} prompt {n_p} tok, chosen {n_c}, rejected {n_r}, "
                  f"{time.time() - t0:.1f}s")
    build_vectors(a)


def build_vectors(a):
    import numpy as np
    pairs = rjsonl(outp(a, "pairs.jsonl"))
    subsets = rjson(outp(a, "ratio_subsets.json"))
    diff, norms = {}, defaultdict(list)
    for p in pairs:
        z = np.load(os.path.join(outp(a, "acts"), safe(p["pair_id"]) + ".npz"))
        for L in a.layers:
            diff[(p["pair_id"], L)] = z[f"chosen_{L}"].astype(np.float64) - z[f"rejected_{L}"].astype(np.float64)
            norms[L] += [float(z[f"norm_chosen_{L}"]), float(z[f"norm_rejected_{L}"])]
    typical = {L: float(np.mean(norms[L])) for L in a.layers}
    vecs, info = {}, {"typical_residual_norm": {str(L): typical[L] for L in a.layers}, "vectors": [],
                      "note": "typical_residual_norm = mean over all pair passes of the mean per-token L2 "
                              "norm of the layer output at response positions"}
    for k, by_ratio in subsets.items():
        for ratio in RATIOS:
            ids = by_ratio[ratio]["refusal"] + by_ratio[ratio]["grounding"]
            for L in a.layers:
                v = np.mean([diff[(i, L)] for i in ids], axis=0)
                vr = np.mean([diff[(i, L)] for i in by_ratio[ratio]["refusal"]], axis=0)
                vg = np.mean([diff[(i, L)] for i in by_ratio[ratio]["grounding"]], axis=0)
                cos = float(vr @ vg / (np.linalg.norm(vr) * np.linalg.norm(vg)))
                vecs[f"{ratio}|{k}|{L}"] = v.astype(np.float32)
                info["vectors"].append({"ratio": ratio, "fold": int(k), "layer": L, "n_pairs": len(ids),
                                        "norm": float(np.linalg.norm(v)),
                                        "norm_over_typical_residual": float(np.linalg.norm(v)) / typical[L],
                                        "cos_refusal_vs_grounding_part": cos})
    stab = []
    for ratio in RATIOS:
        for L in a.layers:
            vs = [vecs[f"{ratio}|{k}|{L}"] for k in subsets]
            cs = [float(x @ y / (np.linalg.norm(x) * np.linalg.norm(y))) for i, x in enumerate(vs) for y in vs[i + 1:]]
            stab.append({"ratio": ratio, "layer": L, "min_cos_between_folds": min(cs), "mean_cos": sum(cs) / len(cs)})
    info["fold_stability"] = stab
    np.savez(outp(a, "vectors.npz"), **vecs)
    with open(outp(a, "vector_info.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json_text(info))
    print("layer  typical residual norm   vector norm / typical (min-max over folds and ratios)")
    for L in a.layers:
        r = [x["norm_over_typical_residual"] for x in info["vectors"] if x["layer"] == L]
        print(f"  {L:<5}{typical[L]:>12.1f}            {min(r):.3f} - {max(r):.3f}")
    print(f"{len(vecs)} vectors -> out/vectors.npz, out/vector_info.json")
    print("VECTORS OK")


def load_vectors(a):
    import numpy as np
    z = np.load(outp(a, "vectors.npz"))
    return {k: z[k] for k in z.files}


# ================================================================== generation steps
def gen_row(E, lm, key, step, prompt, q, g, fold=None, ratio=None, layer=None, strength=0.0, extra=None):
    row = {"key": key, "step": step, "id": prompt["id"], "type": prompt["type"], "prompt_key": prompt["key"],
           "fold": fold, "ratio": ratio, "layer": layer, "strength": strength}
    row.update(g)
    row.update(outcomes(E, g["response"], prompt, q))
    row["degenerate"] = degenerate(g["response"], g["hit_max"])
    if extra:
        row.update(extra)
    row["run"] = lm.info if lm is not None else None
    return row


def show(row):
    tag = "REFUSE" if row["abstained"] else ("ANSWER" if row["answered"] else "EMPTY ")
    print(f"  {row['key']:<34} {tag} {row['n_new_tokens']:>4} tok {row['seconds']:>5}s "
          f"{'DEGEN ' + ','.join(row['degenerate']) if row['degenerate'] else ''} {row['response'][:60]!r}")


class Lazy:
    def __init__(self, a):
        self.a, self.lm = a, None

    def get(self):
        if self.lm is None:
            self.lm = load_lm(self.a)
        return self.lm


def cmd_baseline(a):
    E = exp2(a)
    qd = questions(a)
    mains = [p for p in rjsonl(outp(a, "prompts.jsonl")) if p["kind"] == "main"]
    app = Appender(outp(a, "gen_baseline.jsonl"))
    lz = Lazy(a)
    todo = [p for p in mains if f"base|{p['id']}" not in app]
    print(f"baseline: {len(mains) - len(todo)} done, {len(todo)} to generate")
    for p in todo:
        lm = lz.get()
        g = lm.generate(p["system"], p["user"], max_new=a.max_new)
        row = gen_row(E, lm, f"base|{p['id']}", "baseline", p, qd[p["id"]], g)
        app.add(row)
        show(row)
    print("BASELINE OK")


def need_baseline(a, ids):
    rows = {r["id"]: r for r in rjsonl(outp(a, "gen_baseline.jsonl"))}
    missing = [i for i in ids if i not in rows]
    if missing:
        raise SystemExit(f"STOP: baseline is missing {len(missing)} questions; run baseline first")
    return rows


def settings(a):
    return [(None, 0.0)] + [(L, s) for L in a.layers for s in STRENGTHS]


def cmd_select(a):
    E = exp2(a)
    qd = questions(a)
    P = {p["key"]: p for p in rjsonl(outp(a, "prompts.jsonl"))}
    inner = rjson(outp(a, "inner_sets.json"))
    base = need_baseline(a, [p["id"] for p in P.values() if p["kind"] == "main"])
    vecs = load_vectors(a)
    app = Appender(outp(a, "gen_inner.jsonl"))
    lz = Lazy(a)
    jobs = []
    for ratio in a.ratios:
        for k in sorted(inner, key=int):
            for L in a.layers:
                for s in STRENGTHS:
                    for i in inner[k]["unanswerable"] + inner[k]["answerable"]:
                        key = f"inner|{ratio}|f{k}|L{L}|s{s}|{i}"
                        if key not in app:
                            jobs.append((key, ratio, k, L, s, i))
    print(f"select: {len(app.rows)} inner answers done, {len(jobs)} to generate")
    for n, (key, ratio, k, L, s, i) in enumerate(jobs, 1):
        lm = lz.get()
        p = P[f"main:{i}"]
        g = lm.generate(p["system"], p["user"], layer=L, vec=vecs[f"{ratio}|{k}|{L}"], strength=s, max_new=a.max_new)
        row = gen_row(E, lm, key, "inner", p, qd[i], g, fold=int(k), ratio=ratio, layer=L, strength=s)
        app.add(row)
        if n % 25 == 0 or n == len(jobs):
            print(f"  [{n}/{len(jobs)}]", end="")
            show(row)
    choose(a, app.rows, base, inner)


def choose(a, inner_rows, base, inner):
    sel = {}
    print("\nchosen settings (inner J on training MRs only; optimistic, not reported as a result):")
    for ratio in a.ratios:
        sel[ratio] = {}
        for k in sorted(inner, key=int):
            un, an = inner[k]["unanswerable"], inner[k]["answerable"]
            table = []
            for L, s in settings(a):
                def row(i):
                    return base[i] if s == 0 else inner_rows[f"inner|{ratio}|f{k}|L{L}|s{s}|{i}"]
                rows_u, rows_a = [row(i) for i in un], [row(i) for i in an]
                refused = sum(r["abstained"] for r in rows_u)
                answered = sum(r["answered"] for r in rows_a)
                deg = sum(bool(r["degenerate"]) for r in rows_u + rows_a)
                J = Fraction(refused, len(un)) + Fraction(answered, len(an)) - 1
                dropped = Fraction(deg, len(un) + len(an)) > DEGEN_MAX_SHARE
                table.append({"layer": L, "strength": s, "unans_refused": refused, "n_unans": len(un),
                              "ans_answered": answered, "n_ans": len(an), "degenerate": deg,
                              "J": float(J), "J_exact": str(J), "dropped_degenerate": dropped, "_J": J})
            ok = [t for t in table if not t["dropped_degenerate"]]
            fallback = not ok
            pool = ok or [t for t in table if t["strength"] == 0]
            best = sorted(pool, key=lambda t: (-t["_J"], t["strength"],
                                               abs((t["layer"] if t["layer"] is not None else a.prefer_layer)
                                                   - a.prefer_layer),
                                               t["layer"] if t["layer"] is not None else -1))[0]
            for t in table:
                t.pop("_J")
            sel[ratio][k] = {"layer": best["layer"], "strength": best["strength"], "J": best["J"],
                             "all_settings_dropped": fallback, "table": table}
            print(f"  {ratio} fold {k}: layer {best['layer']} strength {best['strength']} "
                  f"(J {best['J']:+.3f}; unsteered J {table[0]['J']:+.3f})" + ("  ALL DROPPED -> unsteered" if fallback else ""))
    with open(outp(a, "selection.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json_text(sel))
    print("SELECT OK")


def cmd_test(a):
    E = exp2(a)
    qd = questions(a)
    P = {p["key"]: p for p in rjsonl(outp(a, "prompts.jsonl"))}
    folds = rjson(outp(a, "folds.json"))
    sel = rjson(outp(a, "selection.json"))
    base = need_baseline(a, list(qd))
    vecs = load_vectors(a)
    app = Appender(outp(a, "gen_test.jsonl"))
    lz = Lazy(a)
    for ratio in a.ratios:
        if ratio not in sel:
            raise SystemExit(f"STOP: no selection for {ratio}; run select first")
        for k in sorted(folds, key=int):
            st = sel[ratio][k]
            for i in folds[k]:
                key = f"test|{ratio}|{i}"
                if key in app:
                    continue
                p = P[f"main:{i}"]
                if st["strength"] == 0:
                    b = base[i]
                    g = {f: b[f] for f in ("response", "n_prompt_tokens", "n_new_tokens", "eos", "hit_max", "seconds")}
                    row = gen_row(E, None, key, "test", p, qd[i], g, fold=int(k), ratio=ratio,
                                  extra={"reused_baseline": True})
                    row["run"] = b["run"]
                else:
                    lm = lz.get()
                    g = lm.generate(p["system"], p["user"], layer=st["layer"], vec=vecs[f"{ratio}|{k}|{st['layer']}"],
                                    strength=st["strength"], max_new=a.max_new)
                    row = gen_row(E, lm, key, "test", p, qd[i], g, fold=int(k), ratio=ratio, layer=st["layer"],
                                  strength=st["strength"], extra={"reused_baseline": False})
                app.add(row)
                show(row)
    print("TEST OK")


def cmd_sweep(a):
    E = exp2(a)
    qd = questions(a)
    P = {p["key"]: p for p in rjsonl(outp(a, "prompts.jsonl"))}
    folds = rjson(outp(a, "folds.json"))
    fold_of = {i: k for k, ids in folds.items() for i in ids}
    vecs = load_vectors(a)
    app = Appender(outp(a, "gen_sweep.jsonl"))
    lz = Lazy(a)
    jobs = [(r, L, s, i) for r in a.ratios for L in a.layers for s in STRENGTHS for i in sorted(qd)
            if f"sweep|{r}|L{L}|s{s}|{i}" not in app]
    print(f"sweep (descriptive only; nothing is chosen from it): {len(jobs)} answers to generate")
    for n, (r, L, s, i) in enumerate(jobs, 1):
        lm = lz.get()
        p, k = P[f"main:{i}"], fold_of[i]
        g = lm.generate(p["system"], p["user"], layer=L, vec=vecs[f"{r}|{k}|{L}"], strength=s, max_new=a.max_new)
        row = gen_row(E, lm, f"sweep|{r}|L{L}|s{s}|{i}", "sweep", p, qd[i], g, fold=int(k), ratio=r, layer=L,
                      strength=s)
        app.add(row)
        if n % 25 == 0 or n == len(jobs):
            print(f"  [{n}/{len(jobs)}]", end="")
            show(row)
    print("SWEEP OK")


# ================================================================== stats (CPU)
def arm_rows(a):
    base = {r["id"]: r for r in rjsonl(outp(a, "gen_baseline.jsonl"))}
    test = defaultdict(dict)
    for r in rjsonl(outp(a, "gen_test.jsonl")):
        test[r["ratio"]][r["id"]] = r
    return base, test


def cmd_stats(a):
    E = exp2(a)
    qd = questions(a)
    P = {p["key"]: p for p in rjsonl(outp(a, "prompts.jsonl"))}
    base, test = arm_rows(a)
    ans = sorted(i for i, q in qd.items() if q["type"] == "answerable")
    un = sorted(i for i, q in qd.items() if q["type"] != "answerable")
    if len(base) != 70:
        raise SystemExit("STOP: baseline incomplete")
    for r in RATIOS:
        if len(test.get(r, {})) != 70:
            raise SystemExit(f"STOP: test incomplete for {r} ({len(test.get(r, {}))}/70)")
    out = {"wording": "activation steering (no weights changed; not reinforcement learning, not fine-tuning)"}
    # pipeline check: HF unsteered vs the stored Ollama F0 rows, answer vs refuse
    f0 = {r["id"]: r for r in E.read_jsonl(os.path.join(E.OUT, "gen_F0.jsonl"))}
    tab = Counter()
    for i in qd:
        o = outcomes(E, f0[i]["response"], P[f"main:{i}"], qd[i])["answered"]
        h = base[i]["answered"]
        tab[(("ollama_answered" if o else "ollama_not"), ("hf_answered" if h else "hf_not"))] += 1
    agree = tab[("ollama_answered", "hf_answered")] + tab[("ollama_not", "hf_not")]
    po = agree / 70
    pa_ = (tab[("ollama_answered", "hf_answered")] + tab[("ollama_answered", "hf_not")]) / 70
    pb_ = (tab[("ollama_answered", "hf_answered")] + tab[("ollama_not", "hf_answered")]) / 70
    pe = pa_ * pb_ + (1 - pa_) * (1 - pb_)
    out["pipeline_check_hf_vs_ollama_F0"] = {
        "agree": agree, "n": 70, "kappa": round((po - pe) / (1 - pe), 3) if pe < 1 else None,
        "table": {f"{x}/{y}": n for (x, y), n in sorted(tab.items())},
        "ollama_unans_answered": sum(outcomes(E, f0[i]["response"], P[f"main:{i}"], qd[i])["answered"] for i in un),
        "note": "Pipeline check only. The baseline for every test is the HF model unsteered, never Ollama."}
    # per-arm counts
    arms = {"baseline": base, **{f"steered {r}": test[r] for r in RATIOS}}
    counts = []
    for name, rows in arms.items():
        counts.append({"arm": name,
                       "unans_answered_of_18": sum(rows[i]["answered"] for i in un),
                       "answered_of_52": sum(rows[i]["answered"] for i in ans),
                       "overlap_cited_of_52": sum(rows[i]["overlap_cited"] for i in ans),
                       "contain_cited_of_52": sum(bool(rows[i]["contain_cited"]) for i in ans),
                       "refused_with_span_in_context": sum(rows[i]["abstained"] and bool(
                           P[f"main:{i}"]["span_in_context"] and P[f"main:{i}"]["span_in_context"]["any"]) for i in ans),
                       "hedged_of_70": sum(rows[i]["hedged"] for i in qd),
                       "degenerate_of_70": sum(bool(rows[i]["degenerate"]) for i in qd),
                       "empty_of_70": sum(rows[i]["empty"] for i in qd),
                       "n_steered_questions": sum(1 for i in qd if rows[i].get("strength")) if name != "baseline" else 0})
    out["arms"] = counts
    # the Holm family of 9
    fam = []
    for r in RATIOS:
        for outcome, ids, field in (("unanswerable answered (primary)", un, "answered"),
                                    ("answered", ans, "answered"), ("overlap-cited", ans, "overlap_cited")):
            b = sum(bool(base[i][field]) and not test[r][i][field] for i in ids)
            c = sum(not base[i][field] and bool(test[r][i][field]) for i in ids)
            fam.append({"ratio": r, "outcome": outcome, "n": len(ids),
                        "baseline": sum(bool(base[i][field]) for i in ids),
                        "steered": sum(bool(test[r][i][field]) for i in ids),
                        "only_baseline": b, "only_steered": c, "p": mcnemar_exact(b, c)})
    for f, ph in zip(fam, holm([f["p"] for f in fam])):
        f["p_holm"] = ph
    out["tests"] = fam
    # selection summary
    sel = rjson(outp(a, "selection.json"))
    out["selection"] = {r: {k: {"layer": v["layer"], "strength": v["strength"], "inner_J": v["J"],
                                "unsteered_inner_J": v["table"][0]["J"], "all_dropped": v["all_settings_dropped"]}
                            for k, v in sel[r].items()} for r in sel}
    # secondary: correctness from Clifton's labels
    lab_path = a.labels or outp(a, "blind_sheet_labels.csv")
    if os.path.exists(lab_path):
        out["correctness"] = correctness(a, lab_path, qd, ans, base, test)
    else:
        out["correctness"] = None
        print(f"(no labels at {lab_path}: correctness skipped)")
    # optional sweep (descriptive)
    sw = rjsonl(outp(a, "gen_sweep.jsonl"))
    if sw:
        grid = defaultdict(list)
        for r in sw:
            grid[(r["ratio"], r["layer"], r["strength"])].append(r)
        rows = [{"ratio": "none", "layer": None, "strength": 0.0,
                 "unans_refused_share": sum(base[i]["abstained"] for i in un) / len(un),
                 "ans_answered_share": sum(base[i]["answered"] for i in ans) / len(ans),
                 "degenerate": sum(bool(base[i]["degenerate"]) for i in qd), "n": 70}]
        for (r, L, s), rs in sorted(grid.items()):
            u = [x for x in rs if x["type"] != "answerable"]
            an_ = [x for x in rs if x["type"] == "answerable"]
            rows.append({"ratio": r, "layer": L, "strength": s,
                         "unans_refused_share": sum(x["abstained"] for x in u) / max(1, len(u)),
                         "ans_answered_share": sum(x["answered"] for x in an_) / max(1, len(an_)),
                         "degenerate": sum(bool(x["degenerate"]) for x in rs), "n": len(rs)})
        out["sweep"] = rows
        write_csv(outp(a, "sweep.csv"), rows)
        try:
            plot_sweep(a, rows)
        except Exception as e:
            print(f"(sweep figure skipped: {e})")
    with open(outp(a, "stats.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json_text(out))
    write_csv(outp(a, "stats_tests.csv"), fam)
    write_csv(outp(a, "stats_arms.csv"), counts)
    print("pipeline check (HF unsteered vs Ollama F0, answer vs refuse):",
          out["pipeline_check_hf_vs_ollama_F0"]["agree"], "/ 70 agree")
    print("\narm counts:")
    for c in counts:
        print("  " + ", ".join(f"{k}={v}" for k, v in c.items()))
    print("\nexact McNemar vs HF baseline, two-sided, one Holm family of 9:")
    for f in fam:
        print(f"  {f['ratio']}  {f['outcome']:<33} n={f['n']:<3} base {f['baseline']:>2} steered {f['steered']:>2} "
              f"only-base/only-steered {f['only_baseline']}/{f['only_steered']}  p={f['p']:.4f} holm={f['p_holm']:.4f}")
    print("STATS OK")


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


def plot_sweep(a, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 5))
    marks = {"40:60": "o", "50:50": "s", "60:40": "^"}
    for r in rows:
        if r["ratio"] == "none":
            ax.scatter(r["ans_answered_share"], r["unans_refused_share"], c="k", marker="*", s=150, label="unsteered")
        else:
            ax.scatter(r["ans_answered_share"], r["unans_refused_share"], marker=marks[r["ratio"]], s=25 + 25 * r["strength"])
            ax.annotate(f"L{r['layer']}x{r['strength']:g}", (r["ans_answered_share"], r["unans_refused_share"]), fontsize=6)
    ax.set_xlabel("answerable answered (share of 52)")
    ax.set_ylabel("unanswerable refused (share of 18)")
    ax.set_title("Activation steering sweep (descriptive; out-of-fold vectors)")
    ax.legend(loc="lower left", fontsize=7)
    fig.tight_layout()
    fig.savefig(outp(a, "sweep.png"), dpi=150)


# ================================================================== blind sheet + correctness (CPU)
LABELLING = """Labelling the Codex activation-steering correctness sheet (blind_sheet_blank.csv)

Save your labelled copy as blind_sheet_labels.csv in the same folder; never edit blind_sheet_blank.csv.
Do not open keys/ until every label is final.

Each row is one distinct model answer to a "why" question about a GitLab Runner merge request. You see the
question, the gold answer, the gold quotes (verbatim MR text that states the reason) and the model answer.
Which arm (unsteered or a steering ratio) produced it is hidden, citation ids were removed, and identical
answers from several arms appear once.

Fill `label` with exactly one of: correct / partial / wrong, and give a one-line `reason`.
- correct: states the reason the gold quotes support (paraphrase is fine; extra details are fine only if they
  do not contradict the MR).
- partial: gets part of the reason, or is in the right area but misses the key point.
- wrong: a different or invented reason, or contradicts the gold.
Judge against the gold quotes, not against general knowledge. Do not change any other column.
A reason must date from the change; bot notes are not in the model's documents.
"""


def answer_text(E, response):
    return E.strip_citations(response).strip()


def cmd_blind(a):
    E = exp2(a)
    qd = questions(a)
    base, test = arm_rows(a)
    arms = {"baseline": base, **{f"steered {r}": test[r] for r in RATIOS}}
    items = {}
    for arm, rows in arms.items():
        for i, r in rows.items():
            if qd[i]["type"] == "answerable" and r["answered"]:
                t = answer_text(E, r["response"])
                items.setdefault((i, t), []).append(arm)
    order = sorted(items, key=lambda it: hkey("blind", f"{it[0]}\n{it[1]}"))
    key, buf = {}, io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["blind_id", "question", "gold_answer", "gold_quotes", "model_answer", "label", "reason"])
    for n, (i, t) in enumerate(order, 1):
        bid = f"B{n:03d}"
        key[bid] = {"id": i, "arms": items[(i, t)], "answer_sha256": sha256_bytes(t.encode("utf-8"))}
        q = qd[i]
        w.writerow([bid, q["question"], q["answer"], " || ".join(q["quotes"]), t, "", ""])
    put(a, "blind_sheet_blank.csv", buf.getvalue(), bom=True)
    put(a, os.path.join("keys", "blind_key.json"), json_text(key))
    put(a, "LABELLING_CODEX.txt", LABELLING)
    print(f"{len(key)} distinct answers to label -> out/blind_sheet_blank.csv (key in out/keys/, do not open)")
    print("BLIND OK")


def correctness(a, path, qd, ans, base, test):
    E = exp2(a)
    key = rjson(outp(a, "keys", "blind_key.json"))
    labels = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            lab = (row.get("label") or "").strip().lower()
            if lab not in ("correct", "partial", "wrong"):
                raise SystemExit(f"STOP: {row['blind_id']} has label {lab!r}; only correct / partial / wrong")
            k = key[row["blind_id"]]
            t = (row.get("model_answer") or "").strip()
            if sha256_bytes(t.encode("utf-8")) != k["answer_sha256"]:
                raise SystemExit(f"STOP: {row['blind_id']}'s model_answer was changed in the labels file")
            labels[(k["id"], t)] = lab
    if len(labels) != len(key):
        raise SystemExit(f"STOP: {len(labels)} labelled rows, {len(key)} in the key")

    def lab(r, i):
        return labels[(i, answer_text(E, r["response"]))] if r["answered"] else None
    res = {"labels_file": os.path.basename(path), "rows": [], "note": "secondary; exact McNemar, unadjusted"}
    for kind, ok in (("strict (correct)", {"correct"}), ("lenient (correct + partial)", {"correct", "partial"})):
        bvals = {i: lab(base[i], i) in ok for i in ans}
        for r in RATIOS:
            svals = {i: lab(test[r][i], i) in ok for i in ans}
            b = sum(bvals[i] and not svals[i] for i in ans)
            c = sum(svals[i] and not bvals[i] for i in ans)
            res["rows"].append({"kind": kind, "ratio": r, "n": len(ans), "baseline": sum(bvals.values()),
                                "steered": sum(svals.values()), "only_baseline": b, "only_steered": c,
                                "p_unadjusted": mcnemar_exact(b, c)})
    return res


# ================================================================== report (CPU)
def cmd_report(a):
    S = rjson(outp(a, "stats.json"))
    prep = rjson(outp(a, "prepare_summary.json"))
    vi = rjson(outp(a, "vector_info.json")) if os.path.exists(outp(a, "vector_info.json")) else None
    smoke = rjson(outp(a, "smoke.json")) if os.path.exists(outp(a, "smoke.json")) else {}
    base = rjsonl(outp(a, "gen_baseline.jsonl"))
    run = base[0]["run"] if base else {}
    L = []
    w = L.append
    w("# Activation steering on the 70 GitLab Runner questions (Codex build): results\n")
    w("**What this is.** Activation steering (contrastive activation addition) on the frozen "
      "Qwen3-4B-Instruct-2507 (Hugging Face, bf16, greedy). No weights were changed. This is **not "
      "reinforcement learning and not fine-tuning**. The professors asked for reinforcement learning of "
      "weights on the human-checked set; this experiment instead uses the checked set to build a "
      "steering vector, and the report must say so.\n")
    w(f"Model revision `{run.get('revision')}`, torch {run.get('torch')}, transformers {run.get('transformers')}, "
      f"GPU {run.get('gpu')}, code sha `{run.get('code_sha')}`, repo HEAD `{(run.get('git') or {}).get('head')}`.\n")
    w("**Provenance of the 70.** The question check was mostly automated (DeepSeek and Codex); James read about "
      "11 rows himself. The Exp 2 correctness labels are provisional (James 20, Codex 67, Alyssa none, kappa "
      "0.177). The gold answers, used here as the chosen side of the grounding and twin pairs, were written "
      "by Claude.\n")
    w("## Setup checks\n")
    w(f"- Rebuilt main contexts equal `gen_F0.jsonl`: {prep['contexts_equal_gen_F0']} (70/70).")
    w(f"- Answerable questions with the answer span in context: {prep['answerable_span_in_context_any']} of 52 "
      f"(all quotes inside: {prep['answerable_span_in_context_all']}).")
    w(f"- Pairs: {json.dumps(prep['pairs'])}.")
    w(f"- Smoke test: {json.dumps(smoke.get('checks', {}))}.")
    pc = S["pipeline_check_hf_vs_ollama_F0"]
    w(f"- Pipeline check, HF unsteered vs stored Ollama F0 (answer vs refuse): {pc['agree']}/70 agree, "
      f"kappa {pc['kappa']}; table {json.dumps(pc['table'])}. Not a baseline.\n")
    if vi:
        w("## Vectors\n")
        w("| Layer | Typical residual norm | Vector norm / typical (range over 15 fold x ratio) | Min cosine between folds |")
        w("|---|---|---|---|")
        for Ls, tn in vi["typical_residual_norm"].items():
            r = [x["norm_over_typical_residual"] for x in vi["vectors"] if str(x["layer"]) == Ls]
            c = [x["min_cos_between_folds"] for x in vi["fold_stability"] if str(x["layer"]) == Ls]
            w(f"| {Ls} | {tn:.1f} | {min(r):.3f} to {max(r):.3f} | {min(c):.3f} |")
        w("")
    w("## Chosen settings (inner J, training MRs only; optimistic and not a result)\n")
    w("| Ratio | " + " | ".join(f"Fold {k}" for k in sorted(next(iter(S['selection'].values())), key=int)) + " |")
    w("|---|" + "---|" * N_FOLDS)
    for r, ks in S["selection"].items():
        w(f"| {r} | " + " | ".join(
            ("unsteered" if v["strength"] == 0 else f"L{v['layer']} x{v['strength']:g}") + f" (J {v['inner_J']:+.2f})"
            for k, v in sorted(ks.items(), key=lambda kv: int(kv[0]))) + " |")
    w("")
    w("## Held-out counts\n")
    keys = list(S["arms"][0])
    w("| " + " | ".join(keys) + " |")
    w("|" + "---|" * len(keys))
    for c in S["arms"]:
        w("| " + " | ".join(str(c[k]) for k in keys) + " |")
    w("")
    w("## Tests: exact McNemar vs the unsteered HF model, two-sided, one Holm family of 9\n")
    w("| Ratio | Outcome | n | Unsteered | Steered | Only unsteered / only steered | p | Holm p |")
    w("|---|---|---|---|---|---|---|---|")
    for f in S["tests"]:
        w(f"| {f['ratio']} | {f['outcome']} | {f['n']} | {f['baseline']} | {f['steered']} | "
          f"{f['only_baseline']} / {f['only_steered']} | {f['p']:.4f} | {f['p_holm']:.4f} |")
    w("")
    if S.get("correctness"):
        w(f"## Correctness (secondary, labels `{S['correctness']['labels_file']}`, exact McNemar, unadjusted)\n")
        w("| Kind | Ratio | n | Unsteered | Steered | Only unsteered / only steered | p |")
        w("|---|---|---|---|---|---|---|")
        for r in S["correctness"]["rows"]:
            w(f"| {r['kind']} | {r['ratio']} | {r['n']} | {r['baseline']} | {r['steered']} | "
              f"{r['only_baseline']} / {r['only_steered']} | {r['p_unadjusted']:.4f} |")
        w("")
    else:
        w("## Correctness\n\nNot computed yet: the blind sheet has no labels.\n")
    if S.get("sweep"):
        w("## Optional sweep (descriptive only; no setting was chosen from it)\n")
        w("See `sweep.csv` and `sweep.png`.\n")
    w("## Limits\n")
    w("- With 18 unanswerable questions, Holm over 9 tests needs a lopsided split (about 7 to 0 before "
      "correction) to reach significance. A non-significant result does not show steering has no effect.")
    w("- The inner J is optimistic: the inner unanswerables also built that fold's vector.")
    w("- Twin and grounding pairs use Claude's gold answers; WHAT-as-WHY rejections are scripted from MR "
      "titles; only the 5 stored Ollama answers to unanswerables are real model errors.")
    w("- The F0 contexts and pairs come from the q4_K_M Ollama run; the steered model is the bf16 HF model.")
    w("- Correctness labels (if present) come from one rater.")
    put_report = "\n".join(L) + "\n"
    with open(outp(a, "codex_report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(put_report)
    print(f"report -> {outp(a, 'codex_report.md')}")
    print("REPORT OK")


# ================================================================== CLI
COMMANDS = {"preflight": cmd_preflight, "prepare": cmd_prepare, "smoke": cmd_smoke, "vectors": cmd_vectors,
            "baseline": cmd_baseline, "select": cmd_select, "test": cmd_test, "stats": cmd_stats,
            "blind": cmd_blind, "report": cmd_report, "sweep": cmd_sweep, "make-hashes": cmd_make_hashes,
            "rebuild-vectors": lambda a: build_vectors(a), "choose": lambda a: choose(
                a, Appender(outp(a, "gen_inner.jsonl")).rows,
                need_baseline(a, [i for v in rjson(outp(a, "inner_sets.json")).values() for i in
                                  v["unanswerable"] + v["answerable"]]),
                rjson(outp(a, "inner_sets.json")))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=list(COMMANDS))
    ap.add_argument("--repo", default=None, help="James's gitlab_runner_copy (default: the parent folder)")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--revision", default=None, help="model revision (default: out/model_revision.json)")
    ap.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float32", "float16"])
    ap.add_argument("--device", default=None, help="cuda / cpu (default: cuda if available)")
    ap.add_argument("--layers", type=int, nargs="+", default=LAYERS)
    ap.add_argument("--prefer-layer", type=int, default=PREFER_LAYER)
    ap.add_argument("--ratios", nargs="+", default=list(RATIOS), choices=list(RATIOS))
    ap.add_argument("--max-new", type=int, default=MAX_NEW)
    ap.add_argument("--labels", default=None, help="labelled blind sheet (default: out/blind_sheet_labels.csv)")
    ap.add_argument("--overwrite", action="store_true", help="replace deterministic outputs that differ")
    ap.add_argument("--cpu-ok", action="store_true", help="preflight: do not require a CUDA GPU")
    ap.add_argument("--no-download", action="store_true", help="preflight: skip the model download")
    a = ap.parse_args(argv)
    a.out = os.path.abspath(a.out)
    a.repo = find_repo(a.repo)
    os.makedirs(os.path.join(a.out, "logs"), exist_ok=True)
    log = os.path.join(a.out, "logs", f"{a.command}.log")
    sys.stdout = Tee(sys.__stdout__, log)
    sys.stderr = Tee(sys.__stderr__, log)
    try:
        sys.__stdout__.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(f"\n===== {a.command}  {time.strftime('%Y-%m-%d %H:%M:%S')}  code {CODE_SHA}  args {vars(a)}")
    if os.name == "nt" and a.command in ("smoke", "vectors", "baseline", "select", "test", "sweep"):
        try:                                             # ask Windows not to sleep while this process runs
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        except Exception:
            pass
    try:
        COMMANDS[a.command](a)
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        print(f"\n{a.command.upper()} CRASHED; the log is {log}. Re-running the same command resumes.")
        sys.exit(1)


if __name__ == "__main__":
    main()
