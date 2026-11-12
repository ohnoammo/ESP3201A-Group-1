"""Experiment 2 on SymPy (exploratory transfer check): the frozen Django Exp 2 setting, unchanged
except for the project name, run on hand-checked SymPy "why" questions. Counts only, no tests.

Run inside the SymPy copy of Exp 1 (ESP3201A_SWE_exp1_sympy), AFTER the Exp 1 SymPy runs: their
pool, chunk caches and embeddings are reused, so the fixed and structural chunks are not re-embedded.

  python exp2_sympy.py shortlist     1. candidate PRs + readable digests       (no GPU, ~1 min)
  python exp2_sympy.py build         2. check the hand-written questions        (no GPU, ~1 min)
  python exp2_sympy.py retrieve      3. dense top-100 per question, 2 chunkings (GPU, minutes)
  python exp2_sympy.py generate      4. Ollama qwen3 4B, prompt v3, arms F0 and S0-G
  python exp2_sympy.py score         5. results table + blind correctness sheet
  python exp2_sympy.py gate          6. optional MiniCheck gate (downloads ~3 GB once)
  python exp2_sympy.py report        7. after the sheet is labelled: final table

Frozen setting, copied from ESP3201A_Exp2 (HANDOVER "Current setup", prompts/FROZEN.json,
run_generation.py, score.py, faithfulness.py, tuning_rule_gate.md, shortlist.py):
  retrieval  dense Qwen3-Embedding-0.6B (Exp 1 Qwen3Embedder + its cache), Exp 2 "why" instruction,
             exact cosine over all pool chunks, top 100 (Exp 2 used Qdrant cosine: same ranking up
             to float rounding)
  packing    Exp 1 relations.expand_and_pack, alpha 0 (no links), budget 2,560 Exp 1 tokens
  arms       F0   = fixed 512/77, excerpts in score order
             S0-G = structural cap 256, excerpts grouped by PR (PRs by best score, document order)
  prompt     v3 strict grounded (prompts/c_strict_grounded_v3_DRAFT.txt, sha1 759a5e1219)
  model      qwen3:4b-instruct-2507-q4_K_M via Ollama: think off, temperature 0, seed 42,
             num_ctx 8192, num_predict 512 (Exp 2 used Ollama 0.40.4; the version is recorded)
  scoring    score.py: strict abstention, hedged = answered, overlap-/contain-cited, empty answers
  gate       MiniCheck-Flan-T5-Large on the cited chunks; min sentence score < 0.5, or no valid
             citation -> abstain (faithfulness.py windows and sentence splitting)
The only SymPy changes: "Django" -> "SymPy" in the prompt's first line and in the retrieval
instruction, and the docs folder is "doc/" (shortlist rule "not docs-only").
"""
import argparse
import csv
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time

REPO = "gitlab-org/gitlab-runner"
POOL = "A270"
OUT = "exp2_gitlab"
SRC = os.path.join(OUT, "questions_src.json")
QUESTIONS = os.path.join(OUT, "questions.jsonl")
EMB_CACHE = os.path.join("emb_cache", "qwen3_gitlab.npz")
CHUNKINGS = {"fixed_s512_o77": {"name": "fixed_s512_o77", "method": "fixed", "size": 512, "overlap": 77}}
ARMS = {"F0": ("fixed_s512_o77", "score"), "C1": ("fixed_s512_o77", "score")}
ARM_ALPHA = {"F0": 0.0, "C1": 1.0}
BUDGET, ALPHA, K = 2560, 0.0, 100
MODEL = "qwen3:4b-instruct-2507-q4_K_M"
OLLAMA = "http://localhost:11434"
OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512}
EXP2_OLLAMA = "0.40.4"
NOT_FOUND_SENTENCE = "Not found in the provided PRs"

# ---- frozen Exp 2 texts (copied verbatim; the hash check proves the copy is exact) ----
PROMPT_V3_DJANGO = """### SYSTEM
You are an assistant that answers questions about pull requests in the Django project.
### USER
Answer the question using ONLY the pull request excerpts below. Do not use outside knowledge and do not guess.

Rules:
- The question asks WHY something was done. A reason must be stated in the excerpts in words, for example by an author or reviewer explaining a decision.
- A description of WHAT changed is not a reason. Code changes, titles, commit summaries, tests or release notes that only show what was done do not answer a WHY question. Do not work out a reason yourself from the code.
- If the excerpts state the reason, answer in at most three sentences. Then cite, in square brackets, only the id of the excerpt whose text states the reason, for example [PR1234-c0]. This is usually a single excerpt; cite a second one only if the reason is split across two. Never cite an excerpt that does not state the reason.
- If the excerpts do not state the reason, reply with exactly this sentence and nothing else: Not found in the provided PRs

{context}

Question: {question}
"""
PROMPT_V3_SHA1 = "759a5e1219"
INSTRUCTION_DJANGO = ("Given a question about why a change was made in a Django pull request, retrieve "
                      "the pull request excerpts (description, commit messages, review comments or "
                      "discussion) that state the reason")


