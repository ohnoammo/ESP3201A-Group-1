# Update for James (Clifton, Thu 12 Nov 2026, evening)

The report is due **Fri 13 Nov, 12:00**. This is everything since your baselines bundle.

## 1. What's in this zip
| Path | Goes in the repo at | What it is |
|---|---|---|
| `steering/verify/` | `steering/verify/`, as a later commit | The independent check of the steering results you asked for: `verify_codex_results.py`, its README, Claude's pre-run review, Clifton's pair-check sheet and the pre-review Codex originals |
| `exp2_baselines/UNANSWERABLE_READ_RESULTS.md` + `unanswerable_read_unblinded.csv` | `results/`, next to `exp2_baselines_report.md` | Clifton's blind read of the 36 answered unanswerables (file 1). Included in case you don't have it yet |

The steering README can now say that the verification script is in `steering/verify/` and passed every check on 10 Nov.

## 2. Baselines correctness sheet (file 2): done, waiting on you
- Clifton labelled all 147 answers and double-checked them. You already have **`FOR_JAMES_baselines_labels.zip`**.
- **Your part (5 min, CPU):** follow its README.
  - Copy the files in.
  - Commit.
  - Run `python score_baselines_labels.py`.
  - Commit.
- **Send back:** the 4 `results/baselines_correctness*` files and `results/keys/baselines_blind_key.json`. The labels are final, so the key can be shared now, and Claude will cross-check your numbers.
- **Labels overall:** 60 correct, 32 partial, 55 wrong. Per arm is unknown until you unblind.
- **Rule used:**
  - **correct:** the full gold reason, with every claim true. Extra detail is fine if true.
  - **partial:** the reason is there, but there is a false, misleading or self-contradictory claim, or half of a two-part reason is missing.
  - **wrong:** a different or invented reason, denying the premise, or no reason.
- **For the methods section:** say how the labels were made. Clifton labelled them, with suggestions drafted by Claude that he checked row by row.

## 3. Read of the unanswerables (file 1): done
- **Not a rescore.** The pre-registered result stands: F0 5, P0 13, CB 18 of 18 answered; F0 vs P0 Holm p 0.023.
- **The human read (post hoc).** Confident false claims are invented reason + what-as-why + premise denial:
  - F0 **3**, P0 **8**, CB **18** of 18;
  - F0 vs P0: 1/6, p 0.125, not significant;
  - F0 vs CB: 0/15, p 0.0001.
- **Story:**
  - Grounding vs closed-book is robust.
  - Grounding vs plain RAG goes the same way, but isn't significant after the read.
  - **Premise denial is plain RAG's failure mode:** 4 of P0's 13, none of F0's. Given context, P0 "corrects" the user with a fact from a neighbouring MR.
- **Labels to add to the limits section:** nr1372 and nr1781, next to nr3177 and nr4460. P0 answered them from the MR text, so their no_reason labels are doubtful too.

## 4. One decision: F0's correctness numbers
- **The current situation.** Your baselines report's F0 correctness (33/52, and the gate and carry-through tables) uses the old provisional labels: your 20 rows plus Codex's 67, with Alyssa's review still pending. The new sheet re-labels F0 under one rule, by one labeller, alongside P0 and CB.
- **Proposal:**
  - Make the new sheet F0's main correctness number.
  - Mention the old 33/52 only as an earlier provisional figure.
  - Skip Alyssa's 87-row review unless it's already done.
- Once your results and the key arrive, Claude can recompute the gate and carry-through correctness with the new labels (about 15 min). Say if you'd rather keep the old ones.

## 5. Steering: status unchanged, all final
These figures are already in `claude/STEERING_RESULTS.md` and `steering_results_final.zip`.
- **Settings chosen:**
  - 40:60 was never chosen (identical to unsteered);
  - 50:50 steered 1 of 5 folds;
  - 60:40 steered 4 of 5 folds.
- **Pre-registered results (Holm, family of 9):**

| Ratio | Unanswerables answered /18 | Answerables answered /52 | Overlap-cited /52 |
|---|---|---|---|
| unsteered | 7 | 48 | 45 |
| 60:40 | 6 (Holm 1) | 43 (Holm 0.44) | 17 (Holm < 0.001) |

- **Correctness (strict, out of 52):**
  - 39 → 31 at 50:50 (p 0.008);
  - 39 → 12 at 60:40 (p < 1e-7).
- **Post hoc, with paraphrased refusals counted as refusals:** at 60:40, unanswerables answered 7 → 3 (p 0.125) and answerables answered 48 → 38.
- **Story:**
  - It's a trade-off: fewer hallucinations, more over-refusal.
  - The vector is one answer↔refuse axis (cosine of the refusal and grounding parts about −0.8 to −0.9).
  - The unsteered model is best on correctness.
  - Call it activation steering, never RL or fine-tuning.
- **Figure:** `steering_tradeoff.png` / `.svg`.

## 6. Remaining steps
| # | Step | Who | Time |
|---|---|---|---|
| 1 | Run the baselines scorer and send back the results + key | James | 10 min, tonight |
| 2 | Cross-check, write the correctness table and paragraph, and redo the gate/carry tables if agreed | Claude, with Clifton | 30–45 min after step 1 |
| 3 | Steering and Exp 2 baselines report sections, with limits | Clifton + Claude | 2–3 h, tonight |
| 4 | Assemble the full report: Exp 1, Exp 2, transfer checks, steering, figures, limits | All | 3–4 h, tonight |
| 5 | GitHub repo: clean-up, READMEs, push; `steering/verify/` as a later commit | James | 1–2 h, tonight / Fri early |
| 6 | Proofread, check every number against its file, submit | All | Fri morning, **done by 11:00** |

## 7. Limits section checklist (collected so far)
- **Doubtful no_reason labels:** nr3177, nr4460, nr1372, nr1781.
- **Refusal regexes are imperfect.** Lenient misses free-form refusals. The broad sensitivity version was written after seeing F0.
- **Truncation:** P0 and CB answers were often cut off at 512 tokens (30/70 and 45/70).
- **The gate:** it measures citation support, not truth, and it gates every uncited answer.
- **Blinding is imperfect:** answer style hints at the arm (premise denials are mostly CB), and some rows keep empty `()` left behind by removed citations.
- **Single seed (42), temperature 0, n = 18 unanswerables:** low power.
- **Question checks:** done by Codex and DeepSeek passes plus James on some rows, not by both people as first planned.
- **Steering:** exploratory, on the transfer set. A single vector can't make refusal depend on whether the evidence is present.
- **Correctness labels:** say how they were made (section 2).
