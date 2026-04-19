#Requires -Version 5.1
<#
.SYNOPSIS
    Registers a Windows Scheduled Task that runs the CRA feed scraper daily.

.DESCRIPTION
    Run this script once (as the user who owns the repo) to install the task.
    Edit $RepoDir below if your clone is not at the default location, or set
    the REPO_DIR environment variable before running.

    After registration, test the task with:
        Start-ScheduledTask -TaskName "CRA Feed Scraper"
    Logs land in: <repo>\cra_feed\_logs\
#>

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Configuration — edit $RepoDir if your clone is somewhere else,
# or set the REPO_DIR environment variable before running this script.
# ---------------------------------------------------------------------------
$RepoDir = if ($env:REPO_DIR) { $env:REPO_DIR } else { "$env:USERPROFILE\code\payroll" }
$Script   = Join-Path $RepoDir "scripts\run_scraper.ps1"

# ---------------------------------------------------------------------------
# Build task components
# ---------------------------------------------------------------------------
$action = New-ScheduledTaskAction `
    -Execute  "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""

# 7:00 AM local machine time. Adjust to suit your timezone if needed.
$trigger = New-ScheduledTaskTrigger -Daily -At 7:00am

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------
Register-ScheduledTask `
    -TaskName   "CRA Feed Scraper" `
    -Action     $action `
    -Trigger    $trigger `
    -Settings   $settings `
    -Description "Daily CRA scrape + push to GitHub" `
    -User       $env:USERNAME `
    -RunLevel   Limited

Write-Host ""
Write-Host "Task registered successfully."
Write-Host ""
Write-Host "To run it immediately:"
Write-Host "    Start-ScheduledTask -TaskName 'CRA Feed Scraper'"
Write-Host ""
Write-Host "Logs are written to:"
Write-Host "    $RepoDir\cra_feed\_logs\"
