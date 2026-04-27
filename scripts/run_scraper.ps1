﻿#Requires -Version 5.1
<#
.SYNOPSIS
    Runs the CRA payroll feed scraper locally and pushes updated JSON to GitHub.

.DESCRIPTION
    Mirrors what the GitHub Actions workflow does but runs unattended on a
    Windows machine (e.g. via Windows Task Scheduler).

    Environment variable REPO_DIR can override the default repo location.
    Logs are written to <repo>\cra_feed\_logs\run-<UTC-timestamp>.log.

    Self-healing behaviour:
      - Aborts any leftover rebase/merge state from a prior interrupted run.
      - Hard-resets local main to origin/main if fast-forward fails
        (this machine is never the authoritative source for main).
      - Wipes pytest tmp dirs in BOTH locations to avoid Defender/OneDrive
        file-lock errors (PermissionError [WinError 5]).
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
    Write-Host "=== CRA Feed Scraper -- start $(Get-Date -Format o) ==="

    # -----------------------------------------------------------------------
    # Git: sync to latest main (self-healing)
    # -----------------------------------------------------------------------
    Set-Location $RepoDir

    # Defensive: clean up any half-finished rebase/merge from a prior aborted
    # run. Without this, every subsequent run fails until a human intervenes.
    if (Test-Path ".git\rebase-merge") {
        Write-Warning "Found leftover rebase-merge state; aborting it."
        git rebase --abort 2>&1 | Out-Null
    }
    if (Test-Path ".git\rebase-apply") {
        Write-Warning "Found leftover rebase-apply state; aborting it."
        git rebase --abort 2>&1 | Out-Null
    }
    if (Test-Path ".git\MERGE_HEAD") {
        Write-Warning "Found leftover merge state; aborting it."
        git merge --abort 2>&1 | Out-Null
    }
    if (Test-Path ".git\CHERRY_PICK_HEAD") {
        Write-Warning "Found leftover cherry-pick state; aborting it."
        git cherry-pick --abort 2>&1 | Out-Null
    }

    git fetch origin main
    if ($LASTEXITCODE -ne 0) { throw "git fetch failed with exit code $LASTEXITCODE" }

    git checkout main
    if ($LASTEXITCODE -ne 0) { throw "git checkout main failed with exit code $LASTEXITCODE" }

    # Try fast-forward first. If local main has diverged (e.g. a previous
    # local commit was rebased/squashed upstream), hard-reset to origin/main.
    # This box is never authoritative for main — origin always wins.
    git pull --ff-only origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Fast-forward pull failed; hard-resetting local main to origin/main."
        git reset --hard origin/main
        if ($LASTEXITCODE -ne 0) { throw "git reset --hard origin/main failed with exit code $LASTEXITCODE" }
    }

    # -----------------------------------------------------------------------
    # Python virtual environment
    # -----------------------------------------------------------------------
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment with Python 3.12 ..."
        py -3.12 -m venv .venv
    }

    & ".venv\Scripts\Activate.ps1"

    python -m pip install --quiet --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Step failed with exit code $LASTEXITCODE" }
    pip install --quiet -r cra_feed\requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Step failed with exit code $LASTEXITCODE" }

    # -----------------------------------------------------------------------
    # Tests
    # -----------------------------------------------------------------------
    # Move pytest's tmp root inside the repo so Windows Defender / OneDrive don't
    # lock files we need to delete. Wipe stale tmp dirs from prior runs in BOTH
    # the default LOCALAPPDATA location AND the in-repo location.
    Remove-Item "$env:LOCALAPPDATA\Temp\pytest-of-$env:USERNAME" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $RepoDir "cra_feed\_pytest_tmp")     -Recurse -Force -ErrorAction SilentlyContinue

    $env:PYTEST_DEBUG_TEMPROOT = Join-Path $RepoDir "cra_feed\_pytest_tmp"
    New-Item -ItemType Directory -Force -Path $env:PYTEST_DEBUG_TEMPROOT | Out-Null
    pytest cra_feed\tests\ -v
    if ($LASTEXITCODE -ne 0) { throw "Step failed with exit code $LASTEXITCODE" }

    # -----------------------------------------------------------------------
    # Scrape
    # -----------------------------------------------------------------------
    python -m cra_feed.scraper --debug-html
    if ($LASTEXITCODE -ne 0) { throw "Step failed with exit code $LASTEXITCODE" }

    # -----------------------------------------------------------------------
    # Validate
    # -----------------------------------------------------------------------
    python -m cra_feed.validate cra_feed\output\v1\ca\latest.json
    if ($LASTEXITCODE -ne 0) { throw "Step failed with exit code $LASTEXITCODE" }

    # -----------------------------------------------------------------------
    # Commit + push if anything changed
    # -----------------------------------------------------------------------
    # Stage only what we own; check pathspec-scoped diff (not the whole index).
    git add -- cra_feed/output/
    git diff --cached --quiet -- cra_feed/output/
    if ($LASTEXITCODE -ne 0) {
        $env:GIT_AUTHOR_NAME     = 'local-scraper'
        $env:GIT_AUTHOR_EMAIL    = "local-scraper@$env:COMPUTERNAME"
        $env:GIT_COMMITTER_NAME  = 'local-scraper'
        $env:GIT_COMMITTER_EMAIL = "local-scraper@$env:COMPUTERNAME"
        try {
            # Path-scoped commit — never picks up unrelated staged files.
            git commit -m 'chore: update CRA feed [local run] [skip ci]' -- cra_feed/output/
            git push origin main
        } finally {
            $env:GIT_AUTHOR_NAME     = $null
            $env:GIT_AUTHOR_EMAIL    = $null
            $env:GIT_COMMITTER_NAME  = $null
            $env:GIT_COMMITTER_EMAIL = $null
        }
    } else {
        Write-Host "No changes to commit."
    }

    Write-Host "=== CRA Feed Scraper -- end $(Get-Date -Format o) ==="
}
finally {
    Stop-Transcript
}
