# app: PR Explainer demo app (local web/desktop UI on the final settings)

> **Submission notes.** This block was added for the submission. The original README follows below it, unchanged.
>
> - **Source.** `ESP3201A_SWE_exp1_app/app/` at `4a77349`. Not from `ESP3201A_SWE_app.zip`.
> - **What it is.** A local app built on the final settings in `final_settings.json`: dense retrieval, fixed 512 chunks, relation links, Qwen3 4B and the strict v3 prompt. It shows cited excerpts or "not found". It has:
>   - a strict/standard switch;
>   - an optional experimental support check, which is the Exp 2 MiniCheck gate imported from `../exp2_django`;
>   - a 👍/👎 and report feedback log, written to `app/feedback/feedback.jsonl`. The log is git-ignored, and the app never learns from it.
> - **Layout changes for the submission (path fixes):**
>   - `engine.py`: `ROOT` is now `../exp1_retrieval`. The Exp 1 code, `prs/`, `emb_cache/` and `qdrant_app/` live there.
>   - `gate.py`: imports the gate from `../exp2_django`.
>   - `server.py`: writes feedback to `app/feedback/`.
>   - `feedback_summary.py` moved in here.
> - **Run.** `pip install -r ../requirements.txt`, then `ollama pull qwen3:4b-instruct-2507-q4_K_M`, then `python app/server.py` from the repo root. The app opens at http://localhost:8000.
> - **Caches to regenerate.** The PR files, embeddings and Qdrant index under `../exp1_retrieval/`. Rebuild them with the Exp 1 download plus `app/import_repo_data.py` for SymPy and GitLab Runner. The first question on a repo builds its index.
> - **Tested.** The support check was tested live for a held-back answer (score 0.04) and for a refusal. The pass case (0.94) and the no-citation case were tested in Python only. No live demo is planned.

---

# PR Explainer — local demo UI

Ask "why was this code changed?" about Django, SymPy or GitLab Runner; get an answer that cites
the pull-request excerpts it used, or "I couldn't find this in the PR history". Runs entirely on
this computer.

## Repositories
Each chat has one repository: pick it in the top bar, or click one in the sidebar for a new chat.

| Repository | Pool | Dense search | Evidence for the settings |
|---|---|---|---|
| `django/django` | A and H | Fixed 512 and structural (embeddings trimmed from `ESP3201A_SWE_exp1_2510`) | Chosen on it (Exp 1 and 2) |
| `sympy/sympy` | A (75 + 2,000) | Fixed 512 and structural | Transfer check only; its Exp 2 had no relation links |
| `gitlab-org/gitlab-runner` | A (231 + 2,000) | Fixed 512 only (BM25 for structural) | Transfer check only; Exp 2 labels are provisional |

SymPy and GitLab Runner use Django's settings unchanged, including its alphas. They are not
tuned for those repos, and the app says so on each one. Treat their answers as exploratory, and
don't compare them with Django as like for like. On GitLab Runner, alpha 1 lost 12 of 167 correct
MRs from the budget in scaled Exp 1, with no strict-correct difference in Exp 2 (33 vs 32 of 52,
provisional labels).

Their documents use `pr_document_transfer.py`, a byte-for-byte copy of the builder those checks
ran (drops HTML comments in descriptions and `sympy-bot`). Django stays on the Exp 1 builder.
The prompts and search instruction differ only in the project's name. Answers still cite ids like
`[PR1234-c0]` as in the experiments, and the UI shows GitLab's as `MR !1234`.

Their data came from the local copies with `app/import_repo_data.py`, which is only needed again
if those copies change. It copies the pool's PR files and keeps only the embeddings of the chunks
the app uses. The first question on a repo builds its search index, which can take a while.

