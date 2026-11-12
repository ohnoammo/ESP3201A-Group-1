# TIDY_LOG: how this repository was assembled (12 Nov 2026)

Everything here was **copied**. No source folder was moved, deleted or edited. The only git commands run inside the source repos were `log`, `status`, `diff` and `branch`. **Nothing was merged:** following James's instruction, the `exp2-baselines` state of `gitlab_runner_copy` was copied as-is. Root of all sources: `…/Claude code/ESP3201A/`.

## 1. Sources

| Part | Source | Commit / state |
|---|---|---|
| `exp1_retrieval/` | `ESP3201A_SWE_exp1_app/`, without `app/`, `feedback/`, `feedback_summary.py` and `.gitignore` | `master` at `4a77349` (clean apart from caches). Code and `results/` are byte-identical to `ESP3201A_SWE_exp1_2510/ESP3201A_SWE_exp1` and `ESP3201A_SWE_exp1_0111/ESP3201A_SWE_exp1_v3/ESP3201A_SWE_exp1`, except `AI_HANDOFF.md` (newer here) and `requirements.txt` (adds the app packages). The test results equal the contents of `test_results_poolA_poolH.zip`. |
| `app/` | `ESP3201A_SWE_exp1_app/app/`, plus `feedback/README.md` → `app/feedback/` and `feedback_summary.py` → `app/` | `4a77349` (not `ESP3201A_SWE_app.zip`) |
| `exp2_django/` | `ESP3201A_Exp2/`, without `results/aborted/` and `results/oldpool/` (both archived) | `master` at `5237783`. Branches `hybrid-h0`, `sympy-h0`, `sympy-transfer` and `lora-fit-check` are all already merged into `master` (`git branch --no-merged master` is empty). **Working tree copied** (James's decision), and it includes these uncommitted items: modified `HANDOVER.md` (+3 lines) and `results/sympy_h0/correctness_sheet_james.csv` (1 row); untracked `judgements/gate_pass_tags_clifton.md`, `results/faithfulness_run.log`, `results/faithfulness_unanswerable_run.log` and `tuning_rule_hallucination_test.md`. |
| `exp2_gitlab/` | `gitlab_runner_copy/`, without `codex_steering/` (→ `steering/`) and `results/INVALID_no_comments_exp1_gitlab_A270_per_query.csv` (archived) | Branch `exp2-baselines` at `c52e13e`, **not merged**. Working tree copied, including the modified `results/baselines_unanswerable_full.xlsx` (James's edits) and the untracked `ADVISOR_NOTES.md`. |
| `exp2_gitlab/exp2_gitlab/Answered_csvs/` | `gitlab_runner_validation/exp2_gitlab/Answered_csvs/` | The pilot's raw labelled sheets, read by `reconcile_correctness.py`. They exist only in that folder. |
| `exp2_gitlab/logs_A2000/` | `gitlab_runner_logs/` | Run logs of the scaled Exp 2 (6 Nov) |
| `exp2_gitlab/results/UNANSWERABLE_READ_RESULTS.md`, `unanswerable_read_unblinded.csv` | `FOR_JAMES_update_12Nov/exp2_baselines/` | Clifton, 12 Nov |
| `steering/` (code, `out/`, `tests/`, `human_check/`) | `gitlab_runner_copy/codex_steering/` | Untracked in `gitlab_runner_copy`. Working tree copied. |
| `steering/results_final/` | `gitlab_runner_validation/steering_results_final/` | Final, 10–11 Nov, with labels. Newer than the 9 Nov outputs in `ESP3201A_local`. |
| `steering/results_final/vectors.npz` | `C:\Users\kwekt\ESP3201A_local\gitlab_runner_copy\codex_steering\out\vectors.npz` | Exists only in `ESP3201A_local` |
| `steering/verify/` | `FOR_JAMES_update_12Nov/steering/verify/` | This is the "steer_check" folder: `verify_codex_results.py`, its README, the review, Clifton's pair-check sheet and `codex_original/`. Clifton's note suggested it as a later commit. It is in the single commit here because James asked for one commit. |
| `transfer_sympy/` | `ESP3201A_SWE_exp1_sympy.zip` (1.6 GB) | 58 code/result members extracted (prefix `ESP3201A_SWE_exp1_sympy/` removed). Caches skipped (see section 2). |
| `docs/` | `ESP3201A_SWE_exp1_app/AI_HANDOFF.md`; `ESP3201A_Exp2/HANDOVER.md` and `exp2_handoff.md`; `gitlab_runner_copy/HANDOVER.md` and `ADVISOR_NOTES.md`; top-level `STEERING_HANDOFF.md`, `STEERING_RESULTS.md` and `EXP2_BASELINES_HANDOFF.md` (12 Nov); `FOR_JAMES_update_12Nov/UPDATE_FOR_JAMES.md` (→ `UPDATE_12Nov.md`); `outputs/2026-11-06_final_presentation/*.pptx` | The top-level `STEERING_RESULTS.md` (12 Nov) differs from `steering_results_final/STEERING_RESULTS.md` (11 Nov). The newer one is in `docs/`, and the older one stays unchanged in `steering/results_final/`. |

New files written for the submission:
- `README.md`, `.gitignore`, `requirements.txt` and `TIDY_LOG.md`;
- `exp2_gitlab/README.md`, `steering/README.md`, `transfer_sympy/README.md` and `docs/README.md`;
- a "Submission notes" block added at the top of `exp1_retrieval/README.md`, `exp2_django/README.md` and `app/README.md`. The original text below each block is unchanged.

## 2. Exclusions
- **Caches**, never copied: `emb_cache/`, `prs/`, `chunks/`, `qdrant_app/`, `qdrant_exp1/` and `__pycache__/` in every source, plus each repo's `.git/`.
  - From the SymPy zip: `prs/` (2,103 files), `qdrant_exp1/` (14), `chunks/` (6), `emb_cache/` (1) and `__pycache__/` (11). These make up nearly all of its 5.06 GB uncompressed size.
- **Activations**: `ESP3201A_local/gitlab_runner_copy/codex_steering/out/acts/` (159 files, 11 MB). They can be regenerated and are git-ignored by the steering build.
- **Archives**:
  - `gitlab_runner_copy/results/exp2_baselines_bundle.zip`;
  - the top-level `ESP3201A_SWE_app.zip`, `ESP3201A_SWE_exp1_sympy.zip` (members extracted only), `ESP3201A_Exp2_0611.7z`, `dev_results_poolA_poolH.zip` and `test_results_poolA_poolH.zip` (their contents equal `exp1_retrieval/results/`);
  - the zips in `_2510` and `_0111`;
  - `ESP3201A_local/codex_steering_out.zip` and `codex_steering_KEYS_open_after_labelling.zip`. Their contents are superseded by `steering_results_final`, and the key is identical.
- **Feedback log**: `ESP3201A_SWE_exp1_app/feedback/feedback.jsonl`.
- **Model weights**: none were in the sources copied. `ESP3201A_local/hf/Qwen3-8B` was not touched.
- **Files over 50 MB**: none were copied. The largest file is 5.03 MB.
- **Tokens and `.env`**: no `.env` files exist in the sources. The scan result is in section 5.
- **Not copied, machine-specific or not part of the project code:**
  - `.claude/launch.json`;
  - `ESP3201A_local/lora_env`, `pylib_h0` and the loose logs there;
  - `PROMPT_report_new_chat.md`;
  - `GitLab Data for Testing … Recommendations.md` (a research note);
  - `Github description.txt` (its text is in `README.md`);
  - `FOR_JAMES_update_12Nov/UPDATE_FOR_JAMES.md` is copied only as `docs/UPDATE_12Nov.md`.
- **Archived to `../ESP3201A_submission_archive/`** (52 MB, not pushed; caches and zips excluded):

  | Archive folder | Contents |
  |---|---|
  | `exp1_pilot_Oct14/` | `ESP3201A_SWE_exp1`: Oct pilot, with `HOTO/` handoffs |
  | `exp1_v2_2210/` | `ESP3201A_SWE_exp1_2210`: v2 |
  | `exp1_v3_2510_duplicate/`, `exp1_v3_0111_duplicate/` | Duplicates of the final |
  | `gitlab_runner_validation/` | The whole folder (older 6 Nov code, identical to `gitlab_runner_copy` there, plus the steering results) |
  | `exp2_django_results_aborted/`, `exp2_django_results_oldpool/` | Superseded Exp 2 Django results |
  | `misc/` | `INVALID_no_comments_exp1_gitlab_A270_per_query.csv`; the top-level `AI_HANDOFF.md` of 25 Oct (older than the 6 Nov one in `docs/`); `2026-11-05_question_check_review/` |

## 3. Path fixes (in the copies only)

| File | Before | After | Why |
|---|---|---|---|
| `app/gate.py` | `EXP2 = join(dirname(dirname(dirname(__file__))), "ESP3201A_Exp2")` | `EXP2 = join(dirname(dirname(__file__)), "exp2_django")` | `app/` is now one level below the repo root, and Exp 2 is `exp2_django/` |
| `app/engine.py` | `ROOT = os.path.dirname(HERE)` | `ROOT = os.path.join(os.path.dirname(HERE), "exp1_retrieval")` | The Exp 1 modules and the app's caches (`prs/`, `emb_cache/`, `qdrant_app/`) are under `exp1_retrieval/`. `os.chdir(ROOT)` and `sys.path` follow. |
| `app/server.py` | `FEEDBACK_DIR = join(dirname(HERE), "feedback")` | `FEEDBACK_DIR = join(HERE, "feedback")` | The feedback log now sits in `app/feedback/` (git-ignored). `feedback_summary.py` moved to `app/` and already reads `HERE/feedback`, so it needed no edit. |
| `exp2_gitlab/exp2_gitlab_baselines.py` | `EXP2_DIR = …join(…, "..", "ESP3201A_Exp2")` | `… "..", "exp2_django")` | Exp 2 folder renamed |
| `exp2_gitlab/reconcile_correctness.py` | `ANSWERED = r"C:/Users/kwekt/OneDrive - …/gitlab_runner_validation/exp2_gitlab/Answered_csvs"` | `ANSWERED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exp2_gitlab", "Answered_csvs")` | The sheets are now copied in next to the script |

**Not fixed, documented in the READMEs instead:**
- **Absolute paths into `C:/Users/kwekt/ESP3201A_local/…`:** `exp2_django/common.py`, `exp1_retriever.py`, `pack_exp1.py`, `link_map.py`, `leakage_variant.py`, `sanity_check.py`, `sympy_h0.py` and `retrieval_config.json`. They point at regenerable index and cache copies that are not in the repo.
- **`steering/codex_steer.py`:** finds the Exp 2 code via `--repo`. Run it with `--repo exp2_gitlab`.
- **Stale paths in docs and comments** (e.g. `../ESP3201A_SWE_exp1/` in the original `exp2_django/README.md`): left as written.

## 4. ESP3201A_local findings (read only)
`C:\Users\kwekt\ESP3201A_local` is **not** a git repo. Its `gitlab_runner_copy/` is.
- **`gitlab_runner_copy` branch history:**
  - Branch `gitlab-runner-pilot` has **5 commits that are not on OneDrive**: `dd8f532` "codex steering: before setup", `657eda1` "after setup", `e219b2e` "before main", `c3917d7` "main results" and `54175c8` "sweep results". All five sit on `74efd58`, which is OneDrive's `gitlab-runner-pilot` tip.
  - It does not have `exp2-baselines` (the 20 commits from `f33ead5` to `c52e13e`, OneDrive only).
- **Diff of `gitlab_runner_copy`, local vs OneDrive (caches excluded):** 188 files only local, 65 only OneDrive, and 1 that differs (`.gitignore`).
  - The local-only files are all `codex_steering/out/` run outputs from 9 Nov: 159 `acts/*.npz`, `gen_*.jsonl`, logs, `stats*`, `selection.json`, `sweep.*`, `vector_info.json`, `vectors.npz` and `keys/blind_key.json`.
  - Against the final `steering_results_final`, only `codex_report.md`, `stats.json` and `sweep.png` differ. The final versions add the correctness tables after Clifton's labels.
  - `vectors.npz` exists only locally, so it was copied into `steering/results_final/`.
  - The two `blind_key.json` files are identical (md5 `bf58b0ea…`).
  - The OneDrive-only files are the baselines work (P0/CB/F0 rerun, gate, correctness, tagging) plus `score_baselines_*`.
- **`gen_*.jsonl` outside steering** (`exp2_gitlab*/gen_{F0,C1}.jsonl`, `sympy_copy_h0/exp2_sympy/gen_{F0,S0-G}.jsonl`): each has a byte-identical copy on OneDrive.
- **The H0 arm:** its generations and labels (`gen_H0.jsonl`, `gen_F0-rerun.jsonl`, the sheets) are in `ESP3201A_Exp2/results/sympy_h0/` on OneDrive. `sympy_copy_h0/` is the unzipped SymPy workspace H0 ran in: its file list equals the zip's 58 code/result files, plus caches. Nothing H0-specific exists only locally.
- **`exp1_copy`, `exp1_copy_hybrid`, `exp1_copy_redacted`, `exp1_copy_redacted_hybrid`:** Exp 2's read-only Exp 1 workspaces (code, indexes, caches, no `results/`). They are referenced by absolute path from `exp2_django`; see section 3.
- **Other local files:**
  - `index_fixed_s512_o77.npz`, `links_*.json`, `log_*.txt`, `ollama_serve.log` and review-sheet backups: workspace artefacts, not copied.
  - `hf/Qwen3-8B` (weights) and `lora_env`/`pylib_h0` (environments): not copied.
  - `codex_progress.py` and `codex_sweep_waiter.ps1`: James's run helpers, not copied.

## 5. Keys and checks

**Keys included**, all with final labels:
- `exp2_gitlab/results/keys/baselines_blind_key.json`: baselines. Clifton's labels were final on 12 Nov.
- `steering/results_final/keys/blind_key.json`: steering. Clifton labelled it on 10 Nov.
- `exp2_django/blind/keys/`: `pilot_v1_key.json`, `pilot_v2_key.json`, `test_4b-hybrid_key.json`, `test_4b-instruct_key.json`, `test_8b_key.json`, `test_arms_4b-instruct_key.json` and `test_arms_8b_key.json`.
- `exp2_django/judging/keys/judging_key.json`
- `exp2_django/results/sympy_h0/keys/sheet_key.json`
- `exp2_django/results/sympy/sheet_key.json`: a key file outside a `keys/` folder.
- `exp2_gitlab/exp2_gitlab/keys/sheet_key.json`: the GitLab pilot.
- `transfer_sympy/exp2_sympy/keys/sheet_key.json`

The extra Exp 2, SymPy and pilot keys were included on James's decision at the plan checkpoint.

**Keys left out:**
- `gitlab_runner_copy/exp2_gitlab_A2000/keys/` (`sheet_key.json`, `sheet_key_before_q5853.json`), because the 87-row F0/C1 sheet is still unlabelled.
- The keys copies inside the zips and in `ESP3201A_local`.

**Git note.** `exp2_gitlab/.gitignore` (copied unchanged) lists `results/keys/` and `exp2_gitlab/keys/`. Those two included keys were therefore added with `git add -f`. `exp2_gitlab_A2000/keys/` is not in the folder at all.

**Size.** 52 MB and 658 files, none over 50 MB. The 20 largest:
- 5.03 MB `steering/results_final/gen_inner.jsonl`
- 2.64 MB `docs/presentation/ESP3201A_final_presentation_6Nov.pptx`
- 2.48 MB `steering/results_final/gen_sweep.jsonl`
- 2.32 MB and 2.28 MB `exp1_retrieval/results/swe_exp1_test{,H}_tuned_per_query.csv`
- 1.57 MB × 2 `steering/{out,results_final}/prompts.jsonl`
- 1.50 MB and 1.48 MB `exp1_retrieval/results/swe_exp1_test{,H}_untuned_per_query.csv`
- 1.37 MB and 1.35 MB `exp2_django/results/gen_test_arms_{8b,4b-instruct}.jsonl`
- 1.12 MB, 1.10 MB and 0.92 MB `exp1_retrieval/results/swe_exp1_dev{_v2,H,}_per_query.csv`
- 0.94 MB `transfer_sympy/results/swe_exp1_sympy_tuned_per_query.csv`
- 0.70 MB, 0.62 MB and 0.61 MB `exp2_django/results/candidates_*_k100*.jsonl`
- 0.66 MB `exp2_gitlab/exp1_gitlab/tasks_A2000.json`
- 0.64 MB `exp2_django/judging/codex_pack.csv`

**Token scan.** Patterns: `ghp_`, `github_pat_`, `glpat-`, `hf_`, `sk-`, `GITHUB_TOKEN=` and `Authorization` values. **No secret values were found.**
- Every hit is code or prose: `"Authorization": f"Bearer {token}"` with the token read from the environment, `export GITHUB_TOKEN=<token>` placeholders, `hf_home`/`hf_answered` variable names, the word "instruction", "Binary Authorization" in GitLab MR text, and a `/glpat-.*/` regex quoted in an MR description.
- No `.env` files exist.
- The scan was re-run before the commit.

**Smoke tests**, run from the repo root with Python 3.11.0:
- **`python exp1_retrieval/sparse_retrieval.py --selftest`: PASS.** Max |Qdrant − reference BM25| was 2.79e-07, and the top result agreed with rank_bm25 on 4/4 queries.
  - The system Python lacks `nltk` and `rank_bm25`, as the handoff notes record.
  - For this test, `nltk` 3.10.3 came from `ESP3201A_local/pylib_h0` via `PYTHONPATH`, and `rank-bm25==0.2.2` was installed into a scratch folder outside the repo. No system packages were changed.
- **Import check of `app/server.py`** (`import server, engine, gate` with `app/` on `sys.path`): **PASS.**
  - 13 routes.
  - `engine.ROOT` resolves to `exp1_retrieval/`.
  - `FEEDBACK_DIR` resolves to `app/feedback/`.
  - `gate.EXP2` resolves to `exp2_django/`, where `gate_eval.py` and `faithfulness.py` were found.
  - No server was started, no model was loaded and no GPU was used. The `__pycache__` it created was deleted.
- **`exp2_gitlab/exp2_gitlab_baselines.py` and `reconcile_correctness.py`:** parse cleanly, and `exp2_gitlab/exp2_gitlab/Answered_csvs/` exists.

## 6. Commit
- `git init -b main`, then one commit authored by Kwek Tze Xuan (`113795508+ohnoammo@users.noreply.github.com`), with co-author trailers for Alyssa Chua Sin Ru and Liu Ziheng, Clifton, as in the app repo.
- Remote `origin` = `https://github.com/ohnoammo/ESP3201A-Group-1.git`. **Not pushed.**

## 7. Update, 12 Nov evening (second commit): REPO_CHECK_12Nov additions and fixes
- **Added from `FOR_JAMES_repo_additions/`** (all new; nothing overwritten):
  - `exp1_retrieval/posthoc_links_test.py`;
  - `exp1_retrieval/results/posthoc_links_test.txt`. Re-running the script reproduces this file exactly.
  - `steering/results_final/steering_tradeoff.png`.
- **Added from `report_app_figs/`** as `docs/report_figures/`: Fig. 2 (`fig_exp1_links.png` plus `fig_links.py`; its 12 values match the per-query CSVs), the four app screenshots, and `report_app_section.md`.
- **README changes:**
  - top README: a post hoc row in the results index, an AI-use section and a `docs/report_figures/` mention;
  - `exp1_retrieval/README.md`: the post hoc test;
  - `steering/README.md`: the PNG, the token note, and the verifier command fixed to absolute paths (the verifier changes into `--repo` before importing, so relative paths fail);
  - `exp2_gitlab/README.md`: `baselines_correctness.md` is the canonical file, and the `clifton*` files print p = 0 because of rounding;
  - `app/README.md`: the live pass case (0.95) shown in the report screenshot;
  - `docs/README.md`: a report-figures section.
- **Removed:** `exp2_gitlab/results/logs/*.pid` and `*.progress` (10 run-time markers), now git-ignored. The `.log` and `.done` files are kept, because they record completion times and row counts. No result numbers or label files were changed.
- **Not applied:**
  - the report link, because there is no final PDF yet (only drafts in `.docx`);
  - deleting the `baselines_correctness_clifton*` files: they are kept as a cross-check, and the README says which file to cite.
- **Re-run checks** on a copy of the working tree:
  - Exp 1 `stats.py` for pools A and H, and SymPy `stats.py`: identical to the committed stats files.
  - `exp2_django/make_results_tables.py`: identical, apart from the commit stamp.
  - `score_baselines_correctness.py`: identical `.csv` and `.md`.
  - `steering/verify/verify_codex_results.py`: ALL CHECKS PASSED.
  - BM25 selftest: OK.
  - `app/server.py` import: OK.
  - All 119 `.py` files parse.