def sympy_prompt():
    raw = PROMPT_V3_DJANGO
    assert hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10] == PROMPT_V3_SHA1, "v3 copy differs"
    raw = raw.replace("pull requests in the Django project", "pull requests in the GitLab Runner project")
    system, user = raw.split("### USER\n")
    return {"system": system.replace("### SYSTEM\n", "").strip(), "user": user.strip(),
            "sha1": hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10],
            "based_on": f"Exp 2 prompt v3 (c3, sha1 {PROMPT_V3_SHA1}), 'Django' -> 'GitLab Runner'"}


INSTRUCTION = INSTRUCTION_DJANGO.replace("a Django pull request", "a GitLab Runner pull request")


# ---------------------------------------------------------------- shared helpers
def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


_docs = {}


def pool_docs():
    """{pr number: document} of the SymPy pool, exactly as run_retrieval_swe.load_docs builds them."""
    if not _docs:
        from github_prs import load_pr, load_pool
        from pr_document import build_document
        for n in load_pool(REPO, POOL)["numbers"]:
            pr = load_pr(REPO, n)
            if pr is None or pr.get("not_found"):
                continue
            d = build_document(pr)
            if d["text"].strip():
                _docs[int(n)] = d
    return _docs


def chunk_set(chunking):
    """Chunks of one chunking for the whole pool: loads the Exp 1 chunk cache (same name/hash)."""
    from exp1_common import make_chunks
    docs = pool_docs()
    doc_list = [docs[k] for k in sorted(docs)]
    chunks, info = make_chunks(doc_list, CHUNKINGS[chunking], "swe")
    return chunks, info


def short_id(chunk_id):
    """'8930_fixed_s512_o77_3' -> 'PR8930-c3' (run_generation.short_id)."""
    pr, *_, i = chunk_id.split("_")
    return f"PR{pr}-c{i}"


def format_context(cks):
    return "\n\n".join(f"[{short_id(c['chunk_id'])}]\n{c['text']}" for c in cks)


def covered(spans, ctx_chunks, pr, text):
    """eval_links.covered: answer spans fully inside the merged context chunks of the gold PR."""
    iv = sorted((c["start"], c["end"]) for c in ctx_chunks if c["pr_number"] == pr)
    merged = []
    for s, e in iv:
        if merged and (s <= merged[-1][1] or not text[merged[-1][1]:s].strip()):
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [any(ms <= a and b <= me for ms, me in merged) for a, b in spans]


def pack(cand_ids, chunk_by_id, order, exclude_prs=(), alpha=ALPHA, links=None):
    """pack_exp1.build_context_exp1 at alpha 0 + run_generation.pack_context ordering."""
    from relations import expand_and_pack, token_counter
    ntok = token_counter()
    excl = {int(p) for p in exclude_prs}
    ranked = [chunk_by_id[cid] | {"chunk_id": cid} for cid in cand_ids
              if int(cid.split("_")[0]) not in excl]
    packed = expand_and_pack(ranked, alpha, links or {}, chunk_by_id, BUDGET, ntok)
    cks = [{"chunk_id": c["chunk_id"], "pr_number": int(c["chunk_id"].split("_")[0]),
            "start": c["start"], "end": c["end"], "text": c["text"], "score": c["score"],
            "tokens": ntok(c["chunk_id"], c)} for c in packed]
    if order == "grouped":
        best = {}
        for c in cks:
            best[c["pr_number"]] = max(best.get(c["pr_number"], -1), c["score"])
        cks = sorted(cks, key=lambda c: (-best[c["pr_number"]], c["pr_number"], c["start"]))
    elif order != "score":
        raise ValueError(order)
    return cks


# ---- score.py (copied) ----
NOT_FOUND = "not found in the provided prs"
CITE = re.compile(r"PR(\d+)-c(\d+)")


def abstained_strict(resp):
    t = re.sub(r"\[[\s,;]*\]", "", CITE.sub("", resp)).strip()
    return t.lower().startswith(NOT_FOUND) and not re.search(r"\w", t[len(NOT_FOUND):])


