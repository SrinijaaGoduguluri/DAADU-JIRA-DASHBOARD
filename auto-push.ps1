# Auto-push watcher for the DAADU JIRA dashboard.
# Watches this project folder and, whenever files change and then go quiet,
# commits and pushes to GitHub -> Streamlit Cloud auto-redeploys.
#
# Start it by double-clicking auto-push.bat, or run:  powershell -File auto-push.ps1
# Stop it with Ctrl+C (or just close the window).

$ErrorActionPreference = "SilentlyContinue"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

# Make sure git is reachable even if PATH is stale.
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $gitCandidates = @(
        "$env:LOCALAPPDATA\Programs\Git\cmd",
        "$env:ProgramFiles\Git\cmd",
        "${env:ProgramFiles(x86)}\Git\cmd"
    )
    foreach ($c in $gitCandidates) {
        if (Test-Path (Join-Path $c "git.exe")) { $env:Path = "$c;" + $env:Path; break }
    }
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: git not found. Install Git or add it to PATH." -ForegroundColor Red
    Start-Sleep -Seconds 8
    exit 1
}

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ([string]::IsNullOrWhiteSpace($branch)) { $branch = "main" }

Write-Host "==================================================================="
Write-Host " Auto-push is watching:"
Write-Host "   $repo"
Write-Host " Branch: $branch"
Write-Host " Any saved change is committed + pushed after ~6s of quiet."
Write-Host " Keep this window open. Press Ctrl+C to stop."
Write-Host "==================================================================="

$last = ""
while ($true) {
    Start-Sleep -Seconds 3
    $status = (git status --porcelain) -join "`n"

    if ([string]::IsNullOrWhiteSpace($status)) {
        $last = ""
        continue
    }

    if ($status -eq $last) {
        # Changes have been stable for one full cycle -> safe to push.
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        git add -A | Out-Null
        git commit -m "auto: sync $stamp" | Out-Null
        git push origin $branch | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] Pushed to $branch. Streamlit will redeploy shortly."
        } else {
            Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] Push failed - check your GitHub connection."
        }
        $last = ""
    } else {
        $last = $status
    }
}
