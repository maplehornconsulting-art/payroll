#Requires -Version 5.1
<#
.SYNOPSIS
    Runs the CRA payroll feed scraper locally and pushes updated JSON to GitHub.

.DESCRIPTION
    Mirrors what the GitHub Actions workflow does but runs unattended on a
    Windows machine (e.g. via Windows Task Scheduler).

    Environment variable REPO_DIR can override the default repo location.
    Logs are written to <repo>\cra_feed\_logs\run-<UTC-timestamp>.log.
#>

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
$RepoDir = if ($env:REPO_DIR) { $env:REPO_DIR } else { "$env:USERPROFILE\code\payroll" }

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
$LogDir = Join-Path $RepoDir "cra_feed\_logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$LogFile = Join-Path $LogDir "run-$Timestamp.log"

Start-Transcript -Path $LogFile -Append

try {
    Write-Host "=== CRA Feed Scraper — start $(Get-Date -Format o) ==="

    # -----------------------------------------------------------------------
    # Git: sync to latest main
    # -----------------------------------------------------------------------
    Set-Location $RepoDir

    git fetch origin main
    git checkout main
    git pull --ff-only origin main

    # -----------------------------------------------------------------------
    # Python virtual environment
    # -----------------------------------------------------------------------
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment with Python 3.12 ..."
        py -3.12 -m venv .venv
    }

    & ".venv\Scripts\Activate.ps1"

    python -m pip install --quiet --upgrade pip
    pip install --quiet -r cra_feed\requirements.txt

    # -----------------------------------------------------------------------
    # Tests
    # -----------------------------------------------------------------------
    pytest cra_feed\tests\ -v

    # -----------------------------------------------------------------------
    # Scrape
    # -----------------------------------------------------------------------
    python -m cra_feed.scraper --debug-html

    # -----------------------------------------------------------------------
    # Validate
    # -----------------------------------------------------------------------
    python -m cra_feed.validate cra_feed\output\v1\ca\latest.json

    # -----------------------------------------------------------------------
    # Commit + push if anything changed
    # -----------------------------------------------------------------------
    git add cra_feed/output/
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        git -c user.name="local-scraper" `
            -c user.email="local-scraper@$env:COMPUTERNAME" `
            commit -m "chore: update CRA feed (local run) [skip ci]"
        git push origin main
    } else {
        Write-Host "No changes to commit."
    }

    Write-Host "=== CRA Feed Scraper — end $(Get-Date -Format o) ==="
}
finally {
    Stop-Transcript
}
