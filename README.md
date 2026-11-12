# Why Was This Changed? A Local, Grounded RAG Assistant for Code Review History

*Local, offline RAG assistant that answers "why was this code changed?" from GitHub PRs and GitLab MRs, with citations or an honest "not found". Evaluated on Django, SymPy and GitLab Runner.*

NUS ESP3201A, Group 1 · Report: <!-- report link -->

## Project description
Over this six-week project, we built a fully local, offline retrieval-augmented generation (RAG) assistant that answers "why was this code changed?" from a repository's pull requests (GitHub) or merge requests (GitLab). Each PR or MR is treated as one document: its title, description, commit messages, diff, and review and conversation comments.

The system has three parts:
- it retrieves the relevant PR/MR excerpts;
- a small local LLM answers with citations to those excerpts;
- it says "Not found in the provided PRs" when the history gives no reason.

We ran two experiments.

- **Experiment 1 (retrieval, no LLM):**
  - What it compares: fixed-size vs structure-aware chunking, crossed with BM25, dense (Qwen3-Embedding-0.6B) and hybrid (RRF) retrieval.
  - Data: SWE-bench Verified Django tasks (231). The bug report is the query and the fixing PR is the answer.
  - Procedure: settings were tuned on a dev split, and the held-out test split was run once.
  - We used an easy and a hard distractor pool, and a fixed 2,560-token context budget with optional linking between related code chunks.
- **Experiment 2 (generation):**
  - Questions: "why" questions mined from real review threads, answered by qwen3:4b-instruct through Ollama.
  - Comparison: a strict grounded prompt (cite or abstain) against standard RAG and closed-book baselines, plus a MiniCheck-based faithfulness gate and an activation-steering experiment (no weight updates).
  - Scoring: every arm was scored for answer rate, hallucination on unanswerable questions, citation validity and blind human-labelled correctness.

**Repositories tested:** Django (main), with SymPy (GitHub) and GitLab Runner (GitLab) as transfer checks across projects and platforms.

**Demo app:** a local desktop/web app built on the final settings. It shows answers with cited excerpts, has a strict/standard prompt switch and an optional experimental support check, and logs 👍/👎 and "report wrong answer" feedback to a local file for human review.

**Scope:**
- Pre-trained models only, with no training or fine-tuning.
- Everything runs on consumer laptops: RTX 3050 Ti 4 GB and RTX 5070 12 GB.
- Pre-registered tuning rules, a dev/test split and statistical tests: bootstrap CIs, McNemar with Holm correction, and paired permutation.

**Research questions:**
1. Which chunking and retrieval setup best finds the PR that explains a change, and does structure-aware chunking help at equal chunk size?
2. Does a strict grounded prompt reduce hallucinated reasons compared with standard RAG and closed-book answering, and at what cost in answers that could have been given?
3. Can post-hoc checks (a faithfulness gate) or activation steering reduce hallucination further without losing correct answers?

**Software stack:** Python, PyTorch, sentence-transformers (Qwen3-Embedding-0.6B), Qdrant (local mode), BM25, Ollama (qwen3:4b-instruct-2507), Hugging Face Transformers (steering), MiniCheck, the GitHub/GitLab APIs, SWE-bench Verified, and a vanilla JS + Python local web app.

## Folder map
| Folder | What it is | RQ |
|---|---|---|
| [`exp1_retrieval/`](exp1_retrieval/) | Exp 1: chunking × retriever on Django (SWE-bench Verified), pools A and H, final v3 code, results and stats | 1 |
| [`exp2_django/`](exp2_django/) | Exp 2 on Django: questions, generation, scoring, blind labels, judging, faithfulness gate, arms F0/S0/S0-G/S-0.25 (+ W-F, H0), final tables | 2, 3 |
| [`exp2_gitlab/`](exp2_gitlab/) | GitLab Runner transfer: scaled Exp 1, scaled Exp 2, baselines P0 (plain RAG) and CB (closed book), correctness, gate, tagging | 1, 2, 3 |
| [`transfer_sympy/`](transfer_sympy/) | SymPy transfer: Exp 1 and Exp 2 with Django's settings unchanged (Clifton) | 1, 2 |
| [`steering/`](steering/) | Activation steering on the GitLab Runner 70: code, prepared inputs, final results, independent verifier | 3 |
| [`app/`](app/) | PR Explainer demo app: local web/desktop UI, feedback log, optional support check | – |
| [`docs/`](docs/) | Handoff notes, an index of the pre-registered rule files, and the report's figures with their scripts (`docs/report_figures/`) | – |

Each folder has its own README, covering how to run it, which caches to regenerate and which file holds which number. `TIDY_LOG.md` records where every file came from.

