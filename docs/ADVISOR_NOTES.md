# Advisor notes — GitLab Runner validation (Exp 1 + Exp 2)

Independent verification notes from Claude (acting as advisor to the Claude Code
session doing the work). Companion to `HANDOVER.md`, which Claude Code owns and
is the source of truth on provenance and state. This file is my own running
record: what I checked, what I caught, and what I'd flag if someone else picked
this project up.

## Role

Read Claude Code's reports, independently re-verified claims against the actual
files on James's machine (via device bridge, not by trusting pasted summaries),
caught errors and overclaims, drafted prompts for James to relay back. Did not
write or run any of the project's own code.

## Verification log

### Exp 1 (scaled, pool A2000)
- Reviewed Claude Code's scaled Exp 1 results report. No independent code-level
  check performed beyond reading the report; flagged nothing.

### `cmd_gate` bug (pilot `exp2_gitlab.py`)
- Confirmed by direct code comparison: the pilot script's `cmd_gate` called
  `pack()` without `alpha`/`links`, silently defaulting and breaking context
  reconstruction for the C1 (alpha=1) arm.
- Confirmed the fix in `exp2_gitlab_scale.py` (`alpha = ARM_ALPHA[arm]`, built
  `links`) is correct.

### Correctness-sheet reconciliation (pilot)
- Verified directly: S005 restore, S010 overwrite (wrong → partial, Alyssa as
  reference rater), nr188 exclusion/resolution were applied correctly to
  `correctness_sheet_reconciled.csv` / `correctness_sheet.csv`.

### `q2913` false "drop" (Codex)
- Codex recommended dropping `q2913`, claiming the gold quote wasn't on the MR.
- James manually read the MR; the quote exists verbatim, posted by the MR's own
  author during active review.
- Root cause: Codex, like my own WebFetch, cannot see GitLab's JS-rendered
  comment/discussion threads, only static page content. This is a standing
  blind spot for both of us, not a one-off.
- Resolution: kept `q2913` as `ok`, note added to the sheet so it isn't
  re-flagged.

### `nr6848`→`q6848`, `nr5853`→`q5853` reclassification
- James manually read both MRs' full descriptions. Reason for routing
  (`normalizeExitError` / consistency with existing pattern) is stated in the
  description text, matching the house convention already used in the pilot
  (the uid:gid "for consistency with Docker executor options" precedent).
- Reclassified `no_reason` → `answerable` in `questions_src.json` /
  `questions.jsonl`. Verified the sheet rows now match.

### Scaled-70 question check (Codex / DeepSeek / James)
- Verified `question_check_sheet_codex.csv` and `question_check_sheet_deepseek.csv`
  directly: `q2913` and `q6848` rows matched Claude Code's claims about which
  cells were filled/blank.
- Both AI checkers share the JS-rendered-thread blind spot; DeepSeek flagged
  this itself on `q3137`, `q2913`, `q589` (its "ok" there doesn't confirm the
  quote).

### Correctness labelling, 87 rows, Alyssa unavailable
- Confirmed via the 10-row James/Codex disagreement table that my recommended
  resolutions were applied as given: changed on S060, S047, S070, S082, S013;
  kept on S048, S022, S038, S030, S049.
- Verified Codex's 67-row pass was genuinely blind: no tool/file access (its
  commands were blocked by policy; James pasted the rows + rules instead), no
  arm information. Confirmed via `correctness_sheet_codex_67.csv`.
- Verified `exp2_scale_stats.py` now reads `correctness_sheet.csv` as `FINAL`
  and the agreement line compares James's/Codex's original 20-row sheets, not
  `FINAL` against itself.

### Final stats run (6 Nov)
- Re-derived the headline numbers independently from `stats.csv`, `report.csv`,
  `gate_F0.jsonl`, `gate_C1.jsonl` rather than trusting the pasted summary.
  All matched: strict correct 33/32 (n=52, p=1.0), answered 43/44 (p=1.0),
  unanswerable answered 5/3 (n=18, p=0.5), lenient 40/41 (p=1.0), Holm 1.0
  throughout.
- Checked `gated_unanswerable_answered` (F0=2, C1=1) against the raw gate
  files and initially misread it as "rows the gate removed" rather than "rows
  still answered after the gate" — flagged a non-issue. Claude Code corrected
  me with the exact row accounting (F0: 5 total, 3 gated out, 2 remain; C1: 3
  total, 2 gated out, 1 remains). Confirmed correct; no file change needed.
- Confirmed `HANDOVER.md`'s provisional-labelling note is accurate: states
  plainly that the signed "Alyssa labels everything, hers is final" rule did
  not happen, names the actual substitute (James's 20 + Codex's 67), and
  already includes a robustness check I would otherwise have asked for
  (Codex-only labels on all 87 rows: strict correct 36/33, p=0.453, still not
  significant).

## What I'd flag to anyone relying on these results

1. **No significant difference, F0 vs C1, on any pre-registered test** —
   McNemar, Holm-corrected, all p=1.0. This is the headline, but a
   non-significant result does not show the arms are equivalent.
2. **Correctness labelling is provisional.** Alyssa (the signed reference
   rater) never labelled; substitute is James (20 rows, resolved against
   Codex) + Codex (67 rows, blind). If/when Alyssa reviews and her labels
   differ meaningfully, re-run stats on her labels before treating this as
   final.
3. **Rater agreement was poor**: kappa 0.177 on the 20 overlapping rows.
   Codex marked 56/67 of its rows correct; James marked 6/20 correct on a
   different sample. Large base-rate gap between raters.
4. **Raters are mixed within pairs**: of the 43 questions both arms answered,
   12 have one arm labelled by James and the other by Codex. 6 of the 9 strict
   discordant pairs fall in that group (split 3/3 by arm), so some of the
   "disagreement" could be rater identity rather than arm. The Codex-only
   recount (p=0.453) partly addresses this but isn't definitive.
5. **Codex's two passes weren't equally rigorous.** On the original 20-row
   second-opinion pass it apparently had MR access (caught things like the
   Docker-mount contradiction on S013, cited MinGit on S049 — detail not in
   the gold quotes). On the 67-row blind pass it was deliberately restricted
   to gold quotes + `LABELLING.txt` only. So the 67 rows can't catch the kind
   of MR-contradiction error that made S013 wrong; strict-correct on those 67
   may be a touch too generous.
6. **This whole exploratory arm (GitLab Runner) is outside Exp 2's official
   findings**, per the original hard rule — a validation/robustness check on
   the Django-based Exp 2 pipeline, not a replacement result.

## Open items (as of 6 Nov, 04:14 SGT)

- Alyssa's full 87-row review, still outstanding, still the officially
  "correct" step per the signed rule.
- `question_check_sheet.csv`'s OneDrive copy was locked by Excel; waiting on
  James to close it so Claude Code can copy the current version over.