def hedged(resp):
    t = re.sub(r"\[[\s,;]*\]", "", CITE.sub("", resp)).strip()
    return NOT_FOUND in t.lower() and bool(re.search(r"\w", t.lower().replace(NOT_FOUND, "")))


def auto(rec, q, chunking):
    resp = rec["response"].strip()
    cites = [f"PR{a}-c{b}" for a, b in CITE.findall(resp)]
    shown = set(rec["context_short_ids"])
    gold = {short_id(c) for c in q.get(f"overlap_chunks_{chunking}") or []}
    contain = {short_id(c) for c in q.get(f"gold_chunks_{chunking}") or []}
    valid = [c for c in cites if c in shown]
    empty = not re.search(r"\w", CITE.sub("", resp).replace("[", "").replace("]", ""))
    ok = (not empty) and bool(cites) and len(valid) == len(cites)
    return {"overlap_cited": ok and any(c in gold for c in cites),
            "contain_cited": (ok and any(c in contain for c in cites)) if contain else None,
            "empty_answer": empty, "abstained": abstained_strict(resp), "hedged": hedged(resp),
            "n_cites": len(cites), "n_valid_cites": len(valid),
            "n_gold_cites": sum(c in gold for c in cites)}


# ---------------------------------------------------------------- 1. shortlist
MIN_DESC_WORDS, MIN_THREADS, MIN_DISCUSSION, MAX_DOC_TOKENS, N_SHORTLIST = 40, 2, 4, 4000, 60
_TEMPLATE = re.compile(r"^\s*(#{1,6}\s.*|[-*]\s*\[[ xX]\].*|ticket-\d+.*|Trac ticket.*|"
                       r"Branch description.*|Checklist.*)$", re.M)
_URL = re.compile(r"https?://\S+")
MAX_PART = 1800


def clean_desc(body):                                   # shortlist.clean_desc (copied)
    body = re.sub(r"<!--.*?-->", " ", body or "", flags=re.S)
    return _URL.sub(" ", _TEMPLATE.sub(" ", body))


def digest(n, d):                                       # digest.digest (copied)
    out = [f"=================== PR {n}   https://gitlab.com/{REPO}/-/merge_requests/{n}"]
    files = sorted({p["file_path"] for p in d["parts"] if p["type"] in ("hunk", "file_nodiff")})
    for p in d["parts"]:
        if p["type"] in ("hunk", "file_nodiff"):
            continue
        t = d["text"][p["start"]:p["end"]]
        out.append(f"--- [{p['type']}] {p['start']}-{p['end']}\n" + t[:MAX_PART]
                   + (" [...]" if len(t) > MAX_PART else ""))
    out.append("--- files: " + ", ".join(files))
    return "\n".join(out)