## Run as a desktop app
Double-click **PR Explainer.lnk** in the project folder (or run `pythonw app/desktop.py`).
It opens its own window with its own icon (pywebview, using Windows' built-in WebView2), starts
Ollama if needed, and runs the server inside the app; closing the window stops it. If
`app/server.py` is already running on port 8000, the app uses that instead (the search index can
only be open in one program at a time). Needs `pip install pywebview` once. Chats are kept in
`%LOCALAPPDATA%\PRExplainer` (separate from the browser version's chats).

## Run in the browser
1. Start **Ollama** (open the Ollama app) and pull the model once:
   `ollama pull qwen3:4b-instruct-2507-q4_K_M`   (also works: `qwen3:8b`)
2. From the project folder: `python app/server.py`
3. Open http://127.0.0.1:8000

First start per pool/chunking/retriever builds a search index (~4 min for BM25 structural);
after that it's reused (folder `qdrant_app/`). After a restart, reading the PRs takes ~1 min.

**Dense / hybrid** need the repo's Qwen3 embedding cache in `emb_cache/` (Django's is
`qwen3-embedding-0.6b_swe.npz`, from the GPU laptop; embedding ~30k chunks on a CPU would take
hours). Without it, those buttons are disabled for that repo and BM25 is used.

## What's in it
| Feature | Where |
|---|---|
| Question box + optional code snippet / file path / function name | left panel |
| Answer with citation chips ("PR #8534 · Review comment"), click to jump to the source | answer card |
| Sources panel: PR number, title, chunk type, file, text; cited passage highlighted; diffs in red/green | below the answer |
| "Not found" state (strict grounding) | answer card |
| Link to the PR on GitHub | each source |
| "Runs locally" badge (model, local, no data sent) | top right |
| Retriever (BM25/dense/hybrid), chunking (structural/fixed 512), relation links, pool A/H | Retrieval settings |
| Strict grounding vs standard RAG, and side-by-side compare | Answering settings |
| Repo, number of PRs, last sync | top bar |
| Feedback (👍 / 👎, Report: wrong answer / invented reason / borrowed from another PR / describes what, not why, optional correct PR and comment) → `feedback/feedback.jsonl`, for human review only (see `feedback/README.md`, counts: `python feedback_summary.py`) | under each answer |
| Experimental support check (Settings, off by default; strict answers only): the Exp 2 faithfulness gate imported from `../ESP3201A_Exp2` (`faithfulness.py`, `gate_eval.py`: MiniCheck, cited min, threshold 0.5). Answers below the threshold or with no valid citation are held back behind "Show anyway"; refusals are not scored; the answer text is never changed. Not hallucination protection. See `app/gate.py` | answer card |
| History (last 20, stored in the browser) and timing | left panel / meta line |
| Quote: select text in an answer, source or PR, then "Quote". It joins the search and goes to the model marked as not evidence. Not part of the experiments, and the answer says so | composer |
| Text size (Aa) for all text in the app | top bar |

## Experiment mode vs product mode
The app starts in **experiment mode**: every setting is visible and nothing is presented as
"the recommended setup". Once both experiments are finished, open `app/final_settings.json`,
fill in `retriever` (bm25/dense/hybrid), `chunking` (structural/fixed), `mode`
(strict/standard), `links` (true/false), optionally `model` and a one-line `evidence`, set
`"finalized": true` and restart the server. The app then opens with those settings and folds
the toggles into a collapsed "Experiment settings" section. If a field is missing or invalid,
it stays in experiment mode and shows which field to fix.

**Current state: product mode (finalized).** Dense + fixed 512/77 + relation links (Exp 1
code links, alpha 1 on pool A / 0.5 on pool H) + 2,560-token budget + qwen3 4B-instruct +
strict grounded prompt v3. Retrieval and links are backed by significant Exp 1 results; the
rest is chosen, not proven best. This exact combination was not evaluated end to end (Exp 2
ran fixed chunks without links). Without `emb_cache/` the app falls back to BM25 and says so.

## How it maps to the experiments
- Retrieval = Experiment 1 code: locked chunk settings (structural cap 256, fixed 512 / 15%),
  2,560-token budget, relation factor with the alphas locked on dev per pool x chunking x
  retriever (alpha 0 = links off for that setting by the safety rule). Links used: Exp 1
  code links only (the links the alphas were tuned on).
- Answering = Experiment 2 prompts (James): standard = prompt b, strict = grounded prompt v3;
  temperature 0, seed 42, num_ctx 8192.
- Dense queries use Exp 2's frozen "why" retrieval instruction, with only the project's name
  changed for SymPy and GitLab Runner. Until 6 Nov Django used different wording, so answers and
  demo checks from before then may differ.

## Privacy
Server listens on 127.0.0.1 only. The only network calls are to Ollama on 127.0.0.1.
Hugging Face is forced offline. "Open on GitHub" links are opened by you, in your browser.

## Demo (under 2 minutes)
Use the final setup (the composer shows "Final setup"). Checked on 6 Nov with the real 4B on
Ollama 0.40.4, Django pool A unless stated. Copy the questions exactly.

1. **Success** — "Why did some Selenium tests need additional waits once they ran on GitHub
   Actions instead of Jenkins?" Answers that GitHub Actions seems faster, so it is more sensitive
   to missing waits. Click the citation chip to see the source in the PR.
2. **Not found** — "Why did Django's PostgreSQL test requirements switch from psycopg2-binary to
   the psycopg2 package?" Strict grounding replies not found: the PR states no reason.
3. **Compare** — "Why did Django raise its minimum supported SQLite version to 3.8.3?" Turn on
   "Compare standard vs strict". Standard RAG gives a plausible reason the PR doesn't state, and
   strict says not found. Turn compare off afterwards.
4. **Code** — "Why didn't the author fix the list filter crash by making AutoField's
   get_prep_value() validate input and raise ValidationError?" with
   `django/db/models/fields/__init__.py AutoField.get_prep_value` under "Add code". Answers that it
   would be a breaking change.
5. **Other repos (optional)** — chat on `gitlab-org/gitlab-runner`: "Why did the feature flags
   documentation table stop using an x in its Deprecated column?" (community feedback found it
   confusing). Chat on `sympy/sympy`: "Why was it important that nsolve accept SymPy complex numbers
   as initial points?" (the default solver won't find complex roots from a real starting point).
   The first question on a repo may build its index, so run these once beforehand.

**If asked about limits, say it fails both ways.** The 4B over-abstains on some answerable
questions (the LiveServerThread port default says not found) and answers some no-reason ones (the
collectstatic verbosity and JavaScriptCatalog UTF-8 questions). This matches Exp 2.

These examples were picked because they behave well, so they show the app working but aren't
results. Run them once on the presenting computer: answers can change across GPUs and Ollama
versions, and even between runs. If one behaves differently, swap it rather than changing settings.
