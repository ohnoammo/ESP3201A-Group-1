# Codex steering run: what James does

This is the **Codex** build of the activation-steering experiment. It is separate from Claude's build
(`FOR_JAMES_steering`): different folder (`codex_steering`), different script (`codex_steer.py`), different
outputs. Don't mix the two.

**What it is, in one line.** Activation steering: a fixed vector is added inside the frozen
Qwen3-4B-Instruct model while it answers. No weights change. It is not reinforcement learning and not
fine-tuning.

You only run commands. About 20 minutes of your time; the rest runs by itself overnight.

## Before you start (5 min)

1. **Copy the folder.** Copy the whole `CODEX_steering` folder Clifton sent you into your repo and rename it
   `codex_steering`, so you have:
   `C:\Users\kwekt\ESP3201A_local\gitlab_runner_copy\codex_steering\codex_steer.py`
   Do not change anything in `codex_steering\out\`: the run checks that your machine reproduces those files
   exactly.
2. **Quit Ollama.** Right-click the llama icon by the clock → Quit Ollama. (It holds GPU memory.)
3. **Power.** Plug the laptop in and keep the lid open. The script asks Windows not to sleep while it runs,
   but closing the lid can still put it to sleep.
4. **Open PowerShell in the repo** (the same Python environment you used for Exp 1):

```powershell
cd C:\Users\kwekt\ESP3201A_local\gitlab_runner_copy
```

## Step 1: setup (about 15 min; downloads about 8 GB the first time)

```powershell
powershell -ExecutionPolicy Bypass -File .\codex_steering\run_codex.ps1 -Stage setup
```

It commits the folder, then runs:
- **preflight**: checks your Python packages, that torch is a CUDA 12.8 build that works on the RTX 5070,
  free GPU memory, that your data files are byte-identical to Clifton's copy, and downloads the model.
- **prepare**: rebuilds the 70 prompts from your data and checks they equal the stored Exp 2 run and the
  files Clifton sent.
- **smoke**: a 2-minute GPU test (the same answer twice; the steering hook changes the answer; removing it
  restores the answer).

It should end with `SETUP DONE`. If it prints red text and stops, send Clifton a screenshot and the folder
`codex_steering\out\logs`.

**If preflight says the torch build is wrong**, run the command it prints, which is:

```powershell
python -m pip install --upgrade --force-reinstall torch --index-url https://download.pytorch.org/whl/cu128
```

then run Step 1 again.

## Step 2: the main run (unattended, roughly 3 to 6 hours)

```powershell
powershell -ExecutionPolicy Bypass -File .\codex_steering\run_codex.ps1 -Stage main
```

Leave it running (overnight is fine). Smoke printed a time estimate. If it stops for any reason (crash,
sleep, you closed the window), just run the same command again: it continues where it stopped and redoes
nothing.

It ends with `MAIN DONE` and makes **one zip file**, `C:\Users\kwekt\ESP3201A_local\codex_steering_out.zip`.
Send that to Clifton. That's all.

## Optional step 3: the sweep (only if Clifton asks; also several hours)

```powershell
powershell -ExecutionPolicy Bypass -File .\codex_steering\run_codex.ps1 -Stage sweep
```

Send the new zip afterwards.

## Rules (please keep them)

- Don't open `codex_steering\out\keys\` or `exp2_gitlab_A2000\keys\`.
- Don't edit any file in `codex_steering\out\` and don't write labels anywhere.
- Don't run `exp2_gitlab_scale.py score` or `build`. This run never needs them.
- No GitLab token is needed. Nothing here uses the network except the one-time model download.
- The runbook only commits the `codex_steering` folder. It never touches Exp 1 or Exp 2 files.

## After Clifton labels the blind sheet (Clifton, not James)

Clifton labels `out\blind_sheet_blank.csv` into a copy named `out\blind_sheet_labels.csv`, then runs on his
own PC (CPU only, from the unzipped `out` folder in `Latest\CODEX_steering\out`):

```powershell
python CODEX_steering\codex_steer.py stats
```

```powershell
python CODEX_steering\codex_steer.py report
```

(or James runs `-Stage after-labels` if the labelled file is copied back to him).
