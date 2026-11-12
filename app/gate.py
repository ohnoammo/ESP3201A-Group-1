"""Experimental support check (the Exp 2 faithfulness gate), optional in the demo app.

Nothing is reimplemented here: the claim splitting (faithfulness.sentences), the cited-premise
rule (faithfulness.CITE), the MiniCheck model and its window scoring (faithfulness.MiniCheck)
and the threshold (gate_eval.THRESHOLD = 0.5) are imported from ..\\ESP3201A_Exp2, exactly as
faithfulness.py and gate_eval.py use them:
  - premise = the context chunks the answer cites (context order); none -> held back (no_citation)
  - score   = min over the answer's sentences of MiniCheck(premise, sentence)   ("cited min")
  - passed  = score >= THRESHOLD; otherwise held back (low_score)
Only strict-prompt (v3) answers are checked, and refusals are not scored. The answer text is
never changed. Offline: the model loads from the local Hugging Face cache (engine.py sets
HF_HUB_OFFLINE). Not hallucination protection: in Exp 2 it separated unanswerable answers from
answered answerables only weakly (AUROC about 0.54-0.57).
"""
import os
import sys
import threading
import time

EXP2 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "exp2_django")

_lock = threading.Lock()
_F = _G = _model = None
_error = None


def _import():
    """Import faithfulness.py and gate_eval.py from Exp 2 (appended to sys.path, so the app's own
    modules keep priority). Returns the error text, or None."""
    global _F, _G, _error
    if _F is not None or _error is not None:
        return _error
    if not os.path.isdir(EXP2):
        _error = f"Exp 2 folder not found: {EXP2}"
        return _error
    if EXP2 not in sys.path:
        sys.path.append(EXP2)
    try:
        import faithfulness as F
        import gate_eval as G
        _F, _G = F, G
    except Exception as e:                                   # report, don't hide
        _error = f"Could not import the Exp 2 gate: {type(e).__name__}: {e}"
    return _error


def status():
    """{"available": bool, "loaded": bool, "problem": str|None, "threshold": float|None}"""
    err = _import()
    return {"available": err is None, "loaded": _model is not None, "problem": err,
            "threshold": None if err else _G.THRESHOLD}


def load():
    """Load MiniCheck once (about 8 s on the GPU). Safe to call from several threads."""
    global _model
    if _import():
        raise RuntimeError(_error)
    with _lock:
        if _model is None:
            _model = _F.MiniCheck()
    return _model


def check(answer, sources):
    """Gate one strict answer dict (from engine._finish) against the sources given to the model.
    Returns the gate record; the answer itself is not modified."""
    if answer.get("not_found"):
        return {"status": "not_scored_refusal", "score": None, "threshold": _G.THRESHOLD if _G else 0.5,
                "passed": None, "held_back_reason": None, "seconds": 0.0}
    mc = load()
    t0 = time.time()
    text = answer["answer"]
    cited = set(_F.CITE.findall(text))
    premise = [s["text"] for s in sources if s["id"] in cited]   # context order, as faithfulness.py
    rec = {"status": "scored", "threshold": _G.THRESHOLD, "n_cited_chunks": len(premise)}
    if not premise:                                              # no valid citation: gated
        rec.update(score=None, passed=False, held_back_reason="no_citation", sentence_scores=[])
    else:
        sents = _F.sentences(text)
        scores = [mc.score(premise, x) for x in sents]
        score = min(scores)
        passed = score >= _G.THRESHOLD
        rec.update(score=round(score, 4), passed=passed, held_back_reason=None if passed else "low_score",
                   sentence_scores=[{"sentence": x, "score": round(v, 4)} for x, v in zip(sents, scores)])
    rec["seconds"] = round(time.time() - t0, 2)
    return rec
