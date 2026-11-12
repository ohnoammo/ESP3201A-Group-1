# steering: activation steering on the GitLab Runner 70 (exploratory)

**What it is.** It adds contrastive activation vectors inside the frozen `Qwen/Qwen3-4B-Instruct-2507` (HF, bf16, greedy decoding). **No weights change, so this is not RL and not fine-tuning.** The professors asked for it after the 6 Nov presentation. It serves **RQ3**: can steering cut hallucination without losing correct answers?

**Design** (pre-registered in `codex_rule.md`, with the design in `../docs/STEERING_HANDOFF.md`):
- Ratios of refusal to grounding pairs: 40:60, 50:50 and 60:40, with 5-fold cross-validation over the 70 questions.
- Layers {14, 20, 25} and strengths {0.5, 1, 2, 4}. The setting for each fold is chosen on training MRs only.
- Tests: exact McNemar against the unsteered model, in one Holm family of 9.
- Secondary: Clifton's blind correctness labels.

**Folders.**

| Path | Contents |
|---|---|
| `codex_steer.py`, `run_codex.ps1`, `codex_rule.md`, `design_choices.md`, `protocol_issues.md`, `tests/` | The build that ran. Run instructions are in `README_CODEX_FOR_JAMES.md`. |
| `out/` | The prepared inputs (prompts, pairs, folds). The run checks that it reproduces them byte for byte. |
| `human_check/` | Clifton's pair check |
| `results_final/` | Final outputs from 10 Nov: `gen_*.jsonl`, `selection.json`, `stats*.{json,csv}`, `codex_report.md`, `STEERING_RESULTS.md`, `blind_sheet_labels.csv`, `keys/blind_key.json` (opened after labelling), and `vectors.npz` (the steering vectors, from `ESP3201A_local`) |
| `verify/` | An independent verifier (`verify_codex_results.py`). It passed every check on 10 Nov. |

**Run.** Use a GPU with at least 10 GB and a CUDA build of torch, plus `transformers`. The script finds the Exp 2 code through `--repo`, which in this layout is `../exp2_gitlab`:
```
python steering/codex_steer.py --repo exp2_gitlab <stage>         # stages: see README_CODEX_FOR_JAMES.md
python steering/verify/verify_codex_results.py --out "$PWD/steering/results_final" --repo "$PWD/exp2_gitlab"   # absolute paths: the verifier changes into --repo first
```

**Caches.** `out/acts/` holds per-question activations (about 11 MB). It is git-ignored and rebuilt by the vectors stage. The model downloads from Hugging Face on first use (about 8 GB).

**Which file holds which number.**
- **Pre-registered tests, unanswerables answered out of 18:** unsteered 7, 50:50 5, 60:40 6, all Holm 1. File: `results_final/stats_tests.csv`.
- **Correctness, strict, out of 52:** 39 → 31 at 50:50 and 39 → 12 at 60:40. File: `results_final/codex_report.md`.
- **Post hoc, paraphrased refusals counted:** file `results_final/posthoc_paraphrased_refusals.md`.
- **Trade-off figure:** `results_final/steering_tradeoff.png` / `.svg` and `sweep.png`.

**Token note.** `prompts.jsonl` (in `out/` and `results_final/`) contains verbatim excerpts of public GitLab Runner MRs, including example and test-fixture runner tokens from those MRs (e.g. `helpers/shorten_token_test.go` in !5270/!5580/!7018, and the GDK example in !3910). They are not project credentials.
