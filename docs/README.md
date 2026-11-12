# docs: handoff notes and an index of the rule files

These are copies of the project's handoff and handover notes. Each part folder also keeps its own originals. The notes record decisions, status and caveats in date order, and the dates in them are as they were written. Paths such as `claude\…` or `Latest\…` refer to the authors' machines.

## Handoff notes
| File | Covers | Source |
|---|---|---|
| `AI_HANDOFF.md` | Exp 1: project, decisions, status; Exp 2 status as of 6 Nov; the demo app | `ESP3201A_SWE_exp1_app/AI_HANDOFF.md` |
| `exp2_handoff.md`, `exp2_django_HANDOVER.md` | Exp 2 on Django: setup, decisions, state, SymPy and H0 | `ESP3201A_Exp2/` |
| `exp2_gitlab_HANDOVER.md`, `ADVISOR_NOTES.md` | The GitLab Runner validation, scaled Exp 1 and Exp 2 (6 Nov) | `gitlab_runner_copy/` |
| `EXP2_BASELINES_HANDOFF.md` | The Exp 2 baselines P0/CB, correctness, tagging, gate and app (11–12 Nov) | top-level folder, 12 Nov |
| `STEERING_HANDOFF.md`, `STEERING_RESULTS.md` | The activation-steering design (8 Nov) and results (10–11 Nov) | top-level folder, 12 Nov |
| `UPDATE_12Nov.md` | Clifton's 12 Nov update: the unanswerable read, the steering summary and the limits checklist | `FOR_JAMES_update_12Nov/` |
| `presentation/ESP3201A_final_presentation_6Nov.pptx` | The final presentation slides (6 Nov) | `outputs/2026-11-06_final_presentation/` |

## Report figures (`report_figures/`)
| File | Report figure | How it was made |
|---|---|---|
| `fig_exp1_links.png` | Exp 1 links chart (Fig. 2) | `python fig_links.py`. Its values are typed into the script; they equal the mean dense `budget_recall` (test, n = 181) in `../exp1_retrieval/results/swe_exp1_test{,H}_tuned_per_query.csv`, alpha 0 vs the locked alpha. |
| `fig_app_answer.png`, `fig_app_notfound.png`, `fig_app_feedback.png`, `fig_app_supportcheck.png` | App figures 1–4 | Screenshots of `../app` (12 Nov). The captions are in `report_app_section.md`. |
| `report_app_section.md` | The app section text and figure captions, as drafted for the report | – |

## Report and run specification
| File | What it is |
|---|---|
| `ESP3201A_Final_Report_v3.docx` | The final report (v3, 12 Nov). A PDF export, if one is made, goes alongside it. |
| `PROMPT_hybrid_runs_13Nov.md` | The run specification for the 13 Nov hybrid follow-up (Runs 1 and 2). Its rule file is `../exp2_gitlab/tuning_rule_hybrid_13nov.md`. |

The other report figures are in the result folders: `../exp2_gitlab/results/baselines_tradeoff.png`, and `../steering/results_final/steering_tradeoff.png` / `.svg` and `sweep.png`.

## Pre-registered rule files (written before the runs they govern)
| File | Governs |
|---|---|
| `../exp1_retrieval/README.md` ("Selection rule"), `select_chunking.py` | Exp 1 chunk and alpha selection on dev |
| `../exp2_django/tuning_rule_dev2.md` | Exp 2 relation-factor alpha on dev2 |
| `../exp2_django/tuning_rule_gate.md` | The faithfulness gate (threshold 0.5; see the P1 timing note) |
| `../exp2_django/tuning_rule_correctness.md` | Correctness tests and agreement |
| `../exp2_django/tuning_rule_wholepr.md` | Arm W-F (exploratory) |
| `../exp2_django/tuning_rule_hybrid.md`, `tuning_rule_hybrid_limit.md` | Arm H0 and its limit test |
| `../exp2_django/tuning_rule_hallucination_test.md` | A draft that was never committed and never run |
| `../exp2_django/tuning_rule_sympy_h0.md` | H0 on SymPy |
| `../exp2_gitlab/tuning_rule_exp1_scale.md`, `tuning_rule_exp2_scale.md` | Scaled Exp 1 and Exp 2 on GitLab Runner |
| `../exp2_gitlab/tuning_rule_baselines.md` | The baselines P0/CB, gate and carry-through |
| `../steering/codex_rule.md` | Activation steering (protocol plus dated change notes) |
