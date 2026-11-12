# Handoff: activation-steering experiment (state as of Sun 8 Nov 2026, 21:40 SGT)
 
You are continuing as Clifton's advisor on NUS ESP3201A Group 1 (Clifton Liu Ziheng, Alyssa Chua, James Kwek Tze Xuan). The project is a local, offline RAG assistant that answers "why was this code changed?" from PRs/MRs. Django is the main repo; SymPy and GitLab Runner are transfer checks. The report and GitHub link are due **Fri 13 Nov 2026**. Clifton is carrying the main work. Runs happen on James's laptop (RTX 5070 12 GB, Windows); verification is done by Claude. Read `claude/AI_HANDOFF.md` for the earlier project history.
 
## What the experiment is
- **Why it exists.** After the 6 Nov final presentation, the professors asked for "reinforcement learning of weight distribution in the human-checked 70 PRs", plus a ratio of grounded vs hallucination examples. They also noted that Exp 2 involved **no learning**: the hand-checked data only validated the judge. The report must say this.
- **Clifton's decisions.**
  - Method: **activation steering** (contrastive activation addition). It changes no weights, so it must never be called RL or fine-tuning.
  - Validation: 5-fold cross-validation.
  - Ratios of refusal : grounding pairs: **40:60, 50:50, 60:40**.
- **Data.** The 70 GitLab Runner questions in `exp2_gitlab_A2000` (52 answerable, 8 no_reason, 10 removed), with arm F0 contexts. Labels are provisional: the question check was mostly automated, and kappa was 0.177.
- **Model and settings.**
  - HF `Qwen/Qwen3-4B-Instruct-2507`, bf16, greedy decoding. The baseline is the same HF model without steering.
  - Layers {14, 20, 25}; strengths {0.5, 1, 2, **4**} plus 0. Strength 4 was added by Clifton on 8 Nov, before any run.
  - Setting chosen per fold on training MRs only: J = refusal rate on unanswerables + answer rate on answerables − 1, dropping any setting with more than 10% degenerate answers.
- **Tests.** Exact McNemar, steered vs baseline, in one Holm family of 9 (3 ratios × 3 outcomes): unanswerable answered /18 (primary), answered /52, overlap-cited /52.
  - Secondary: blind correctness, labelled by Clifton (strict and lenient, unadjusted).
  - Optional sweep: descriptive only.
## The build James is running: `Latest\CODEX_steering\`
Zipped as `Latest\FOR_JAMES_CODEX_steering.zip`. Its files: `codex_steer.py`, `run_codex.ps1`, `README_CODEX_FOR_JAMES.md`, `codex_rule.md` (protocol plus dated change notes), `design_choices.md`, `protocol_issues.md`, `out\` (prepared inputs) and `human_check\` (Clifton's pair check).
 
**Provenance.** It was written by "Codex", which in fact was Claude in another chat, from `Latest\CODEX_README.md`. Claude reviewed it against its own separate build (`Latest\FOR_JAMES_steering\`, marked DO NOT SEND, kept for cross-checking).
- The two builds produce identical prompts (122), contexts (all 70 equal `gen_F0.jsonl`) and pairs.
- A re-run of prepare reproduces `out\` exactly.
- The fake-model test passes 26/26.
**Claude's fixes.**
- The VRAM stop threshold is now 9 GiB, with a warning below 10.5.
- The blind key is packed in a separate zip.
- `out/keys` is git-ignored.
- Strength 4 was added.
- 5 pairs were dropped.
**Pair check.**
- Clifton checked 20 flagged pairs in `steer_check\pairs_check_for_Clifton_v2.xlsx`.
- Claude scanned all 52 twins.
- The 5 dropped pairs: twin:q3239, twin:q1189, twin:q1754, unans:nr3177, unans:nr4460.
- 159 pairs remain. They are recorded in `DROPPED_PAIRS` in the code and in `out/dropped_pairs.jsonl`.
**Report caveat.** nr3177 and nr4460 are 2 of Exp 2 F0's 5/18 "hallucinations". Their no_reason labels are doubtful: the model's answers were grounded. The true count may be 3/18. This goes in the limits section.
 
## Status now
- James is running it (8 Nov evening). Setup takes ~15 min; main takes ~4–7 h; the sweep is optional (~2–4 h).
- When main finishes, James sends two zips: `codex_steering_out.zip` and `codex_steering_KEYS_open_after_labelling.zip`.
- If setup prints STOP or FAIL, he sends `codex_steering\out\logs\`.
## Next steps
1. **Check James's results.**
   - Unzip the out zip into `Latest\CODEX_steering\out` (NOT the keys zip).
   - Run `python Latest\steer_check\verify_codex_results.py --out <...\CODEX_steering\out> --repo "<...\Latest\TX addtions\TX addtions\gitlab_runner_copy>"`.
   - The checker is independent of the Codex code. It recomputes outcomes, degenerate flags, selection, fold use, McNemar/Holm and blind-sheet coverage, and checks that no dropped pair was used.
   - Also read `out\codex_report.md` and `vector_info.json`: the vector norm vs the residual norm, and the HF vs Ollama agreement.
2. **Clifton labels** `out\blind_sheet_blank.csv` into `out\blind_sheet_labels.csv` (correct / partial / wrong). Only then unzip the keys zip into `out\`, then run `run_codex.ps1 -Stage after-labels` (or `codex_steer.py stats`, then `report`) on CPU.
3. **Report sections.**
   - Steering method, written honestly: not RL, the professors' request, and the ratio as a pair mix.
   - Results: expect a trade-off. All three ratios lean toward refusal, because half of the grounding pairs are why-vs-what, not answer-vs-refuse. A single added vector cannot make refusal depend on the evidence.
   - Limits: 70 questions from 1 repo, provisional labels, synthetic rejected answers, Claude-written gold answers, one seed, HF bf16 rather than Ollama q4, 18 unanswerables so low power, and the doubtful no_reason labels.
4. GitHub repository and the rest of the report. James's latest `ESP3201A_Exp2` folder (with the H0 arm) is still needed.
## Standing rules
- Never edit Exp 1 files.
- Never run `exp2_gitlab_scale.py score` or `build`.
- Commit before runs in James's repo.
- Labels are made by humans; never write label files.
- Labellers don't open `keys` before their labels are final.
- Tokens are set in the terminal only, never in files or chat.
- Latest folder: `C:\Users\liuzh\OneDrive\Desktop\NUS Y4S1\ESP3201A Machine Learning in Engineering Science\RAG Project\Latest`.