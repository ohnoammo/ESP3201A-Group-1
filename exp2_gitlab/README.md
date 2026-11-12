# exp2_gitlab: GitLab Runner transfer check (Exp 1 scaled, Exp 2 scaled, baselines P0/CB, gate, tagging)

**What it is.** A copy of `gitlab_runner_copy` on branch `exp2-baselines` (`c52e13e`) plus its working tree as of 12 Nov 2026. It was not merged into `gitlab-runner-pilot`. `codex_steering/` was moved out to `../steering/`. It applies Django's final settings, unchanged, to `gitlab-org/gitlab-runner` merge requests, which tests transfer across both project and platform. Everything here is **exploratory** and not part of the Django Findings.

**Research questions served.**
- **RQ1 (retrieval):** scaled Exp 1, with pool A2000 (231 tasks plus 2,000 distractors).
- **RQ2 (grounded prompt vs plain RAG vs closed book):** the baselines on the 70 hand-checked questions (52 answerable, 8 no_reason, 10 removed).
- **RQ3 (gate):** the MiniCheck gate on F0 and P0.

**Run** (Python 3.11/3.12; `pip install -r ../requirements.txt`; Ollama with `qwen3:4b-instruct-2507-q4_K_M`). Run all commands from this folder:
```
powershell -File step1_download.ps1; powershell -File step1b_download_scale.ps1   # MR downloads (GITLAB token in your terminal only)
python exp1_gitlab.py --pool A2000 ; python exp1_gitlab_stats.py --pool A2000 --exclude-pilot A270
python exp2_gitlab_baselines.py meta | generate --arm P0 | generate --arm CB | analyse | gate   # rule: tuning_rule_baselines.md
python score_baselines_correctness.py                                                          # correctness from Clifton's labels
```
- `exp2_gitlab_baselines.py` imports `faithfulness.py` and `gate_eval.py` from `../exp2_django`; that path was fixed for this layout.
- **Never run** `exp2_gitlab_scale.py score` or `build`: they would overwrite labelled sheets.

**Caches to regenerate.** `prs/`, `chunks/` and `emb_cache/` are not in the repo. Rebuild them with the step1 scripts and the first Exp 1 run.

**Which file holds which number.**

| Claim | File |
|---|---|
| Scaled Exp 1: alpha 1 loses gold_in_budget 167 → 155 of 201 (Holm 0.002) | `results/exp1_gitlab_A2000_stats.txt` |
| Unanswerables answered F0 5, P0 13, CB 18 of 18; F0 vs P0 Holm p 0.023 | `results/baselines_counts.csv`, `results/baselines_tests.csv` |
| Correctness: strict F0 30, P0 30, CB 0 of 52 (Clifton's blind labels) | `results/baselines_correctness.md`, `results/baselines_correctness_clifton_*.csv` |
| Post hoc human read of the 36 answered unanswerables | `results/UNANSWERABLE_READ_RESULTS.md`, `results/unanswerable_read_unblinded.csv` |
| Gate on GitLab, and retrieval carry-through | `results/baselines_gate*.csv`, `results/baselines_carry*.csv` |
| Full write-up and decision log | `results/exp2_baselines_report.md`, `results/RUN_LOG.md`, `results/OVERNIGHT_SUMMARY.md` |
| Scaled Exp 2 (provisional labels, 6 Nov) | `exp2_gitlab_A2000/stats.csv`, `report.csv`; `HANDOVER.md` |

**Keys.**
- Included: `results/keys/` (baselines, labels final) and `exp2_gitlab/keys/` (pilot).
- Left out: `exp2_gitlab_A2000/keys/`, because the 87-row F0/C1 sheet is still unlabelled.
