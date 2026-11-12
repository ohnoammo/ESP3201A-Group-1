"""Local web UI for the code-review RAG assistant.

    python app/server.py            (from the project folder)
    then open http://127.0.0.1:8000

Binds to 127.0.0.1 only (not reachable from other machines). Talks only to Ollama on
localhost. See app/README.md.
"""
import datetime
import json
import os
import threading

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import gate
from engine import ENGINE, CHUNKINGS, DEFAULT_REPO, HERE, PROMPT_VERSIONS, REPOS, with_quote

app = FastAPI(title="Code review RAG (local)")
STATIC = os.path.join(HERE, "static")
# Feedback log for human review (see feedback/README.md). Nothing reads it back into the app.
FEEDBACK_DIR = os.path.join(HERE, "feedback")
FEEDBACK = os.path.join(FEEDBACK_DIR, "feedback.jsonl")
FEEDBACK_LOCK = threading.Lock()
RATINGS = {"up", "down"}
REPORT_TYPES = {"wrong_answer", "invented_reason", "borrowed_from_other_pr", "what_not_why"}
FINAL = os.path.join(HERE, "final_settings.json")
VALID = {"retriever": {"bm25", "dense", "hybrid"}, "chunking": set(CHUNKINGS),
         "mode": {"strict", "standard"}}


