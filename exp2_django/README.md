# exp2_django: Experiment 2, grounded generation (Django "why" questions)

> **Submission notes.** This block was added for the submission. The original README follows below it, unchanged.
>
> - **Source.** `ESP3201A_Exp2`, `master` at `5237783`, plus its working tree on 12 Nov. All side branches (`hybrid-h0`, `sympy-h0`, `sympy-transfer`, `lora-fit-check`) are already merged into `master`. Moved to the archive: `results/aborted/` and `results/oldpool/`.
> - **Research questions.**
>   - RQ2: does the strict grounded prompt (v2/v3) cut hallucinated reasons, compared with standard RAG and no retrieval?
>   - RQ3: does a MiniCheck faithfulness gate help?
>   - Setup: arms F0, S0, S0-G, S-0.25 (plus exploratory W-F and H0); models qwen3:4b-instruct-2507 and qwen3:8b on Ollama 0.40.4; temperature 0, seed 42.
> - **Run.** The full pipeline and the hard rules are in `HANDOVER.md`, and the tuning rules in `tuning_rule_*.md`. Regenerate the tables, offline, with `python make_results_tables.py`. Versions are recorded in `results/run_provenance.md`.
> - **Caches to regenerate.** `common.py`, `exp1_retriever.py`, `pack_exp1.py`, `link_map.py`, `sanity_check.py`, `sympy_h0.py` and `retrieval_config.json` read a read-only Exp 1 working copy at the absolute path `C:/Users/kwekt/ESP3201A_local/exp1_copy*` (index, chunks, embeddings). These are not in the repo. Rebuild them from `../exp1_retrieval` and point those constants at your copy. Only regeneration needs them: every saved candidate and context is already in `results/`.
> - **Which file holds which number:**
>   - The final Findings 1–9, every table and the Limitations: `results/exp2_results_tables.md`.
>   - Tests: `results/stats_test_arms*.csv`, `stats_correctness.csv`, `stats_hybrid.csv`.
>   - Gate: `results/gate_eval*.csv`, `gate_auroc*.csv`.
>   - SymPy transfer and H0 on SymPy: `results/sympy/`, `results/sympy_transfer.csv`, `results/sympy_h0/`.
> - **13 Nov hybrid follow-up (Run 1, Django part, post hoc):** `h0_retrieval_tests.py` writes `results/retrieval_why_django.csv`, the per-question Hit@5, MRR@5 and span for dense (F0) vs hybrid (H0) on the 50 answerable test questions. No new retrieval: it reads the saved candidates. The tests (Holm over 6, with GitLab) are in `../exp2_gitlab/results/retrieval_why_tests.csv`.
> - **Keys.** `blind/keys/`, `judging/keys/`, `results/sympy/sheet_key.json` and `results/sympy_h0/keys/` are included, because all their labels are final.

---

# Experiment 2: grounded generation on Django PR "why" questions

Question: given retrieved context, does a strict grounded prompt make a small local LLM answer
"why" questions about code changes faithfully, and say "not found" when the answer isn't there?

Exp 1 code (`../ESP3201A_SWE_exp1/ESP3201A_SWE_exp1/`) is imported read-only via `common.py`
(`pr_document.build_document`, `chunking.fixed_size_chunks`), so documents, offsets and the
fixed 512/77 chunks are identical to Exp 1 (checked: 400 PRs, 0 mismatches vs its chunk cache).

## Files
| File | What |
|---|---|
| `shortlist.py` | Candidate PRs from pool A (thresholds + funnel in its docstring) -> `shortlist.json` |
| `digest.py` | Readable PR digest (no diffs) used to write questions |
| `questions_src.py` | Hand-written questions (by Claude, not Qwen): 60 answerable, 5 no_reason, 5 removed |
| `build_questions.py` | Verbatim-quote check, span, copy check, gold chunks -> `questions.jsonl`, `review_sheet.csv`, `build_report.json` |
| `prompts/` | (a) no retrieval, (b) standard RAG, (c) strict grounded |
| `run_generation.py` | Ollama runner (think=False, temperature 0, seed 42, num_ctx 8192) -> `results/gen_<tag>.jsonl` |
| `score.py` | Abstention, citation checks, judged labels, rerun agreement -> `results/summary_<tag>.csv` |
| `judgements/` | Correctness labels (pilot: by Claude, to be spot-checked) |
| `blind.py` | Blinded, shuffled hand-check sheet (`blind/`) + separate key (`blind/keys/`) |
| `prompts/FROZEN.json` | Frozen prompt hashes (git tag `prompts-v2-frozen`); `run_generation.py --split test` refuses other prompts |
| `retrieval_config.json` | Retrieval settings incl. the Exp 2 query instruction and embedding model revision |
| `retrieve_np.py` | Read-only dense stand-in: `retrieve(query, k, exclude_prs)`, `get_chunks(pr)`; exact cosine in numpy over Exp 1's cached embeddings (copy outside OneDrive) |
| `eval_retrieval.py` | Top-5 per question (`results/retrieved_top5.jsonl`, the exact generation inputs) + Hit@5 of the quote-containing chunk (`results/retrieval_eval.json`) |

## Splits and labels
- **Dev set** (`pilot_ids.json`, `split=dev`): 10 answerable + 5 no_reason, used only to develop
  the prompts. **Test set** (`split=test`): 50 answerable + 5 no_reason + 5 removed. Full runs
  use the test set only.
- **Pilot correctness labels** (`judgements/pilot_4b_claude.jsonl`) were made by Claude,
  **unblinded** (Claude knew the condition of every response), and are **pending James's
  blinded check** (`blind/pilot_v1_sheet.csv`; key in `blind/keys/`, do not open before
  labelling). Treat them as provisional.
- `questions_retired.jsonl`: nr12338, dropped on 15 Oct because its answer follows from general
  Python knowledge; kept only so the v1 pilot outputs can still be read.

## Run
```
python shortlist.py
python build_questions.py
python run_generation.py --select pilot --tag pilot_4b --conditions none:a oracle:b oracle:c
python score.py results/gen_pilot_4b.jsonl --judgements judgements/pilot_4b_claude.jsonl
```
Tier 2 (retrieved context, test split only):
```
python retrieve_np.py --build --check          # local index + embedding agreement check
python eval_retrieval.py
python run_generation.py --select all --split test --tag test_4b-instruct \
    --conditions none:a retrieved:b retrieved:c oracle:b oracle:c
python score.py results/gen_test_4b-instruct.jsonl --retrieved results/retrieved_top5.jsonl
```

Models (Ollama): `qwen3:4b-instruct-2507-q4_K_M` (primary 4B, non-thinking 2507),
`qwen3:4b-q4_K_M` and `qwen3:8b` (original hybrid Qwen3, same family, for the size comparison).
The plain `qwen3:4b` tag is Qwen3-4B-Thinking-2507, which ignores think=False: do not use it.
