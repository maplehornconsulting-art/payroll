# scripts/ — Windows local scraper setup

These scripts let you run the CRA feed scraper **locally on Windows** via
Windows Task Scheduler, bypassing the canada.ca bot-protection that blocks
GitHub-hosted runner IPs.

## Prerequisites

1. **Python 3.12** — download from [python.org](https://www.python.org/downloads/).
   During installation check *"Add Python to PATH"* and ensure the **`py` launcher**
   is installed (it is by default on Windows).

2. **Git for Windows** — download from [git-scm.com](https://git-scm.com/download/win).
   Ensure `git` is on your `PATH`.

## Setup

### 1. Clone the repo

```powershell
cd $env:USERPROFILE\code          # or any directory you prefer
git clone https://github.com/maplehornconsulting-art/payroll.git
```

If you clone to a different location, set the `REPO_DIR` environment variable
to that path (or edit `$RepoDir` at the top of each script):

```powershell
[System.Environment]::SetEnvironmentVariable("REPO_DIR", "D:\projects\payroll", "User")
```

### 2. Authenticate Git for unattended push

Create a **fine-grained Personal Access Token** (PAT) on GitHub:

- Go to **Settings → Developer settings → Personal access tokens → Fine-grained tokens**
- Repository access: `maplehornconsulting-art/payroll` only
- Permissions: **Contents** → *Read and write*

Embed the token in the remote URL so Git can push without a prompt:

```powershell
cd $env:USERPROFILE\code\payroll
git remote set-url origin https://maplehornconsulting-art:<YOUR_PAT>@github.com/maplehornconsulting-art/payroll.git
```

> **Security note:** Anyone with access to your user profile can read this URL
> from `.git/config`. Treat it like a password.

### 3. Register the scheduled task

Open **PowerShell as your normal user** (not Administrator) and run:

```powershell
cd $env:USERPROFILE\code\payroll
.\scripts\register_task.ps1
```

This registers a task called **"CRA Feed Scraper"** that runs daily at **07:00
local machine time** (edit `$trigger` in `register_task.ps1` to change this)
and starts as soon as possible if the machine was off at that time.

### 4. Test the task

```powershell
Start-ScheduledTask -TaskName "CRA Feed Scraper"
```

Then check **Task Scheduler → Task Scheduler Library** for the last run result,
or inspect the log files directly:

```powershell
Get-ChildItem $env:USERPROFILE\code\payroll\cra_feed\_logs\
```

## Running manually

You can also run the scraper any time without the scheduler:

```powershell
cd $env:USERPROFILE\code\payroll
.\scripts\run_scraper.ps1
```

## Script reference

| Script | Purpose |
|---|---|
| `run_scraper.ps1` | Pulls latest `main`, installs deps, runs tests + scraper + validate, commits and pushes if JSON changed. |
| `register_task.ps1` | One-shot installer — registers the Windows Scheduled Task. Run once per machine. |

## Logs

Each run writes a transcript to `cra_feed\_logs\run-<UTC-timestamp>.log`.
The directory is created automatically on first run and is git-ignored.