def final_settings():
    """Product defaults from app/final_settings.json, only once both experiments are done.
    Returns {"finalized": False} (experiment mode) unless finalized is true AND every
    required field holds a valid value."""
    try:
        with open(FINAL, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        return {"finalized": False, "problem": "app/final_settings.json missing or not valid JSON"}
    if not s.get("finalized"):
        return {"finalized": False}
    bad = [k for k, ok in VALID.items() if s.get(k) not in ok]
    if not isinstance(s.get("links"), bool):
        bad.append("links")
    if bad:
        return {"finalized": False, "problem": f"final_settings.json: fill in {', '.join(bad)}"}
    return {k: v for k, v in s.items() if not k.startswith("_")}


class Ask(BaseModel):
    question: str
    quote: str = ""                         # text selected from an earlier answer, source or PR
    code: str = ""
    repo: str = DEFAULT_REPO
    pool: str = "A2000"
    chunking: str = "structural"
    retriever: str = "bm25"
    links: bool = True
    modes: list[str] = ["strict"]          # ["strict"], ["standard"] or both (compare)
    model: str = "qwen3:4b-instruct-2507-q4_K_M"
    gate: bool = False                      # experimental support check on strict answers (gate.py)


class Feedback(BaseModel):
    question: str
    answer: str = ""
    mode: str = ""                          # strict / standard
    model: str = ""
    settings: dict = {}                     # what the UI used for this answer (may differ from final)
    context_chunk_ids: list[str] = []       # chunks given to the model, in context order
    cited_ids: list[str] = []               # ids the answer cites, e.g. PR1234-c0
    gate: dict | None = None                # gate record of the answer (gate.check), if the check ran
    rating: str | None = None               # up / down
    report_type: str | None = None          # one of REPORT_TYPES
    correct_pr: str = ""
    comment: str = ""


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/status")
def status(repo: str = DEFAULT_REPO, pool: str = "A2000", chunking: str = "structural"):
    if repo not in REPOS:
        raise HTTPException(400, f"Unknown repository {repo}.")
    problem = ENGINE.dense_problem(repo, chunking)
    return {"engine": ENGINE.status, "ollama": ENGINE.ollama_status(),
            "repos": ENGINE.repo_list(), "repo_note": REPOS[repo]["note"], "repo_final_note": REPOS[repo]["final_note"],
            "pools": [{"id": p, "label": REPOS[repo]["pools"][p]} for p in ENGINE.available_pools(repo)],
            "chunkings": list(CHUNKINGS), "index": ENGINE.index_info(repo, pool, chunking),
            "dense_cache": problem is None, "dense_problem": problem,
            "final": final_settings(), "gate": gate.status()}


def gated(a, mode, answer, sources):
    """Attach the support-check record to a strict answer when the toggle is on. The answer text
    is left as it is; a failed check is reported, not hidden."""
    if a.gate and mode == "strict":
        try:
            answer["gate"] = gate.check(answer, sources)
        except Exception as e:
            answer["gate"] = {"status": "error", "error": f"{type(e).__name__}: {e}", "score": None,
                              "threshold": 0.5, "passed": None, "held_back_reason": None}
    return answer


@app.post("/api/gate_warmup")
def gate_warmup():
    """Load MiniCheck in the background when the toggle is switched on (about 8 s)."""
    st = gate.status()
    if st["available"] and not st["loaded"]:
        threading.Thread(target=lambda: gate.load(), daemon=True).start()
    return st


@app.post("/api/warmup")
def warmup(a: Ask):
    """Build the index for these settings in the background (first time can take minutes)."""
    def run():
        try:
            ENGINE.index(a.repo, a.pool, a.chunking, a.retriever)
        except Exception:
            pass                            # error is reported through /api/status
    threading.Thread(target=run, daemon=True).start()
    return {"started": True}


@app.post("/api/ask")
def ask(a: Ask):
    if not a.question.strip():
        raise HTTPException(400, "Type a question first.")
    if a.pool not in ENGINE.available_pools(a.repo):
        raise HTTPException(400, f"Pool {a.pool} of {a.repo} is not downloaded.")
    try:
        ret = ENGINE.retrieve(a.question, "\n".join(x for x in (a.quote, a.code) if x.strip()), a.repo, a.pool, a.chunking, a.retriever, a.links)
    except Exception as e:
        raise HTTPException(409, str(e))
    answers, error = [], None
    if ENGINE.ollama_status()["running"]:
        for mode in a.modes:
            try:
                answers.append(gated(a, mode, ENGINE.generate(with_quote(a.question, a.quote), ret["sources"], a.repo, mode, a.model),
                                     ret["sources"]))
            except Exception as e:
                error = f"Ollama error: {e}"
                break
    else:
        error = "Ollama is not running, so only the retrieved sources are shown."
    return {"retrieval": ret, "answers": answers, "error": error,
            "index": ENGINE.index_info(a.repo, a.pool, a.chunking)}


@app.post("/api/ask_stream")
def ask_stream(a: Ask):
    """Same as /api/ask, streamed as one JSON object per line: retrieval, then tokens as the
    model writes them, then each finished answer, then done."""
    if not a.question.strip():
        raise HTTPException(400, "Type a question first.")
    if a.pool not in ENGINE.available_pools(a.repo):
        raise HTTPException(400, f"Pool {a.pool} of {a.repo} is not downloaded.")
    try:
        ret = ENGINE.retrieve(a.question, "\n".join(x for x in (a.quote, a.code) if x.strip()), a.repo, a.pool, a.chunking, a.retriever, a.links)
    except Exception as e:
        raise HTTPException(409, str(e))

    def events():
        line = lambda obj: json.dumps(obj, ensure_ascii=False) + "\n"
        yield line({"type": "retrieval", "retrieval": ret, "index": ENGINE.index_info(a.repo, a.pool, a.chunking)})
        if not ENGINE.ollama_status()["running"]:
            yield line({"type": "error", "error": "Ollama is not running, so only the retrieved sources are shown."})
        else:
            for mode in a.modes:
                try:
                    for kind, value in ENGINE.generate_stream(with_quote(a.question, a.quote), ret["sources"], a.repo, mode, a.model):
                        if kind == "token":
                            yield line({"type": "token", "mode": mode, "text": value})
                            continue
                        if a.gate and mode == "strict" and not value.get("not_found"):
                            yield line({"type": "checking", "mode": mode})
                        yield line({"type": "answer", "answer": gated(a, mode, value, ret["sources"])})
                except Exception as e:
                    yield line({"type": "error", "error": f"Ollama error: {e}"})
                    break
        yield line({"type": "done"})

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.get("/api/pr/{number}")
def pr(number: int, repo: str = DEFAULT_REPO, pool: str = "A2000"):
    """Whole PR document for the viewer panel (read-only; nothing else changes)."""
    if pool not in ENGINE.available_pools(repo):
        raise HTTPException(400, f"Pool {pool} of {repo} is not downloaded.")
    doc = ENGINE.pr_document(repo, pool, number)
    if doc is None:
        raise HTTPException(404, f"{number} is not in {repo} pool {pool}.")
    return doc


def final_settings_raw():
    """app/final_settings.json as it is now (comment keys left out), recorded with each row."""
    try:
        with open(FINAL, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except (OSError, ValueError) as e:
        return {"error": f"could not read final_settings.json: {e}"}


def gate_record(g):
    """The feedback log's gate field: score, threshold, passed, held_back_reason (+ status)."""
    if not g:
        return None
    return {"status": g.get("status"), "score": g.get("score"), "threshold": g.get("threshold"),
            "passed": g.get("passed"), "held_back_reason": g.get("held_back_reason"),
            "seconds": g.get("seconds"), **({"error": g["error"]} if g.get("error") else {})}


@app.post("/api/feedback")
def feedback(f: Feedback):
    """Append one line to feedback/feedback.jsonl. Log only: the app never reads it back."""
    if f.rating not in RATINGS | {None}:
        raise HTTPException(400, f"rating must be one of {sorted(RATINGS)}")
    if f.report_type not in REPORT_TYPES | {None}:
        raise HTTPException(400, f"report_type must be one of {sorted(REPORT_TYPES)}")
    if not (f.rating or f.report_type or f.correct_pr.strip() or f.comment.strip()):
        raise HTTPException(400, "Nothing to save: pick a rating or a report, or write a comment.")
    row = {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "question": f.question, "answer": f.answer,
        "model": f.model or f.settings.get("model", ""),
        "mode": f.mode, "prompt_version": PROMPT_VERSIONS.get(f.mode),
        "final_settings": final_settings_raw(), "settings_used": f.settings,
        "context_chunk_ids": f.context_chunk_ids, "cited_ids": f.cited_ids,
        "gate": gate_record(f.gate),        # null when the support check was off
        "rating": f.rating, "report_type": f.report_type,
        "correct_pr": f.correct_pr.strip() or None, "comment": f.comment.strip() or None,
        "reviewed": False,
    }
    try:
        with FEEDBACK_LOCK:
            os.makedirs(FEEDBACK_DIR, exist_ok=True)
            with open(FEEDBACK, "a", encoding="utf-8") as out:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as e:
        raise HTTPException(500, f"Could not write the feedback log: {e}")
    return {"saved": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
