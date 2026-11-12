"""RAG engine for the demo UI: Exp 1 retrieval + relation factor + Exp 2 prompts via Ollama.

Three repositories (REPOS below): Django, plus SymPy and GitLab Runner from the transfer checks.
SymPy and GitLab Runner use the settings chosen on Django, unchanged.

Everything runs locally:
  - retrieval: Exp 1 code (BM25 always; dense/hybrid if the Qwen3 embedding cache covers
    the chunk set), Qdrant in local mode (folder qdrant_app/, separate from experiments)
  - packing: relations.expand_and_pack, 2,560-token budget (Exp 1 token unit), locked alphas
  - answering: Ollama on http://localhost:11434 with James's Exp 2 prompts
    (standard = prompts b, strict = grounded prompt v3)
No call leaves the machine: Hugging Face is put in offline mode before the embedding model
loads, and the only HTTP calls are to localhost.
"""
import copy
import json
import os
import re
import sys
import threading
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")          # never download / phone home
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "exp1_retrieval")
sys.path.insert(0, ROOT)
sys.path.insert(1, HERE)
os.chdir(ROOT)                                          # Exp 1 code uses relative paths

import numpy as np                                      # noqa: E402
import requests                                         # noqa: E402
from qdrant_client import QdrantClient                  # noqa: E402

from chunking import count_tokens                       # noqa: E402
from exp1_common import make_chunks, build_retrievers   # noqa: E402
from github_prs import load_pool, load_pr, pool_path    # noqa: E402
from pr_document import build_document                  # noqa: E402
from pr_document_transfer import build_document as build_document_transfer  # noqa: E402
from relations import build_links, expand_and_pack, token_counter  # noqa: E402

OLLAMA = "http://127.0.0.1:11434"      # not "localhost": on Windows that tries IPv6 first (+2 s)
BUDGET = 2560
OLLAMA_OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512}
NOT_FOUND = "Not found in the provided PRs"


def why_task(name):
    """The frozen Exp 2 retrieval instruction (retrieval_config.json); the transfer checks changed
    only the project's name."""
    return (f"Given a question about why a change was made in a {name} pull request, retrieve "
            "the pull request excerpts (description, commit messages, review comments or "
            "discussion) that state the reason")


# build: the document builder each repo's embeddings were made with. The transfer checks removed
# HTML comments from descriptions and sympy-bot's comments; Django's documents don't, so they
# stay on the Exp 1 builder (and its embedding cache stays valid).
REPOS = {
    "django/django": {
        "name": "Django", "dataset": "swe", "collection": "app", "build": build_document,
        "task": why_task("Django"), "emb_cache": "qwen3-embedding-0.6b_swe.npz",
        "dense_chunkings": ("fixed", "structural"),
        "url": "https://github.com/django/django/pull/{n}",
        "item": "PR", "prefix": "#", "host": "GitHub", "note": "", "final_note": "",
        "pools": {"A2000": "Pool A (231 fixing PRs + 2,000 random)",
                  "H2000": "Pool H (231 fixing PRs + 2,000 look-alike, same module)"}},
    "sympy/sympy": {
        "name": "SymPy", "dataset": "sympy", "collection": "app_sympy", "build": build_document_transfer,
        "task": why_task("SymPy"), "emb_cache": "qwen3_sympy.npz",
        "dense_chunkings": ("fixed", "structural"),
        "url": "https://github.com/sympy/sympy/pull/{n}",
        "item": "PR", "prefix": "#", "host": "GitHub",
        "note": "Settings were chosen on Django and not retuned.",
        "final_note": "SymPy's exploratory check did not run this exact combination (its Exp 2 had "
                      "no relation links).",
        "pools": {"A2000": "Pool A (75 fixing PRs + 2,000 random)"}},
    "gitlab-org/gitlab-runner": {
        "name": "GitLab Runner", "dataset": "gitlab", "collection": "app_gitlab",
        "build": build_document_transfer, "task": why_task("GitLab Runner"),
        "emb_cache": "qwen3_gitlab.npz", "dense_chunkings": ("fixed",),
        "url": "https://gitlab.com/gitlab-org/gitlab-runner/-/merge_requests/{n}",
        "item": "MR", "prefix": "!", "host": "GitLab",
        "note": "Settings were chosen on Django and not retuned.",
        "final_note": "GitLab Runner's exploratory check ran this combination, on provisional labels.",
        "pools": {"A2000": "Pool A (231 task MRs + 2,000 random)"}},
}
DEFAULT_REPO = "django/django"

