# transfer_sympy: SymPy transfer check (Clifton; Exp 1 and Exp 2 on a second GitHub project)

**What it is.** The code and results from Clifton's `ESP3201A_SWE_exp1_sympy.zip` (5 Nov 2026), with the 1.6 GB of caches left out. Django's final settings are applied unchanged to `sympy/sympy`. This was decided before any SymPy result. It is **exploratory**: counts only, no SymPy comparison tested, and no arm ranked on it.

**Research questions served.**
- **RQ1:** Exp 1, with 75 SWE-bench Verified tasks plus 2,000 other PRs.
- **RQ2:** Exp 2, the 4B on prompt v3 with arms F0 and S0-G, on 15 answerable and 7 unanswerable hand-checked questions.

**Differences from Django** (see `START_HERE.md`):
- `pr_document.py` drops `sympy-bot` and HTML comments in descriptions.
- The same-ticket filter also reads "Fixes #N".
- There is no pool H.

**Run** (PowerShell, from this folder; Python 3.12; `pip install -r requirements.txt`):
```
powershell -ExecutionPolicy Bypass -File .\step1_download.ps1      # PRs + pool (GitHub token in your terminal only)
powershell -ExecutionPolicy Bypass -File .\step2_exp1_runs.ps1     # Exp 1 tuned run + stats (GPU)
powershell -ExecutionPolicy Bypass -File .\step4_exp2_run.ps1      # Exp 2 F0 / S0-G (GPU, Ollama)
powershell -ExecutionPolicy Bypass -File .\step2b_exp1_untuned.ps1 # untuned run + stats
powershell -ExecutionPolicy Bypass -File .\step5_exp2_finish.ps1   # after labelling: gate + report
```

**Caches to regenerate.** `prs/`, `chunks/`, `emb_cache/` and `qdrant_exp1/` are rebuilt by steps 1 and 2.

**Which file holds which number.**

| Claim | File |
|---|---|
| Exp 1 on SymPy, tuned vs untuned, with CIs | `results/stats_sympy_full.txt`, `results/swe_exp1_sympy_{tuned,untuned}*.csv` |
| Exp 2 on SymPy: F0 answered 10/15 and unanswerables answered 4/7; S0-G 14/15 and 5/7 | `exp2_sympy/summary.csv`, `exp2_sympy/report.csv` |
| Correctness labels (Alyssa, James, merged) | `exp2_sympy/correctness_sheet_*.csv`, `LABEL_MERGE_RULE.txt` |
| Import check and section 8 of the Django tables | `../exp2_django/results/sympy/` (`MANIFEST.json`), `../exp2_django/results/sympy_transfer.csv` |
| Arm H0 on SymPy | `../exp2_django/results/sympy_h0/summary.csv`, `../exp2_django/tuning_rule_sympy_h0.md` |

**Key.** `exp2_sympy/keys/sheet_key.json` is included, because the labels are final.
