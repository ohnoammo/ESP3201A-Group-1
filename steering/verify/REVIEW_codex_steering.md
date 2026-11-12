# Review of the CODEX_steering build (Claude, 8 Nov 2026)

## Verdict
The Codex build is sound, and I recommend it as **the build James runs**. Claude's own build
(`FOR_JAMES_steering`) becomes the independent checker; it is not sent to James.

**Why the Codex build.** It was tested on a real (small) Hugging Face model on CPU: the hook,
the response mask and the activations all checked out. Claude's build has never run on any model.
It also has stricter safety checks:
- `prepare` must reproduce the shipped files byte for byte;
- the hook call count must equal the number of new tokens;
- the PC is kept awake during long runs;
- a half-written line is cut off on resume.

**One caveat.** By its own note, the "Codex" build was written by Claude in another chat, not by
OpenAI's Codex. Agreement between the two builds therefore guards against coding slips more than
against a shared misreading of the protocol.

## What I checked

| Check | Result |
|---|---|
| Prompts (122) | Identical to Claude's build: same text, same context chunks |
| 70 contexts vs stored `gen_F0.jsonl` | All equal, in both builds |
| Answerables with the answer span in context | 47 of 52 in both builds |
| Pairs (164) | Identical, except q589 cites gold chunk c2 instead of c0; both chunks hold a gold quote |
| Input file hashes | Equal wherever the two builds hash the same file |
| `prepare` re-run on a separate Linux machine | Reproduced all 7 shipped `out/` files exactly |
| Leakage (folds, inner sets, ratio subsets) | No held-out MR used anywhere; ratios exact |
| Codex fake-model pipeline test (26 checks) | Passes here too |
| Hook, mask, layer numbering (code read) | Same meaning as Claude's build: 0-based block outputs, i.e. `hidden_states[L+1]`; the hook adds at the last prompt position and at every generated token |
| McNemar, Holm, J, tie-breaks, degenerate rule | Correct; the McNemar and Holm values were also checked against hand-computed numbers |

## What I changed (none of it changes the protocol; each change is noted in `codex_rule.md`)
1. **preflight VRAM check.** It used to stop the run below 10.5 GiB free. A 12 GB card that also
   drives the Windows desktop can show less than that. It now stops below 9 GiB (the run needs
   about 8.7) and only warns below 10.5.
2. **Blind key.** The key now goes in a separate zip, `codex_steering_KEYS_open_after_labelling.zip`,
   and `out/keys/` is git-ignored. Clifton is the labeller, so he can unzip the results without
   seeing the key.
3. **James's README.** It now mentions the two zips.

The originals are kept in `steer_check\codex_original\`.

## Added
- **`verify_codex_results.py`.** An independent checker for when James's results come back; it
  does not import the Codex code. It recomputes:
  - every outcome from the raw answers;
  - the degenerate flags;
  - the chosen setting per fold;
  - that each test answer used its own fold's setting;
  - the counts, McNemar and Holm;
  - the blind-sheet coverage.

  It passes on the fake-model run and catches deliberately planted errors.
- **`pairs_check_for_Clifton_v2.xlsx`.** The v1 sheet was open on your PC, so it was left untouched.
  The 164 pairs are the same in both versions, so any checks already made in v1 still count. v2 now
  uses the Codex build's folds. It merges both builds'
  automatic flags: 20 rows are yellow, and 3 were flagged by both builds (twin q3239, title q3831,
  title q6695).

## Pair check: done (8 Nov)
- **Clifton checked the 20 flagged pairs** in `pairs_check_for_Clifton_v2.xlsx`: 17 ok, 3 drop
  (twin:q3239, unans:nr3177, unans:nr4460).
- **Claude then scanned all 52 twins for a reworded reason** in the remaining context. Clifton
  dropped the two cases it found (twin:q1189, twin:q1754).
- **Result:** 159 pairs are used. The drops are recorded in `DROPPED_PAIRS` (`codex_steer.py`), in
  `codex_rule.md` and in `out/dropped_pairs.jsonl`.
- **Checks after the drops:** `out/` was rebuilt and re-running `prepare` reproduces it exactly. The
  fake-model test (26/26) and the verifier both pass.
- **Exp 2 caveat for the report:** nr3177 and nr4460 are 2 of the 5 "hallucinated" answers among
  the 18 unanswerables in arm F0. Their `no_reason` labels are doubtful.

## Two things to know before the run

**1. All three ratios push towards "Not found"; none pushes towards answering.** The answer-vs-refuse
balance inside each vector, per fold, is:

| Ratio | Refusal pairs | Grounding pairs (answer vs "Not found") | Net |
|---|---|---|---|
| 40:60 | about 48 | about 36 | about 12 towards refusing |
| 50:50 | about 56 | about 28 | about 28 towards refusing |
| 60:40 | about 54 | about 18 | about 36 towards refusing |

Half of the grounding pairs are about the *content* of the answer (reason vs restated title), not
about answering vs refusing, which is why every ratio leans towards refusal. So the expected
pattern is fewer hallucinated answers on the 18 unanswerables, at the cost of more over-refusal on
the 52 answerables, getting stronger from 40:60 to 60:40. The selection rule (J) weighs both sides,
so it may often pick "no steering". The report should present this as a trade-off and not call it a
failure. A single added vector cannot make refusal depend on whether the evidence is in the context
(Codex's `protocol_issues.md` item 2).

**2. The strength grid may be too weak.** Strengths 0.5, 1 and 2 multiply the raw mean-difference
vector. Because the pairs partly cancel, that vector may be small; in Codex's small-model test, only
strength 4 changed an answer. If all nine settings act like no steering, the run shows nothing.
**Decided 8 Nov:** Clifton added strength 4 to the grid before any run. This is recorded in
`codex_rule.md`, and the fake-model test and the verifier both pass with the 12-setting grid. The
main run now takes about 4 to 7 hours.
