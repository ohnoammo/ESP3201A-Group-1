# Activation steering: results (10 Nov 2026, 00:50 SGT; sweep analysis added 11 Nov)
 
Read `claude/STEERING_HANDOFF.md` first for the design. This file records the results.
 
## Status
- **Run.** James ran setup, main and the sweep with no errors. The results are in `Latest\codex_steering_out\`; that folder, not `CODEX_steering\out`, is the folder of record.
- **Verification.** Claude's independent `steer_check\verify_codex_results.py` passes every check: folds and leakage, re-scoring, degenerate flags, selection, fold use, McNemar and Holm, and blind-sheet coverage.
- **Labels.** Clifton labelled all 87 blind answers in `blind_sheet_for_Clifton.xlsx`, then converted to `blind_sheet_labels.csv`: 43 correct, 15 partial, 29 wrong.
- **Key and stats.** The key was opened only after labelling (`keys\blind_key.json`). `stats` and `report` were re-run with the labels, and Claude recomputed the correctness figures independently: they match exactly.
## Selected settings (inner J, training MRs only)
- **40:60:** every fold chose no steering, so its results are identical to the unsteered model's.
- **50:50:** steered in 1 of 5 folds (L20, x4).
- **60:40:** steered in 4 of 5 folds (L20, x2 or x4).
- **Vector norms:** about 0.08 to 0.27 of the typical residual norm.
- **Pipeline check:** HF and Ollama agree on answer vs refuse for 63/70 (kappa 0.746).
## Pre-registered tests (exact McNemar vs unsteered HF, one Holm family of 9)
 
| Ratio | Unanswerables answered /18 | Answerables answered /52 | Overlap-cited /52 |
|---|---|---|---|
| unsteered | 7 | 48 | 45 |
| 40:60 | 7 (p 1) | 48 (p 1) | 45 (p 1) |
| 50:50 | 5 (2/0, Holm 1) | 44 (4/0, Holm 0.75) | 37 (8/0, Holm 0.0625) |
| 60:40 | 6 (1/0, Holm 1) | 43 (5/0, Holm 0.44) | 17 (28/0, Holm < 0.001) |
 
## Correctness (secondary, Clifton's blind labels, exact McNemar, unadjusted; out of 52)
 
| Ratio | Strict: unsteered → steered | Lenient: unsteered → steered |
|---|---|---|
| 40:60 | 39 → 39 | 47 → 47 |
| 50:50 | 39 → 31 (8/0, p 0.008) | 47 → 38 (9/0, p 0.004) |
| 60:40 | 39 → 12 (27/0, p < 1e-7) | 47 → 20 (27/0, p < 1e-7) |
 
## Post hoc (`posthoc_paraphrased_refusals.md`; must be labelled post hoc in the report)
 
Steered models often refuse in their own words ("The excerpts do not state the reason…"). The strict Exp 2 scorer only recognises the exact "Not found in the provided PRs", so it counts these as answers. Re-scored with paraphrased refusals counted as refusals:
 
| Ratio | Unanswerables answered /18 | Answerables answered /52 |
|---|---|---|
| 50:50 | 7 → 5 (2/0, p 0.5) | 48 → 41 (7/0, p 0.016) |
| 60:40 | 7 → 3 (4/0, p 0.125) | 48 → 38 (10/0, p 0.002) |
 
## Sweep (descriptive, all 70, each question with its own fold's vector; paraphrased refusals counted as refusals; analysed 11 Nov)
 
**One axis.** In `vector_info.json`, the cosine between the refusal part and the grounding part of each vector is about −0.77 to −0.90. Both families push along nearly the same "answer vs refuse" axis, in opposite directions. So the ratio mostly sets how far a vector points along that one axis, and ratio and strength largely trade off against each other. 40:60 nearly cancels: even at x4 it barely moves anything.
 
Notable settings (unanswerables answered /18, answerables answered /52, overlap-cited /52):
 
| Setting | Unanswerables answered | Answerables answered | Overlap-cited |
|---|---|---|---|
| unsteered | 7 | 48 | 45 |
| 50:50 L20 x2 | 5 | 45 | 42 |
| 60:40 L25 x2 | 3 | 39 | 26 |
| 60:40 L20 x2 | 1 | 32 | 26 |
| 50:50 L20 x4 | 2 | 20 | 1 |
| 60:40 L25 x4 | 14 | 46 | 0 (25 degenerate) |
 
No setting reduces hallucination without losing answers. Every point lies on a trade-off curve. Strong settings (x4) also break citations and produce degenerate output.
 
**Other ratios (asked by James, 11 Nov): not worth running before Fri.** Because the vector is essentially one axis, 20:80 or 0:100 would push towards answering, giving more hallucination. 80:20 or 100:0 would act like 60:40 at a higher strength, which the sweep already covers. They would add 3–5 h of GPU time per ratio plus more blind labelling.
 
## Story for the report
- **The trade-off.** Steering trades more over-refusal for fewer hallucinations, and the effect grows with the refusal share. 40:60 is never selected; 60:40 roughly halves hallucinated answers, but costs 10 refusals of questions that have an answer and 27 correct answers.
- **Broken outputs.** Steering also produces some: truncated "The provided PRs" answers, and one repeating loop.
- **Why the trade-off is expected.** One added vector cannot make refusal depend on whether the evidence is present. The refusal and grounding parts point in nearly opposite directions (cosine about −0.9), so the vector is one answer–refuse axis.
- **No significant effect on hallucination.** With n = 18, a significant result needs a split of about 7 to 0.
- **Doubtful labels.** nr3177 and nr4460 are 2 of the unsteered model's 7 answered unanswerables, and their no_reason labels are doubtful.
- **Overall.** The unsteered model is best on correctness.
- **Framing.** Call it activation steering, never RL or fine-tuning.
## Next
Steering section of the report (method, results, limits), then the full report and GitHub repository, due Fri 13 Nov 2026, 12:00.