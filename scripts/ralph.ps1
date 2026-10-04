<#
.SYNOPSIS
    Ralph Autonomous Development Loop for Windows PowerShell.
.DESCRIPTION
    Runs an iterative, fresh-context AI coding agent loop (using opencode or custom agent CLI)
    against the project backlog defined in tasks.md using instructions in PROMPT.md.
.PARAMETER MaxIterations
    Maximum number of autonomous iterations to perform (default: 10).
.PARAMETER AgentCommand
    Agent CLI runner command. Defaults to 'opencode run --auto'.
.PARAMETER PromptFile
    Path to the system instructions prompt file (default: PROMPT.md).
.PARAMETER TasksFile
    Path to the task backlog file (default: tasks.md).
.EXAMPLE
    .\scripts\ralph.ps1
    .\scripts\ralph.ps1 -MaxIterations 5
#>

param(
    [int]$MaxIterations = 10,
    [string]$AgentCommand = "opencode run --auto",
    [string]$PromptFile = "PROMPT.md",
    [string]$TasksFile = "tasks.md"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "               RALPH AUTONOMOUS CODING LOOP               " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Target Tasks:    $TasksFile"
Write-Host "Prompt File:     $PromptFile"
Write-Host "Agent Command:   $AgentCommand"
Write-Host "Max Iterations:  $MaxIterations"
Write-Host "==========================================================" -ForegroundColor Cyan

if (-not (Test-Path $PromptFile)) {
    Write-Error "Prompt file '$PromptFile' not found!"
    exit 1
}

if (-not (Test-Path $TasksFile)) {
    Write-Error "Tasks file '$TasksFile' not found!"
    exit 1
}

$promptContent = Get-Content -Raw -Path $PromptFile

for ($i = 1; $i -le $MaxIterations; $i++) {
    Write-Host "`n>>> [Iteration $i of $MaxIterations] Starting Ralph Cycle..." -ForegroundColor Green

    # Check if any incomplete tasks remain in tasks.md
    $incompleteTasks = Get-Content $TasksFile | Where-Object { $_ -match '^\s*-\s*\[\s*\]' }
    if (-not $incompleteTasks) {
        Write-Host "`nAll tasks in $TasksFile are completed! Exiting loop." -ForegroundColor Green
        break
    }

    $firstTask = $incompleteTasks[0].Trim()
    Write-Host "Next backlog item: $firstTask" -ForegroundColor Gray

    # Build prompt argument
    $fullPrompt = @"
$promptContent

---
Current Ralph Loop Iteration: $i of $MaxIterations.
Selected Target Task: $firstTask
Please execute this task thoroughly, verify tests, update tasks.md, log in PROGRESS.md, and commit.
"@

    $tempPromptFile = [System.IO.Path]::GetTempFileName()
    try {
        Set-Content -Path $tempPromptFile -Value $fullPrompt -Encoding utf8

        # Execute agent CLI with fresh context
        Write-Host "Invoking agent with fresh context..." -ForegroundColor Cyan
        $processInfo = New-Object System.Diagnostics.ProcessStartInfo
        $cmdParts = $AgentCommand.Split(' ', 2)
        $processInfo.FileName = $cmdParts[0]
        if ($cmdParts.Length -gt 1) {
            $processInfo.Arguments = "$($cmdParts[1]) `"$fullPrompt`""
        } else {
            $processInfo.Arguments = "`"$fullPrompt`""
        }
        $processInfo.UseShellExecute = $false
        $processInfo.RedirectStandardOutput = $true
        $processInfo.RedirectStandardError = $true
        $processInfo.CreateNoWindow = $false

        $process = [System.Diagnostics.Process]::Start($processInfo)
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()

        Write-Host $stdout

        if ($stderr) {
            Write-Host $stderr -ForegroundColor DarkYellow
        }

        if ($stdout -match "<<<RALPH_ALL_TASKS_COMPLETED>>>") {
            Write-Host "`nSignal received: <<<RALPH_ALL_TASKS_COMPLETED>>>. Halting loop." -ForegroundColor Green
            break
        }

        # Check git status
        $gitStatus = git status --porcelain
        if ($gitStatus) {
            Write-Host "Notice: Uncommitted changes detected after iteration $i. Check git diff." -ForegroundColor Yellow
        } else {
            Write-Host "Git working tree clean. Iteration $i committed successfully." -ForegroundColor Green
        }
    }
    catch {
        Write-Host "Error in iteration $i`: $_" -ForegroundColor Red
        break
    }
    finally {
        if (Test-Path $tempPromptFile) {
            Remove-Item -Force $tempPromptFile
        }
    }

    Write-Host "Completed iteration $i. Cooling down before next cycle..." -ForegroundColor Cyan
    Start-Sleep -Seconds 2
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "               RALPH LOOP FINISHED                        " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