# Chunk settings and relation factors locked on dev (Exp 1), per pool / chunking / retriever
CHUNKINGS = {
    "fixed": {"name": "fixed_s512_o77", "method": "fixed", "size": 512, "overlap": 77},
    "structural": {"name": "struct_c256", "method": "structural", "cap": 256},
}
ALPHAS = {
    "A2000": {"fixed": {"bm25": 0, "dense": 1, "hybrid": 0.5},
              "structural": {"bm25": 0, "dense": 0.5, "hybrid": 0}},
    "H2000": {"fixed": {"bm25": 0.5, "dense": 0.5, "hybrid": 0},
              "structural": {"bm25": 0, "dense": 0.25, "hybrid": 0}},
}

# Exp 2 prompts (James, frozen): standard RAG = b; strict grounded = v3.
# Other repos: only "Django" changes to the project's name, as in the transfer checks (repo_prompt).
PROMPTS = {
    "standard": {
        "system": "You are an assistant that answers questions about pull requests in the Django project.",
        "user": "Use the following excerpts from Django pull requests to answer the question.\n\n"
                "{context}\n\nQuestion: {question}\n\nAnswer in at most three sentences.",
    },
    "strict": {
        "system": "You are an assistant that answers questions about pull requests in the Django project.",
        "user": "Answer the question using ONLY the pull request excerpts below. Do not use outside "
                "knowledge and do not guess.\n\nRules:\n"
                "- The question asks WHY something was done. A reason must be stated in the excerpts in "
                "words, for example by an author or reviewer explaining a decision.\n"
                "- A description of WHAT changed is not a reason. Code changes, titles, commit summaries, "
                "tests or release notes that only show what was done do not answer a WHY question. Do not "
                "work out a reason yourself from the code.\n"
                "- If the excerpts state the reason, answer in at most three sentences. Then cite, in square "
                "brackets, only the id of the excerpt whose text states the reason, for example [PR1234-c0]. "
                "This is usually a single excerpt; cite a second one only if the reason is split across two. "
                "Never cite an excerpt that does not state the reason.\n"
                f"- If the excerpts do not state the reason, reply with exactly this sentence and nothing else: {NOT_FOUND}\n\n"
                "{context}\n\nQuestion: {question}",
    },
}


# Version labels of the prompts above, recorded with feedback (labels only; prompts unchanged).
PROMPT_VERSIONS = {"standard": "b", "strict": "v3"}


def repo_prompt(repo, mode):
    name = REPOS[repo]["name"]
    return {part: text.replace("Django", name) for part, text in PROMPTS[mode].items()}


def with_quote(question, quote):
    """The question as the model sees it when the user quoted something. The quote only says what
    the question is about: it may be an earlier model answer, so it must not count as evidence.
    Without a quote this is the plain question, as in the experiments."""
    if not quote.strip():
        return question
    return (f"{question.strip()}\n\nThis question refers to the passage below. It is quoted by the user, "
            f"may come from an earlier answer, and is not evidence; use only the excerpts above as "
            f"evidence.\n\"\"\"\n{quote.strip()}\n\"\"\"")


CITE = re.compile(r"\[\s*PR\s*#?\s*(\d+)\s*-\s*c\s*(\d+)\s*\]", re.I)
WORD = re.compile(r"[a-z0-9_]+")
STOP = set("the a an of to and or is are was were be been in on for with that this it its as by "
           "at from not no but if so do does did can could would should will which who what why how "
           "when where there their they them he she we you i".split())


def short_id(chunk_id):
    """'8930_fixed_s512_o77_3' -> 'PR8930-c3' (what the model sees and cites)."""
    pr, *_, i = chunk_id.split("_")
    return f"PR{pr}-c{i}"


