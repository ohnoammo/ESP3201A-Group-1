# steering/verify: independent check of the steering results

This is activation steering. It is **not** RL and **not** fine-tuning.

These files check the steering run independently of the code that produced it.
- The run used the "Codex" build, `codex_steer.py`. That build was written by Claude in a separate chat, not by OpenAI's Codex.
- `verify_codex_results.py` was written separately and does **not** import `codex_steer.py`. It recomputes every result from the raw outputs, using its own code.

## Files
| File | What it is |
|---|---|
| `verify_codex_results.py` | The independent verifier (CPU, standard library plus `exp2_gitlab_scale.auto()` for re-scoring) |
| `REVIEW_codex_steering.md` | Claude's review of the Codex build before the GPU run (8 Nov): what was checked, what was changed, the two protocol changes |
| `pairs_check_for_Clifton_v2.xlsx` | Clifton's human check of the steering pairs: 20 flagged pairs (17 ok, 3 dropped), plus 2 more twin drops found by a scan, so 5 pairs dropped and 159 used |
| `codex_original/` | The Codex build as it was before the review edits, kept for provenance. The edited version is the one that ran. |

## What the verifier checks
1. **Folds, inner sets and ratio subsets:** they cover what they should, no held-out MR leaks into a fold's vector or inner set, and the ratios are exact.
2. **Re-scoring:** every stored response is re-scored from its raw text, and the abstained, answered and overlap-cited flags must match.
3. **Degenerate outputs:** the degenerate rule is recomputed with its own implementation.
4. **Setting selection:** the choice per fold (J, the 10% degenerate drop, tie-breaks) is recomputed and must equal `selection.json`.
5. **Fold use:** every test answer used its own fold's chosen layer and strength, and strength-0 rows equal the baseline.
6. **Statistics:** counts, exact McNemar and Holm are recomputed and must equal `stats.json`.
7. **Blind sheet coverage:** the sheet holds exactly the distinct answered answerable answers. The key is not read.

## Result
On 10 Nov 2026 the verifier ran on James's results (`codex_steering_out`) and printed **ALL CHECKS PASSED**.

Clifton's blind correctness labels (43 correct, 15 partial, 29 wrong of 87) were then used to recompute the correctness figures independently. They match `stats` exactly: strict correct out of 52 was 39 → 39 (40:60), 39 → 31 (50:50) and 39 → 12 (60:40).

## Run it
From the repo root (CPU, about a minute):
```
python steering/verify/verify_codex_results.py --out <path to codex_steering_out> --repo <path to gitlab_runner_copy>
```
It prints `ok` or `FAIL` for each check, then either `ALL CHECKS PASSED` or a list of the checks that failed.
