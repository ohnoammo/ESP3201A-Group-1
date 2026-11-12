# SymPy test: start here

This folder tests our system on a second project, SymPy, with the settings we chose on Django,
unchanged. It is a separate copy, so nothing in the Django folders is touched.

## How to run a step
1. In VS Code: File > Open Folder > this folder (`ESP3201A_SWE_exp1_sympy`).
2. Terminal > New Terminal (PowerShell).
3. Type the command for the step, e.g.
   `powershell -ExecutionPolicy Bypass -File .\step1_download.ps1`
4. Each step prints coloured headings. Green "STEP n DONE" = finished. Red "STOPPED" = copy the
   red text to Claude. Every step is safe to run again (it resumes where it stopped).

## The steps
| Step | When | Command (after `powershell -ExecutionPolicy Bypass -File`) | Time | GPU? |
|---|---|---|---|---|
| 1 | Tonight | `.\step1_download.ps1` (asks for your GitHub token) | 2-3 h | no |
| 2 | Wednesday | `.\step2_exp1_runs.ps1` (tuned run) | 4-5 h | yes |
| - | During step 2 | Claude writes the Exp 2 questions | - | - |
| 3 | When Claude says the questions are ready | `.\step3_exp2_check_questions.ps1`, then a person checks the sheet (~30 min) | 1 min | no |
| 4 | After steps 2 and 3 | `.\step4_exp2_run.ps1` | 30-45 min | yes |
| 2b | After step 4 (overnight) | `.\step2b_exp1_untuned.ps1` (untuned run + stats) | 7-9 h | yes |
| - | After step 4 | A person labels `exp2_sympy\correctness_sheet.csv` (~20 min) | - | - |
| 5 | After labelling | `.\step5_exp2_finish.ps1` | 5-30 min | yes |

Before step 2 (long GPU run): pause Windows Update for 1 week, plug in the charger, set sleep to
Never, and pause OneDrive sync. Only one GPU step at a time (2, 4, 2b, 5).

## What the steps do
- **Step 1** downloads the 75 SymPy tasks' fixing PRs plus 2,000 other SymPy PRs (like pool A),
  then picks candidate PRs for the Exp 2 questions (James's shortlist rules, fixed order).
- **Step 2** = Experiment 1 on SymPy: a 5-task check, then the tuned run (Django's locked pool A
  settings: fixed 512/77, structural 256, size-matched baseline, the same alpha per retriever),
  then stats.py on it. **Step 2b** = the untuned run + stats.py tuned vs untuned.
  Results: `results\swe_exp1_sympy_*`.
- **Step 3** checks every question quote is word for word in its PR and makes
  `exp2_sympy\question_check_sheet.csv`. A person opens each PR link and writes ok / fix / drop.
- **Step 4** = Experiment 2 on SymPy with the frozen setting: 4B model
  (qwen3:4b-instruct-2507-q4_K_M), prompt v3, arms F0 (fixed 512/77) and S0-G (structural,
  grouped), dense retrieval, 2,560-token budget, temperature 0, seed 42. Installs the model with
  Ollama if needed.
- **Step 5** runs the optional MiniCheck gate and prints the final table (`exp2_sympy\report.csv`).

## What is different from Django (decided before any SymPy result)
- `pr_document.py`: comments by `sympy-bot` are removed as a bot, and hidden HTML comments in PR
  descriptions (SymPy's PR template instructions, invisible on GitHub) are removed.
- `github_prs.py`: the same-ticket filter also reads "Fixes #N" in the description, because SymPy
  PR titles do not contain issue numbers.
- No pool H: its look-alike rules ("Fixed #N" titles, `django/` modules) are Django-specific.
- `exp2_sympy.py`: one script that copies James's frozen Exp 2 setting. Checked on the Django data:
  it rebuilds the same model inputs as James's runs (65/65 questions for F0 and for S0-G) and the
  same scores. Only "Django" -> "SymPy" in the prompt's first line and the search instruction.
- Everything else is the Django code, unchanged.
