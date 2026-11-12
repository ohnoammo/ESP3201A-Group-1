# STEP 1 (tonight): download the SymPy data. About 2-3 hours, no GPU. Safe to re-run: it resumes.
# Run:  powershell -ExecutionPolicy Bypass -File .\step1_download.ps1
. "$PSScriptRoot\_common.ps1"
Write-Host "STEP 1: download SymPy pull requests (about 2-3 hours, no GPU)." -ForegroundColor Green
# GitHub token: test it before the long download; ask again if GitHub rejects it.
$check = "import os,requests,sys; t=os.environ.get('GITHUB_TOKEN',''); " +
         "r=requests.get('https://api.github.com/rate_limit', headers={'Authorization':'Bearer '+t}, timeout=30); " +
         "ok=r.status_code==200; print('GitHub says: token accepted, %s requests/hour' % r.json()['resources']['core']['limit'] if ok else 'GitHub says: HTTP %d (token rejected)' % r.status_code); " +
         "sys.exit(0 if ok else 1)"
$ok = $false
for ($try = 0; $try -le 3; $try++) {
    if ($env:GITHUB_TOKEN) {
        $env:GITHUB_TOKEN = $env:GITHUB_TOKEN.Trim()
        $t = $env:GITHUB_TOKEN
        Write-Host ("Testing the token (starts with '" + $t.Substring(0, [Math]::Min(11, $t.Length)) + "', " + $t.Length + " characters) ...")
        & $py -c $check
        if ($LASTEXITCODE -eq 0) { $ok = $true; break }
        Write-Host "That token does not work (expired, mistyped, or an old one)." -ForegroundColor Yellow
        $env:GITHUB_TOKEN = ""
    }
    if ($try -eq 3) { break }
    $sec = Read-Host "Paste your GitHub token and press Enter (it is not shown and not saved)" -AsSecureString
    $env:GITHUB_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
if (-not $ok) {
    Write-Host "No working token after 3 tries. Make a new token (see Claude's steps) and run step 1 again." -ForegroundColor Red
    exit 1
}
Invoke-Step @("swebench_loader.py", "--repo", "sympy/sympy") "Check the SymPy tasks (should say 75 tasks)"
Invoke-Step @("github_prs.py", "index", "--repo", "sympy/sympy") "List all SymPy PRs"
Invoke-Step @("github_prs.py", "fixing", "--repo", "sympy/sympy") "Download the 75 fixing PRs"
Invoke-Step @("github_prs.py", "download", "--repo", "sympy/sympy", "--pool", "A", "--n-distractors", "2000") "Download 2,000 other PRs (the long part)"
Invoke-Step @("github_prs.py", "pool-check", "--repo", "sympy/sympy", "--pool", "A", "--n-distractors", "2000") "Check the pool"
& $py -c "import json,sys; d=json.load(open('prs/sympy_sympy/_pool_A2000.json', encoding='utf-8')); sys.exit(0 if d.get('complete') else 3)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "The pool is not complete yet (some downloads failed). Run step 1 again; it resumes." -ForegroundColor Yellow
    exit 1
}
Invoke-Step @("exp2_sympy.py", "shortlist") "Experiment 2: shortlist PRs for the questions"
Write-Host ""
Write-Host "STEP 1 DONE. Tell Claude: step 1 done." -ForegroundColor Green