def cmd_shortlist(a):
    from github_prs import load_pr
    from pr_document import is_bot
    from chunking import count_tokens
    docs = pool_docs()
    feats = []
    for n, d in sorted(docs.items()):
        pr = load_pr(REPO, n)
        roots = [c for c in pr.get("review_comments", [])
                 if not c.get("in_reply_to_id") and not is_bot(c.get("user"))]
        conv = [c for c in pr.get("issue_comments", []) if not is_bot(c.get("user"))]
        files = pr.get("files", [])
        feats.append({"n": n, "title": pr.get("title"), "merged": bool(pr.get("merged")),
                      "docs_only": bool(files) and all(f["filename"].startswith("docs/") for f in files),
                      "desc_words": len(clean_desc(pr.get("body")).split()),
                      "threads": len(roots), "conv": len(conv),
                      "doc_tokens": count_tokens(d["text"])})
    steps = [("in pool", lambda f: True), ("merged", lambda f: f["merged"]),
             ("not docs-only", lambda f: not f["docs_only"]),
             (f"description >= {MIN_DESC_WORDS} words", lambda f: f["desc_words"] >= MIN_DESC_WORDS),
             (f">= {MIN_THREADS} review threads or >= {MIN_DISCUSSION} threads + comments",
              lambda f: f["threads"] >= MIN_THREADS or f["threads"] + f["conv"] >= MIN_DISCUSSION),
             (f"document <= {MAX_DOC_TOKENS} tokens", lambda f: f["doc_tokens"] <= MAX_DOC_TOKENS)]
    funnel, keep = [], feats
    for name, ok in steps:
        keep = [f for f in keep if ok(f)]
        funnel.append({"step": name, "n": len(keep)})
        print(f"  {name:<55}{len(keep):>6}")
    keep.sort(key=lambda f: hashlib.sha256(f"42:{f['n']}".encode()).hexdigest())
    short = keep[:N_SHORTLIST]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "shortlist.json"), "w", encoding="utf-8") as f:
        json.dump({"rule": "Exp 2 shortlist.py thresholds; fixed SHA-256 order (seed 42); docs = doc/",
                   "funnel": funnel, "shortlist": short}, f, indent=1)
    with open(os.path.join(OUT, "digests.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(digest(s["n"], docs[s["n"]]) for s in short))
    print(f"{len(short)} shortlisted PRs -> {OUT}/shortlist.json, {OUT}/digests.txt")


# ---------------------------------------------------------------- 2. build
PART_TYPES = {"description": "title_description", "review_thread": "review_thread",
              "comment": "conversation", "commit": "commits"}
COPY_N = 6


def words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def longest_shared_run(question, text, max_n=20):     # build_questions.longest_shared_run
    q, t = words(question), words(text)
    best = 0
    for n in range(1, max_n + 1):
        grams = {tuple(t[i:i + n]) for i in range(len(t) - n + 1)}
        if any(tuple(q[i:i + n]) in grams for i in range(len(q) - n + 1)):
            best = n
        else:
            break
    return best


def find_span(d, quote, part):                         # build_questions.find_span
    ptype = PART_TYPES[part]
    start = d["text"].find(quote)
    while start != -1:
        end = start + len(quote)
        if any(p["type"] == ptype and p["start"] <= start and end <= p["end"] for p in d["parts"]):
            return start, end
        start = d["text"].find(quote, start + 1)
    return None


def cmd_build(a):
    with open(SRC, encoding="utf-8") as f:
        src = json.load(f)
    docs = pool_docs()
    by_pr = {}
    for ch in CHUNKINGS:
        cks, _ = chunk_set(ch)
        for c in cks:
            by_pr.setdefault((ch, int(c["pr_number"])), []).append(c)
    rows, dropped = [], []
    prefix = {"answerable": "q", "no_reason": "nr", "removed": "rm"}
    for e in src["questions"]:
        n, typ = int(e["pr"]), e["type"]
        if n not in docs:
            dropped.append({"pr": n, "why": "PR not in the pool"})
            continue
        d = docs[n]
        quotes, parts = e.get("quotes", []), e.get("parts", [])
        spans = [find_span(d, qt, pt) for qt, pt in zip(quotes, parts)]
        if typ != "no_reason" and (not quotes or None in spans):
            dropped.append({"pr": n, "why": "quote not found verbatim in a part of the stated type",
                            "quotes": [qt for qt, sp in zip(quotes, spans) if sp is None]})
            continue
        qid = f"{prefix[typ]}{n}"
        while qid in {r["id"] for r in rows}:           # a second question on the same PR
            qid += "b"
        row = {"id": qid, "type": typ, "pr_number": n, "question": e["q"],
               "answer": NOT_FOUND_SENTENCE if typ != "answerable" else e["a"],
               "gold_answer_if_present": e.get("a") if typ == "removed" else None,
               "quotes": quotes, "spans": [list(s) for s in spans], "source_parts": parts,
               "note": e.get("note", ""), "split": "gitlab-runner"}
        for ch in CHUNKINGS:
            cks = by_pr.get((ch, n), [])
            row[f"gold_chunks_{ch}"] = [c["chunk_id"] for c in cks
                                        if any(c["start"] <= s and t <= c["end"] for s, t in spans)]
            row[f"overlap_chunks_{ch}"] = [c["chunk_id"] for c in cks
                                           if any(c["start"] < t and s < c["end"] for s, t in spans)]
        row["copy_max_run"] = longest_shared_run(e["q"], d["text"])
        row["copy_flag"] = row["copy_max_run"] >= COPY_N
        elsewhere = sorted(m for m, dm in docs.items() if m != n and any(qt in dm["text"] for qt in quotes))
        row["quote_elsewhere"] = elsewhere
        row["exclude_prs"] = [n] + elsewhere if typ == "removed" else []
        rows.append(row)
    write_jsonl(QUESTIONS, rows)
    with open(os.path.join(OUT, "question_check_sheet.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "type", "pr_url", "question", "answer", "quotes", "copy_flag", "check", "note"])
        for r in rows:
            w.writerow([r["id"], r["type"], f"https://gitlab.com/{REPO}/-/merge_requests/{r['pr_number']}",
                        r["question"], r["gold_answer_if_present"] or r["answer"],
                        " || ".join(r["quotes"]), r["copy_flag"], "", r["note"]])
    counts = {t: sum(r["type"] == t for r in rows) for t in prefix}
    print(f"{len(rows)} questions {counts} -> {QUESTIONS}; dropped {len(dropped)}")
    for x in dropped:
        print("  DROPPED", x)
    for r in rows:
        if r["copy_flag"]:
            print(f"  copy flag: {r['id']} shares {r['copy_max_run']} words in a row with its PR")
        if r["type"] == "answerable" and not r["gold_chunks_fixed_s512_o77"]:
            print(f"  note: {r['id']} has no fixed chunk that fully contains its quote")
    print(f"Human check: {OUT}/question_check_sheet.csv (fill 'check' with ok / fix / drop)")


# ---------------------------------------------------------------- 3. retrieve
def cmd_retrieve(a):
    import numpy as np
    from dense_retrieval import Qwen3Embedder, DEFAULT_MODEL
    qs = read_jsonl(QUESTIONS)
    emb = Qwen3Embedder(DEFAULT_MODEL, task=None, device=a.device, batch_size=a.batch_size,
                        cache_path=EMB_CACHE)
    emb.query_prompt = f"Instruct: {INSTRUCTION}\nQuery:"
    emb._query_cache = {}
    emb.embed_queries([q["question"] for q in qs])
    for ch in CHUNKINGS:
        cks, info = chunk_set(ch)
        E = emb.embed_documents([c["text"] for c in cks])
        prs = np.array([int(c["pr_number"]) for c in cks])
        out, hits = [], []
        for q in qs:
            s = E @ emb.embed_query(q["question"])
            if q["exclude_prs"]:
                s = np.where(np.isin(prs, q["exclude_prs"]), -np.inf, s)
            top = np.argsort(-s, kind="stable")[:K]
            ids = [cks[i]["chunk_id"] for i in top]
            out.append({"id": q["id"], "chunk_ids": ids, "scores": [float(s[i]) for i in top]})
            if q["type"] == "answerable":
                first = [int(cid.split("_")[0]) for cid in ids]
                prs5 = list(dict.fromkeys(first))[:5]
                hits.append(q["pr_number"] in prs5)
        meta = {"chunking": ch, "chunk_set": info["chunk_set"], "model": DEFAULT_MODEL,
                "query_prompt": emb.query_prompt, "k": K, "search": "exact cosine (numpy)",
                "n_truncated_queries": emb.n_truncated_queries}
        path = os.path.join(OUT, f"candidates_{ch}.jsonl")
        write_jsonl(path, [{"_meta": meta}] + out)
        print(f"[{ch}] {len(out)} questions -> {path}; gold PR in the top 5 PRs for "
              f"{sum(hits)}/{len(hits)} answerable questions")


# ---------------------------------------------------------------- 4. generate
def _candidates(ch):
    rows = read_jsonl(os.path.join(OUT, f"candidates_{ch}.jsonl"))
    return rows[0]["_meta"], {r["id"]: r for r in rows[1:]}


def machine():
    try:
        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version",
                                       "--format=csv,noheader"], text=True).strip()
    except Exception:
        gpu = "unknown"
    return {"host": platform.node(), "os": platform.platform(), "gpu": gpu}


def cmd_generate(a):
    import requests
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    prompt = sympy_prompt()
    qs = read_jsonl(QUESTIONS)
    docs = pool_docs()
    version = requests.get(f"{OLLAMA}/api/version", timeout=30).json().get("version")
    tags = requests.get(f"{OLLAMA}/api/tags", timeout=30).json()["models"]
    digest_ = next((m["digest"][:12] for m in tags if m["name"] == a.model), None)
    if digest_ is None:
        raise SystemExit(f"model {a.model} is not pulled: run  ollama pull {a.model}")
    if version != EXP2_OLLAMA:
        print(f"NOTE: Ollama {version} (Exp 2 used {EXP2_OLLAMA}); recorded in every row")
    mach = machine()
    for arm in a.arms:
        ch, order = ARMS[arm]
        meta, cands = _candidates(ch)
        chunks, _ = chunk_set(ch)
        by_id = {c["chunk_id"]: c for c in chunks}
        alpha = ARM_ALPHA[arm]
        from relations import build_links
        links = build_links(chunks, {str(k): v for k, v in docs.items()}, kinds=("code",)) if alpha else {}
        path = os.path.join(OUT, f"gen_{arm}.jsonl")
        done = {r["id"] for r in read_jsonl(path)} if os.path.exists(path) else set()
        print(f"{arm}: {len(qs) - len(done)} questions to generate -> {path}")
        with open(path, "a", encoding="utf-8") as out:
            for q in qs:
                if q["id"] in done:
                    continue
                cks = pack(cands[q["id"]]["chunk_ids"], by_id, order, q["exclude_prs"], alpha, links)
                user = prompt["user"].format(question=q["question"], context=format_context(cks))
                body = {"model": a.model, "think": False, "stream": False, "options": OPTIONS,
                        "messages": [{"role": "system", "content": prompt["system"]},
                                     {"role": "user", "content": user}]}
                t0 = time.time()
                r = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=900)
                r.raise_for_status()
                d = r.json()
                n_in = d.get("prompt_eval_count")
                cov = (covered(q["spans"], cks, q["pr_number"], docs[q["pr_number"]]["text"])
                       if q["type"] == "answerable" else None)
                rec = {"id": q["id"], "type": q["type"], "pr_number": q["pr_number"], "arm": arm,
                       "chunking": ch, "order": order, "alpha": alpha, "budget": BUDGET,
                       "chunk_set": meta["chunk_set"], "query_prompt": meta["query_prompt"],
                       "prompt_sha1": prompt["sha1"], "prompt_based_on": prompt["based_on"],
                       "model": a.model, "model_digest": digest_, "ollama_version": version,
                       "options": OPTIONS, "think": False, "machine": mach,
                       "context_chunk_ids": [c["chunk_id"] for c in cks],
                       "context_short_ids": [short_id(c["chunk_id"]) for c in cks],
                       "context_tokens": sum(c["tokens"] for c in cks),
                       "n_prs_in_context": len({c["pr_number"] for c in cks}),
                       "span_in_context": {"any": any(cov), "all": all(cov)} if cov else None,
                       "exclude_prs": q["exclude_prs"],
                       "prompt_eval_count": n_in, "eval_count": d.get("eval_count"),
                       "possibly_truncated": bool(n_in and n_in >= OPTIONS["num_ctx"] - 16),
                       "done_reason": d.get("done_reason"), "seconds": round(time.time() - t0, 2),
                       "response": d["message"]["content"]}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                print(f"  {arm:<5}{q['id']:<10} in={n_in} out={d.get('eval_count')} "
                      f"{rec['seconds']:.0f}s {rec['response'][:70]!r}")


# ---------------------------------------------------------------- 5. score
CITES = re.compile(r"\[\s*PR\d+-c\d+(?:\s*[,;]\s*PR\d+-c\d+)*\s*\]")


def strip_citations(t):
    return re.sub(r"[ \t]+([.,;:!?])", r"\1", CITE.sub("", CITES.sub("", t))).replace("[]", "").strip()


def summarise(gens, qs):
    rows = []
    for arm, recs in gens.items():
        ch = ARMS[arm][0] if arm in ARMS else recs[0]["chunking"]
        A = [(r, auto(r, qs[r["id"]], ch)) for r in recs]
        ans = [(r, x) for r, x in A if r["type"] == "answerable"]
        un = [(r, x) for r, x in A if r["type"] in ("no_reason", "removed")]
        answered = [(r, x) for r, x in ans if not x["abstained"] and not x["empty_answer"]]
        nc = sum(x["n_cites"] for _, x in ans)
        rows.append({
            "arm": arm, "n_answerable": len(ans),
            "span_in_context": sum(bool(r["span_in_context"] and r["span_in_context"]["any"]) for r, _ in ans),
            "answered": len(answered),
            "abstained_with_span": sum(x["abstained"] and bool(r["span_in_context"] and
                                                              r["span_in_context"]["any"]) for r, x in ans),
            "overlap_cited": sum(x["overlap_cited"] for _, x in ans),
            "contain_cited": sum(bool(x["contain_cited"]) for _, x in ans),
            "cite_precision": round(sum(x["n_gold_cites"] for _, x in ans) / nc, 2) if nc else None,
            "empty_answers": sum(x["empty_answer"] for _, x in A),
            "hedged": sum(x["hedged"] for _, x in A),
            "cross_pr_borrowing": sum(1 for r, x in answered
                                      if (p := {int(m) for m, _ in CITE.findall(r["response"])})
                                      and r["pr_number"] not in p),
            "n_unanswerable": len(un),
            "unanswerable_answered": sum(not x["abstained"] and not x["empty_answer"] for _, x in un),
            "no_reason_answered": sum(not x["abstained"] and not x["empty_answer"]
                                      for r, x in un if r["type"] == "no_reason"),
            "removed_answered": sum(not x["abstained"] and not x["empty_answer"]
                                    for r, x in un if r["type"] == "removed")})
    return rows


def _gens(arms):
    out = {}
    for arm in arms:
        p = os.path.join(OUT, f"gen_{arm}.jsonl")
        if os.path.exists(p):
            out[arm] = read_jsonl(p)
    return out


def print_table(rows, keys=None):
    keys = keys or list(rows[0])
    print(" | ".join(keys))
    for r in rows:
        print(" | ".join(str(r.get(k, "")) for k in keys))


def cmd_score(a):
    qs = {q["id"]: q for q in read_jsonl(QUESTIONS)}
    gens = _gens(a.arms)
    rows = summarise(gens, qs)
    print_table(rows)
    with open(os.path.join(OUT, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    # blind correctness sheet: answered answerable rows, shuffled, arm hidden, citations removed
    items = []
    for arm, recs in gens.items():
        for r in recs:
            x = auto(r, qs[r["id"]], ARMS[arm][0])
            if r["type"] == "answerable" and not x["abstained"] and not x["empty_answer"]:
                items.append((hashlib.sha256(f"42:{arm}:{r['id']}".encode()).hexdigest(), arm, r))
    items.sort(key=lambda t: t[0])
    key, sheet = {}, []
    for i, (_, arm, r) in enumerate(items, 1):
        bid = f"S{i:03d}"
        q = qs[r["id"]]
        key[bid] = {"arm": arm, "id": r["id"]}
        sheet.append([bid, q["question"], q["answer"], " || ".join(q["quotes"]),
                      strip_citations(r["response"]), "", ""])
    os.makedirs(os.path.join(OUT, "keys"), exist_ok=True)
    with open(os.path.join(OUT, "keys", "sheet_key.json"), "w", encoding="utf-8") as f:
        json.dump(key, f, indent=1)
    sheet_path = os.path.join(OUT, "correctness_sheet.csv")
    if os.path.exists(sheet_path) and not a.overwrite_sheet:
        print(f"{sheet_path} already exists (labels?): not overwritten; new sheet -> _new.csv")
        sheet_path = sheet_path.replace(".csv", "_new.csv")
    with open(sheet_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["blind_id", "question", "gold_answer", "gold_quotes", "model_answer", "label", "reason"])
        w.writerows(sheet)
    with open(os.path.join(OUT, "LABELLING.txt"), "w", encoding="utf-8") as f:
        f.write(LABELLING)
    print(f"\n{len(sheet)} answers to label -> {sheet_path}; rules in {OUT}/LABELLING.txt. "
          f"Do not open {OUT}/keys/ before labelling.")


LABELLING = """Labelling the SymPy correctness sheet (same rules as Exp 2's judging/codex_instructions.md)

Each row is one model answer to a "why" question about a GitLab Runner pull request. You see the question,
the gold answer, the gold quotes (verbatim PR text that states the reason) and the model answer.
The arm (F0 / S0-G) is hidden and citation ids were removed. Do not open exp2_sympy/keys/.

Fill `label` with exactly one of: correct / partial / wrong, and give a one-line `reason`.
- correct: states the reason the gold quotes support (paraphrase is fine; extra details are fine
  only if they do not contradict the PR).
- partial: gets part of the reason, or is in the right area but misses the key point.
- wrong: a different or invented reason, or contradicts the gold.
Judge against the gold quotes, not against general knowledge. Do not change any other column.
"""


# ---------------------------------------------------------------- 6. gate (faithfulness.py, copied)
NTAG = re.compile(r"(?<![\w`\]])\[\d+(?:\s*,\s*\d+)*\](?!`)")
CITE_B = re.compile(r"\[?(PR\d+-c\d+)\]?")
MIN_WORDS, WIN, SUB_OVERLAP = 3, 400, 100


def sentences(t):
    t = NTAG.sub("", CITE_B.sub("", CITES.sub("", t)))
    t = re.sub(r"[ \t]+([.,;:!?])", r"\1", re.sub(r"[ \t]+", " ", t)).strip()
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t)
            if len(re.findall(r"\w+", s)) >= MIN_WORDS] or [t]


def windows(texts, n=WIN, overlap=SUB_OVERLAP):
    out, cur, cur_n = [], [], 0
    for t in texts:
        k = len(t.split())
        if k > n:
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
    def __init__(self, device):
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        self.torch = torch
        self.dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        name, rev = "lytang/MiniCheck-Flan-T5-Large", "96eafd01cee2d16cf81aaa2fb226b14f422a37b3"
        self.tok = AutoTokenizer.from_pretrained(name, revision=rev)
        self.m = AutoModelForSeq2SeqLM.from_pretrained(name, revision=rev).to(self.dev).eval()
        self.ids = [self.tok("0", add_special_tokens=False).input_ids[0],
                    self.tok("1", add_special_tokens=False).input_ids[0]]

    def score(self, chunks, claim):
        best = 0.0
        with self.torch.no_grad():
            for win in windows(chunks):
                enc = self.tok(f"premise: {win} hypothesis: {claim}", return_tensors="pt",
                               truncation=True, max_length=1024).to(self.dev)
                dec = self.torch.full((1, 1), self.m.config.decoder_start_token_id, device=self.dev)
                logits = self.m(**enc, decoder_input_ids=dec).logits[0, -1, self.ids]
                best = max(best, self.torch.softmax(logits, -1)[1].item())
        return best


def cmd_gate(a):
    qs = {q["id"]: q for q in read_jsonl(QUESTIONS)}
    gens = _gens(a.arms)
    mc = MiniCheck(a.device)
    print(f"MiniCheck on {mc.dev}")
    for arm, recs in gens.items():
        ch, order = ARMS[arm]
        _, cands = _candidates(ch)
        chunks, _ = chunk_set(ch)
        by_id = {c["chunk_id"]: c for c in chunks}
        out = []
        for r in recs:
            x = auto(r, qs[r["id"]], ch)
            if x["abstained"] or x["empty_answer"]:
                continue
            q = qs[r["id"]]
            cks = pack(cands[r["id"]]["chunk_ids"], by_id, order, q["exclude_prs"])
            assert [c["chunk_id"] for c in cks] == r["context_chunk_ids"], r["id"]
            cited = set(CITE_B.findall(r["response"]))
            prem = [c["text"] for c in cks if short_id(c["chunk_id"]) in cited]
            sc = [mc.score(prem, s) for s in sentences(r["response"])] if prem else []
            mn = min(sc) if sc else None
            out.append({"id": r["id"], "arm": arm, "type": r["type"], "minicheck_cited_min": mn,
                        "gated": mn is None or mn < 0.5})
            print(f"  {arm:<5}{r['id']:<10} min={mn if mn is None else round(mn, 3)} "
                  f"-> {'abstain' if out[-1]['gated'] else 'keep'}")
        write_jsonl(os.path.join(OUT, f"gate_{arm}.jsonl"), out)


# ---------------------------------------------------------------- 7. report
def cmd_report(a):
    qs = {q["id"]: q for q in read_jsonl(QUESTIONS)}
    with open(os.path.join(OUT, "keys", "sheet_key.json"), encoding="utf-8") as f:
        key = json.load(f)
    labels = {}
    with open(os.path.join(OUT, "correctness_sheet.csv"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            lab = (row["label"] or "").strip().lower()
            if lab:
                k = key[row["blind_id"]]
                labels[(k["arm"], k["id"])] = lab
    gens = _gens(a.arms)
    rows = []
    for arm, recs in gens.items():
        gate_p = os.path.join(OUT, f"gate_{arm}.jsonl")
        gated = {g["id"]: g["gated"] for g in read_jsonl(gate_p)} if os.path.exists(gate_p) else None
        ch = ARMS[arm][0]
        ans = [r for r in recs if r["type"] == "answerable"]
        un = [r for r in recs if r["type"] != "answerable"]

        def answered(r):
            x = auto(r, qs[r["id"]], ch)
            return not x["abstained"] and not x["empty_answer"]
        lab = [labels.get((arm, r["id"])) for r in ans if answered(r)]
        row = {"arm": arm, "answerable": len(ans), "answered": len(lab),
               "labelled": sum(x is not None for x in lab),
               "correct": lab.count("correct"), "partial": lab.count("partial"), "wrong": lab.count("wrong"),
               "unanswerable": len(un), "unanswerable_answered": sum(answered(r) for r in un)}
        if gated is not None:
            keep = [r for r in ans if answered(r) and not gated.get(r["id"], True)]
            row["gated_answered"] = len(keep)
            row["gated_correct"] = sum(labels.get((arm, r["id"])) == "correct" for r in keep)
            row["gated_unanswerable_answered"] = sum(answered(r) and not gated.get(r["id"], True) for r in un)
        rows.append(row)
    print_table(rows)
    with open(os.path.join(OUT, "report.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["shortlist", "build", "retrieve", "generate", "score", "gate", "report"])
    ap.add_argument("--arms", nargs="+", default=list(ARMS), choices=list(ARMS))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--device", default=None, help="cuda / cpu (default: auto)")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--overwrite-sheet", action="store_true")
    args = ap.parse_args()
    {"shortlist": cmd_shortlist, "build": cmd_build, "retrieve": cmd_retrieve,
     "generate": cmd_generate, "score": cmd_score, "gate": cmd_gate, "report": cmd_report}[args.command](args)