## How to reproduce
1. Use Python 3.11 or 3.12, and run `pip install -r requirements.txt`. For a GPU, install a CUDA build of torch (see `exp1_retrieval/environment.yml`). Install [Ollama](https://ollama.com) and run `ollama pull qwen3:4b-instruct-2507-q4_K_M`.
2. Set a GitHub (or GitLab) token **in your terminal only**, never in a file: `export GITHUB_TOKEN=<token>`.
3. Regenerate the caches. These are not in the repo: `prs/`, `chunks/`, `emb_cache/`, `qdrant*/` and `steering/out/acts/`. Each part's README gives the commands. Downloads take hours, and embedding needs a GPU.
4. Re-run or re-score from the saved outputs. Every generation (`gen_*.jsonl`), label sheet and blind key whose labels are final is included, so the statistics and tables can be recomputed offline. Examples: `python exp2_django/make_results_tables.py` and `python exp1_retrieval/stats.py …`.

Quick checks: `python exp1_retrieval/sparse_retrieval.py --selftest`, then `python app/server.py` once the caches exist.

## Results index
| Claim | File |
|---|---|
| Dense beat hybrid and BM25. Django test, pool A, tuned dense fixed 512/77: Hit@5 0.978, MRR@5 0.937 | `exp1_retrieval/results/stats_test_poolA_full.txt` |
| Same comparison on the hard pool H | `exp1_retrieval/results/stats_test_poolH_full.txt` |
| Per-query Exp 1 test rows (tuned and untuned, pools A and H) | `exp1_retrieval/results/swe_exp1_test{,H}_{tuned,untuned}_per_query.csv` |
| Post hoc: structural + links ≈ fixed 512 + links on pool A and beats size-matched + links by 0.16 on both pools | `exp1_retrieval/results/posthoc_links_test.txt` |
| Exp 2 Django Findings 1–9: no arm difference survives Holm; 8B answers more unanswerables; prompt v3; correctness; gate; AUROC; W-F; H0 | `exp2_django/results/exp2_results_tables.md` |
| GitLab Runner closed book: 0/52 strictly correct; grounded F0 and plain RAG P0: 30/52 each | `exp2_gitlab/results/baselines_correctness.md` |
| GitLab Runner unanswerables answered: F0 5, P0 13, CB 18 of 18 (F0 vs P0 Holm p 0.023) | `exp2_gitlab/results/baselines_counts.csv`, `baselines_tests.csv`, `exp2_baselines_report.md` |
| Post hoc human read of the answered unanswerables | `exp2_gitlab/results/UNANSWERABLE_READ_RESULTS.md` |
| Gate on GitLab Runner (F0 unanswerables answered 5 → 2) | `exp2_gitlab/results/baselines_gate*.csv` |
| Scaled Exp 1 on GitLab Runner (alpha 1 vs 0, gold in budget) | `exp2_gitlab/results/exp1_gitlab_A2000_stats.txt` |
| Steering: a trade-off of fewer hallucinations for more refusals; unsteered model best on correctness (39 → 12 at 60:40) | `steering/results_final/stats_tests.csv`, `codex_report.md`, `STEERING_RESULTS.md` |
| Steering results independently verified | `steering/verify/README.md` |
| SymPy transfer, Exp 1 | `transfer_sympy/results/stats_sympy_full.txt` |
| SymPy transfer, Exp 2 (F0 / S0-G counts), and H0 on SymPy | `transfer_sympy/exp2_sympy/summary.csv`, `exp2_django/results/sympy_h0/summary.csv` |

## Limitations
- **Small question sets:** 50 answerable Django questions, 52 on GitLab Runner, and 17–18 unanswerables, so power is low. Several tests are exploratory or post hoc and are labelled that way.
- **Question checks:** mostly automated on GitLab Runner (kappa 0.177).
- **Correctness labels:** each set comes from a single human labeller or an LLM judge checked by one rater (old vs new F0 labels kappa 0.39).
- **Doubtful labels:** a few no_reason labels are doubtful (nr3177, nr4460, nr1372, nr1781).
- **Refusal detection:** the regexes miss some paraphrased refusals.
- **Blinding:** the blinding of plain-RAG answers leaked through left-over "()" traces.
- **Runs:** one seed at temperature 0, with small Ollama run-to-run variation.
- **Transfer checks:** SymPy and GitLab Runner reuse Django's settings unchanged and are counts-only checks.
- **The gate:** it measures citation support, not truth.
- **Steering:** a single vector cannot make refusal depend on whether the evidence is present.
- **Gold answers:** written by Claude.

## AI use
*AI use:* Claude (Anthropic) helped write code and analysis scripts, wrote the GitLab Runner questions and gold answers, and drafted correctness-label and category suggestions that a team member checked row by row; Codex produced the LLM-judge labels (validated against human labels) and, with DeepSeek, the automated question checks.

## Team
Clifton Liu Ziheng, Alyssa Chua Sin Ru, James Kwek Tze Xuan (NUS ESP3201A, Group 1).
