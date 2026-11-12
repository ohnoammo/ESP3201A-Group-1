# For James: score the baselines correctness sheet (about 5 minutes, CPU only)

Clifton has labelled all 147 answers on the blind sheet, and the labels are final (12 Nov 2026). The key has not been opened.

This zip holds:
- `baselines_blind_sheet_labels.xlsx`: Clifton's labelled sheet, in the format you sent him.
- `baselines_blind_sheet_labels.csv`: the same labels in the blank sheet's CSV format (same 7 columns and order). This is the file the script reads.
- `score_baselines_labels.py`: the scorer. Your `exp2_gitlab_baselines.py` has no command for this, so this script fills the gap. It uses the standard library only.

## Steps (PowerShell, in `gitlab_runner_copy`, branch `exp2-baselines`)

1. **Copy files into place:**
   - `baselines_blind_sheet_labels.csv` (and the `.xlsx`, for the record) go into `results\`, next to `baselines_blind_sheet_blank.csv`.
   - `score_baselines_labels.py` goes into the repo root, next to `exp2_gitlab_baselines.py`.
   - **Don't open the CSV in Excel and save it.** The script checks the file's hash and stops if it changed.
2. **Commit before running:**
   ```
   git add results/baselines_blind_sheet_labels.csv results/baselines_blind_sheet_labels.xlsx score_baselines_labels.py
   git commit -m "baselines: final correctness labels + scorer, before unblinding"
   ```
3. **Run:**
   ```
   python score_baselines_labels.py
   ```
   This takes a few seconds. It opens `results\keys\baselines_blind_key.json`, which is fine now that the labels are final. It prints a table and writes:
   - `results\baselines_correctness.md`
   - `results\baselines_correctness_per_arm.csv`
   - `results\baselines_correctness_tests.csv`
   - `results\baselines_correctness_rows.csv`
4. **Commit the outputs:**
   ```
   git add results/baselines_correctness*
   git commit -m "baselines: correctness unblinded"
   ```
5. **Send Clifton these 5 files:**
   - the 4 outputs above;
   - `results\keys\baselines_blind_key.json`, so that Claude can cross-check the numbers independently.

## What it computes (pre-registered in the brief)
- **Per arm (F0, P0, CB):**
  - strict correct (label = correct) out of 52;
  - lenient correct (correct + partial) out of 52.
- **How refusals count:** an answer the arm refused (so it isn't on the sheet) counts as not correct.
- **Tests:** exact McNemar, two-sided, **unadjusted**, F0 vs P0 and F0 vs CB, for both strict and lenient scoring.
- **Optional extra:** F0's new labels compared with the provisional ones from `correctness_sheet.csv`, via your `f0_labels()`. If that import fails, the script skips this part and says so.

## Checks it runs (it stops if one fails)
- The labels file hash equals the approved one (`e33bb8a0…`).
- The labels file has 147 rows and lines up with the blank sheet: same ids, questions and answers.
- The key has the same 147 ids.
- Every key entry's question matches its row.
- No arm has two rows for one question.
- **Expected answer counts per arm:** F0 43, P0 52, CB 52. If a count differs, the script prints a warning instead of stopping.

If anything stops with red text, send Clifton a screenshot. Don't edit the labels.
