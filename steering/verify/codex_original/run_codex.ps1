# run_codex.ps1 - Codex build of the ACTIVATION STEERING run (no weights change; not RL, not fine-tuning).
# James only runs this. It lives in <repo>\codex_steering\ and commits that folder before every stage.
#
#   .\codex_steering\run_codex.ps1 -Stage setup        preflight + prepare + smoke   (~15 min, downloads ~8 GB once)
#   .\codex_steering\run_codex.ps1 -Stage main         vectors, baseline, select, test, stats, blind sheet, report
#                                                      (unattended, several hours; safe to re-run, it resumes)
#   .\codex_steering\run_codex.ps1 -Stage sweep        optional, descriptive (also several hours)
#   .\codex_steering\run_codex.ps1 -Stage after-labels stats + report once Clifton's labels are in (CPU, 1 min)
#
# No $ErrorActionPreference = "Stop" on purpose: Python warnings on stderr must not abort the run.
param(
    [ValidateSet("setup", "main", "sweep", "after-labels")]
    [string]$Stage = "setup",
    [string]$Python = "python"
)

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONDONTWRITEBYTECODE = "1"
$Here = $PSScriptRoot
$Repo = Split-Path $Here -Parent
$Leaf = Split-Path $Here -Leaf
$Script = Join-Path $Here "codex_steer.py"

if (-not (Test-Path (Join-Path $Repo "exp2_gitlab_scale.py"))) {
    Write-Host "This folder must sit inside gitlab_runner_copy (as $Leaf). Not found: $Repo\exp2_gitlab_scale.py" -ForegroundColor Red
    exit 1
}

function Commit([string]$msg) {
    git -C $Repo add -- $Leaf
    git -C $Repo commit -q -m $msg -- $Leaf
    if ($LASTEXITCODE -eq 0) { Write-Host "committed: $msg" -ForegroundColor DarkGray }
    else { Write-Host "(nothing new to commit)" -ForegroundColor DarkGray }
}

function Step([string]$cmd, [string[]]$extra = @()) {
    Write-Host ""
    Write-Host ">>> $cmd   $(Get-Date -Format 'HH:mm')" -ForegroundColor Cyan
    & $Python $Script $cmd @extra
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "STOPPED at '$cmd' (exit code $LASTEXITCODE)." -ForegroundColor Red
        Write-Host "Send Clifton the folder $Here\out\logs (or a screenshot of the red text above)." -ForegroundColor Red
        Write-Host "Re-running the same stage later continues where it stopped." -ForegroundColor Red
        exit 1
    }
}

function Pack {
    $zip = Join-Path (Split-Path $Repo -Parent) "codex_steering_out.zip"
    Get-ChildItem (Join-Path $Here "out") -Exclude "acts" | Compress-Archive -DestinationPath $zip -Force
    Write-Host ""
    Write-Host "Results zipped to $zip - send this one file to Clifton." -ForegroundColor Green
}

$ollama = Get-Process -Name "ollama*" -ErrorAction SilentlyContinue
if ($ollama -and $Stage -ne "after-labels") {
    Write-Host "Ollama is running and holds GPU memory. Quit it first: right-click the llama icon by the clock -> Quit Ollama." -ForegroundColor Yellow
    Write-Host "Then run this command again." -ForegroundColor Yellow
    exit 1
}

switch ($Stage) {
    "setup" {
        Commit "codex steering: before setup"
        Step "preflight"
        Step "prepare"
        Step "smoke"
        Commit "codex steering: after setup"
        Write-Host ""
        Write-Host "SETUP DONE. Next (leave the laptop plugged in, lid open):  .\$Leaf\run_codex.ps1 -Stage main" -ForegroundColor Green
    }
    "main" {
        Commit "codex steering: before main"
        Step "vectors"
        Step "baseline"
        Step "select"
        Step "test"
        Step "stats"
        Step "blind"
        Step "report"
        Commit "codex steering: main results"
        Pack
        Write-Host "MAIN DONE." -ForegroundColor Green
    }
    "sweep" {
        Commit "codex steering: before sweep"
        Step "sweep"
        Step "stats"
        Step "report"
        Commit "codex steering: sweep results"
        Pack
        Write-Host "SWEEP DONE." -ForegroundColor Green
    }
    "after-labels" {
        Commit "codex steering: before after-labels"
        Step "stats"
        Step "report"
        Commit "codex steering: correctness"
        Write-Host "DONE: see $Here\out\codex_report.md" -ForegroundColor Green
    }
}
