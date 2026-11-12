# Scaled Exp 1 on gitlab-runner: rule set before the run

Written 5 Nov 2026, after seeing the 30-task pilot and before downloading or running the scaled pool.

- **Design:** 231 tasks + 2,000 distractors (pool `A2000`), the size of the Django pool. Tasks and distractors follow the same fixed SHA-256 order, filters and adapter as the pilot.
- **Settings, unchanged:** dense Qwen3-Embedding-0.6B, Exp 1's instruction, fixed 512/77, 2,560 budget, alpha 0 vs alpha 1.
- **Labels:** an MR's closing reference to an earlier public issue. These differ from SWE-bench, so results are not compared with Django as if like for like.
- **Primary set:** the tasks not in the pilot, because the pilot suggested looking at precision. All tasks are a sensitivity check.
- **Tests:** one Holm family of 4, alpha 1 vs alpha 0. `gold_in_budget` by exact McNemar; budget recall, precision and F1 by paired permutation (10,000 sign flips, seed 0). `exp1_gitlab_stats.py`.
- **Sensitivity:** Wilcoxon signed-rank in place of the permutation test, with its own Holm family. Added 5 Nov, before any scaled result, because the two tests disagree on the pilot (precision Holm 0.138 by permutation, 0.029 by Wilcoxon).
- **Primary test confirmed (James, 5 Nov, before any scaled result):** permutation stays primary because Exp 1's `stats.py` uses it for MRR, not because the pilot favoured it. Both tests are reported either way.
- **No Hit@5 or MRR test:** links do not change the ranking, so these are the same at both alphas.
- **Status:** exploratory transfer check, not in the Exp 2 Findings. No settings are tuned on this set.