class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = {"state": "idle", "message": "", "progress": None}
        self.client = None
        self.pools = {}            # (repo, pool) -> {"docs", "titles", "synced", "n_prs"}
        self.indexes = {}          # (repo, pool, chunking, retriever) -> dict
        self.embedders = {}        # repo -> Qwen3Embedder (all share one loaded model)
        self.emb_keys = {}         # repo -> set of cached embedding keys
        self.pool_sizes = {}       # (repo, pool) -> number of PRs in the pool file

    # ---------- environment ----------
    def available_pools(self, repo):
        pools = REPOS[repo]["pools"] if repo in REPOS else {}
        return [p for p in pools if os.path.exists(pool_path(repo, p))]

    def _pool_size(self, repo, pool):
        if (repo, pool) not in self.pool_sizes:
            self.pool_sizes[repo, pool] = len(load_pool(repo, pool)["numbers"])
        return self.pool_sizes[repo, pool]

    def repo_list(self):
        """Repositories whose PRs are in this folder, for the sidebar and the chat's selector."""
        out = []
        for repo, r in REPOS.items():
            pools = self.available_pools(repo)
            if pools:
                out.append({"id": repo, "name": r["name"], "item": r["item"],
                            "prs": max(self._pool_size(repo, p) for p in pools)})
        return out

    def ollama_status(self):
        try:
            # generous timeout: while the server loads the embedding model the CPU is busy,
            # and a 2 s limit wrongly reported a running Ollama as "not running"
            tags = requests.get(f"{OLLAMA}/api/tags", timeout=8).json().get("models", [])
            version = requests.get(f"{OLLAMA}/api/version", timeout=8).json().get("version")
            return {"running": True, "version": version, "models": [m["name"] for m in tags]}
        except requests.RequestException:
            return {"running": False, "version": None, "models": []}

    def dense_cache_path(self, repo):
        return os.path.join("emb_cache", REPOS[repo]["emb_cache"])

    def dense_problem(self, repo, chunking):
        """Why dense search can't run for these settings, or None if it can."""
        r = REPOS[repo]
        if not os.path.exists(self.dense_cache_path(repo)):
            return f"No Qwen3 embedding cache for {r['name']} on this computer ({self.dense_cache_path(repo)})"
        if chunking not in r["dense_chunkings"]:
            return f"{r['name']} was only embedded with fixed 512 chunks, not {chunking} chunks"
        return None

    def _emb_keys(self, repo):
        if repo not in self.emb_keys:
            path = self.dense_cache_path(repo)
            if not os.path.exists(path):
                self.emb_keys[repo] = set()
            else:
                with np.load(path) as d:
                    self.emb_keys[repo] = set(d["keys"].tolist())
        return self.emb_keys[repo]

    def dense_coverage(self, repo, chunks):
        """Share of these chunks whose Qwen3 embedding is already cached (dense needs ~100%)."""
        import hashlib
        keys = self._emb_keys(repo)
        if not keys:
            return 0.0
        have = sum(hashlib.sha1(c["text"].encode("utf-8")).hexdigest() in keys for c in chunks)
        return have / max(1, len(chunks))

    # ---------- loading ----------
    def _set(self, state, message, progress=None):
        self.status = {"state": state, "message": message, "progress": progress}

    def _pool(self, repo, pool):
        if (repo, pool) not in self.pools:
            r = REPOS[repo]
            self._set("loading", f"Reading {r['name']}: {r['pools'].get(pool, pool)}")
            numbers = load_pool(repo, pool)["numbers"]
            docs, titles, fetched = {}, {}, []
            for i, n in enumerate(numbers):
                pr = load_pr(repo, n)
                if not pr or pr.get("not_found"):
                    continue
                d = r["build"](pr)
                if d["text"].strip():
                    docs[d["paper_id"]] = d
                    titles[d["paper_id"]] = pr.get("title") or ""
                    if pr.get("fetched_at"):
                        fetched.append(pr["fetched_at"])
                if i % 200 == 0:
                    self._set("loading", f"Reading {r['name']} documents", i / len(numbers))
            self.pools[repo, pool] = {"docs": docs, "titles": titles, "n_prs": len(docs),
                                      "synced": max(fetched) if fetched else None}
        return self.pools[repo, pool]

    def pr_document(self, repo, pool, number):
        """The whole PR as the experiments saw it (read-only, for the PR viewer)."""
        p = self._pool(repo, pool)
        d = p["docs"].get(str(number))
        if d is None:
            return None
        return {"number": int(number), "title": p["titles"].get(str(number), ""),
                "url": REPOS[repo]["url"].format(n=number), "text": d["text"],
                "parts": [{"type": x["type"], "start": x["start"], "end": x["end"],
                           "file": x.get("file_path")} for x in d["parts"]]}

    def _get_embedder(self, repo):
        """One embedder per repo (its own instruction and cache), all sharing one loaded model.
        The instruction must not be shared: embed_query memoises by question text alone."""
        if repo not in self.embedders:
            r = REPOS[repo]
            base = next(iter(self.embedders.values()), None)
            if base is None:
                from dense_retrieval import Qwen3Embedder, DEFAULT_MODEL
                self._set("loading", "Loading the Qwen3 embedding model (local)")
                self.embedders[repo] = Qwen3Embedder(DEFAULT_MODEL, task=r["task"],
                                                     cache_path=self.dense_cache_path(repo))
            else:
                e = copy.copy(base)
                e.query_prompt = f"Instruct: {r['task']}\nQuery:"
                e.cache_path = self.dense_cache_path(repo)
                e._doc_cache = e._load_cache()
                e._query_cache = {}
                self.embedders[repo] = e
        return self.embedders[repo]

    def index(self, repo, pool, chunking, retriever):
        key = (repo, pool, chunking, retriever)
        if key in self.indexes:
            if self.status["state"] == "error":     # an earlier failure no longer applies
                self._set("ready", "Ready")
            return self.indexes[key]
        with self.lock:
            if key in self.indexes:
                return self.indexes[key]
            try:
                r = REPOS[repo]
                p = self._pool(repo, pool)
                docs = [p["docs"][k] for k in sorted(p["docs"], key=int)]
                cfg = CHUNKINGS[chunking]
                self._set("loading", f"Chunking ({chunking})")
                chunks, info = make_chunks(docs, cfg, r["dataset"])
                embedder = None
                if retriever in ("dense", "hybrid"):
                    cov = self.dense_coverage(repo, chunks)
                    if cov < 0.99:
                        raise RuntimeError(
                            f"Dense search on {r['name']} needs the Qwen3 embedding cache for these "
                            f"chunks ({cov:.0%} cached here). Copy emb_cache/ from the GPU laptop, or use BM25.")
                    embedder = self._get_embedder(repo)
                if self.client is None:
                    self.client = QdrantClient(path="qdrant_app")
                self._set("loading", f"Building the {r['name']} {retriever} index ({len(chunks):,} chunks; "
                                     f"first time only)")
                fns = build_retrievers(self.client, r["collection"], cfg["name"], chunks, [retriever],
                                       embedder, chunk_set=info["chunk_set"])
                self._set("loading", "Linking chunks (relation factor)")
                links = build_links(chunks, p["docs"], kinds=("code",))  # as in Exp 1 (alphas tuned on these)
                self.indexes[key] = {"search": fns[retriever], "chunks": chunks, "info": info,
                                     "links": links, "by_id": {c["chunk_id"]: c for c in chunks},
                                     "ntok": token_counter()}
                self._set("ready", "Ready")
            except Exception as e:
                self._set("error", str(e))
                raise
        return self.indexes[key]

    # ---------- answering ----------
    def retrieve(self, question, code, repo, pool, chunking, retriever, links_on):
        idx = self.index(repo, pool, chunking, retriever)
        r = REPOS[repo]
        query = question.strip() + (("\n" + code.strip()) if code and code.strip() else "")
        t0 = time.time()
        ranked = idx["search"](query, 100, None)
        alpha = ALPHAS[pool][chunking][retriever] if links_on else 0.0
        packed = expand_and_pack(ranked, alpha, idx["links"], idx["by_id"], BUDGET, idx["ntok"])
        secs = time.time() - t0
        rank_of = {c["chunk_id"]: i + 1 for i, c in enumerate(ranked)}
        titles = self.pools[repo, pool]["titles"]
        sources = []
        for c in packed:
            sources.append({
                "id": short_id(c["chunk_id"]), "chunk_id": c["chunk_id"],
                "pr": int(c["pr_number"]), "title": titles.get(str(c["pr_number"]), ""),
                "type": c.get("chunk_type"), "file": c.get("file_path"), "text": c["text"],
                "start": c.get("start"), "end": c.get("end"),     # where it sits in the PR (viewer)
                "linked": bool(c.get("linked")), "rank": rank_of.get(c["chunk_id"]),
                "url": r["url"].format(n=c["pr_number"]),
                "tokens": idx["ntok"](c["chunk_id"], c)})
        return {"query": query, "sources": sources, "alpha": alpha,
                "item": r["item"], "prefix": r["prefix"], "host": r["host"],
                "retrieve_seconds": secs, "tokens": sum(s["tokens"] for s in sources),
                "n_prs": len({s["pr"] for s in sources}), "n_linked": sum(s["linked"] for s in sources)}

    def generate(self, question, sources, repo, mode, model):
        for kind, value in self.generate_stream(question, sources, repo, mode, model):
            if kind == "done":
                return value

    def generate_stream(self, question, sources, repo, mode, model):
        """Yields ("token", text piece) as Ollama writes, then ("done", answer dict).
        Same request as before (temperature 0, seed 42), only streamed."""
        p = repo_prompt(repo, mode)
        context = "\n\n".join(f"[{s['id']}]\n{s['text']}" for s in sources)
        user = p["user"].format(context=context, question=question.strip())
        body = {"model": model, "think": False, "stream": True, "options": OLLAMA_OPTIONS,
                "messages": [{"role": "system", "content": p["system"]},
                             {"role": "user", "content": user}]}
        t0 = time.time()
        parts = []
        with requests.post(f"{OLLAMA}/api/chat", json=body, timeout=600, stream=True) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("error"):
                    raise RuntimeError(msg["error"])
                piece = (msg.get("message") or {}).get("content", "")
                if piece:
                    parts.append(piece)
                    yield "token", piece
                if msg.get("done"):
                    break
        text = "".join(parts).strip()
        secs = time.time() - t0
        yield "done", self._finish(text, sources, mode, secs)

    def _finish(self, text, sources, mode, secs):
        # Exp 2 strict rule: only the refusal sentence (citations/whitespace/full stop aside) counts
        bare = re.sub(r"\s+", " ", CITE.sub("", text)).strip().rstrip(".").strip()
        not_found = bare.lower() == NOT_FOUND.lower()
        return {"mode": mode, "answer": text, "not_found": not_found,
                "citations": self._citations(text, sources), "answer_seconds": secs}

    def _citations(self, answer, sources):
        """Cited ids -> which source, and which sentences of it best match the citing sentence."""
        by_id = {s["id"].lower(): s for s in sources}
        out, prev = [], ""
        for sent in re.split(r"(?<=[.!?])\s+", answer):
            claim = CITE.sub("", sent).strip()
            if not WORD.search(claim):           # citation after the full stop: "... . [PR1-c2]"
                claim = prev                     # -> it belongs to the sentence before
            for m in CITE.finditer(sent):
                cid = f"pr{m.group(1)}-c{m.group(2)}"
                src = by_id.get(cid)
                out.append({"id": f"PR{m.group(1)}-c{m.group(2)}", "in_context": src is not None,
                            "highlights": self._highlight(claim, src["text"]) if src else []})
            if WORD.search(CITE.sub("", sent)):
                prev = CITE.sub("", sent)
        return out

    @staticmethod
    def _highlight(claim, text, max_spans=2):
        """Character spans of the source sentences/lines that share the most words with the claim."""
        cw = {w for w in WORD.findall(claim.lower()) if w not in STOP and len(w) > 2}
        if not cw:
            return []
        scored = []
        for m in re.finditer(r"[^\n.!?]+[.!?]?", text):
            sw = {w for w in WORD.findall(m.group().lower()) if w not in STOP and len(w) > 2}
            if not sw:
                continue
            overlap = len(cw & sw)
            if overlap >= 2:
                scored.append((overlap / len(sw | cw) + 0.01 * overlap, m.start(), m.end()))
        scored.sort(reverse=True)
        return sorted([(s, e) for _, s, e in scored[:max_spans]])

    def index_info(self, repo, pool, chunking):
        p = self.pools.get((repo, pool))
        loaded = [k for k in self.indexes if k[:3] == (repo, pool, chunking)]
        n_chunks = self.indexes[loaded[0]]["info"]["n_chunks"] if loaded else None
        return {"repo": repo, "item": REPOS[repo]["item"], "pool": pool,
                "pool_label": REPOS[repo]["pools"].get(pool, pool),
                "n_prs": p["n_prs"] if p else None, "synced": p["synced"] if p else None,
                "n_chunks": n_chunks, "budget": BUDGET}


ENGINE = Engine()
