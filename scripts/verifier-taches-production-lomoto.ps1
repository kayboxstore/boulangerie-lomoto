param(
    [switch]$NoElevate
)

$ErrorActionPreference = "Stop"

$ProgramDataRoot = Join-Path $env:ProgramData "BoulangerieLomoto"
$MaintenanceRoot = Join-Path $ProgramDataRoot "maintenance"
$OutputPath = Join-Path $MaintenanceRoot "taches-production-status.json"
$TaskNames = @(
    "Boulangerie Lomoto - Sauvegarde quotidienne",
    "Boulangerie Lomoto - Sauvegarde externe hebdomadaire",
    "Boulangerie Lomoto - Surveillance service",
    "Boulangerie Lomoto - Test restauration hebdomadaire"
)

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ($NoElevate) {
        throw "Execution administrateur requise."
    }
    Start-Process powershell.exe `
        -Verb RunAs `
        -WindowStyle Hidden `
        -Wait `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$PSCommandPath`"",
            "-NoElevate"
        )
    if (Test-Path -LiteralPath $OutputPath) {
        Get-Content -LiteralPath $OutputPath -Raw -Encoding UTF8
    }
    exit
}

New-Item -ItemType Directory -Force -Path $MaintenanceRoot | Out-Null
$rows = foreach ($taskName in $TaskNames) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
        [ordered]@{
            taskName = $taskName
            exists = $true
            state = [string]$task.State
            lastRunTime = $taskInfo.LastRunTime
            lastResult = $taskInfo.LastTaskResult
            nextRunTime = $taskInfo.NextRunTime
        }
    }
    else {
        [ordered]@{
            taskName = $taskName
            exists = $false
            state = ""
            lastRunTime = ""
            lastResult = ""
            nextRunTime = ""
        }
    }
}

$payload = [ordered]@{
    checkedAt = (Get-Date).ToString("s")
    computer = $env:COMPUTERNAME
    tasks = $rows
}
$payload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Get-Content -LiteralPath $OutputPath -Raw -Encoding UTF8
