param(
    [switch]$NoElevate
)

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ($NoElevate) {
        throw "Execution administrateur requise pour creer les taches planifiees."
    }
    Start-Process powershell.exe `
        -Verb RunAs `
        -WindowStyle Hidden `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$PSCommandPath`"",
            "-NoElevate"
        )
    exit
}

$ScriptRootResolved = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$BackupScript = Join-Path $ScriptRootResolved "sauvegarde-automatique-quotidienne.ps1"
$ExternalBackupScript = Join-Path $ScriptRootResolved "sauvegarde-externe-hebdomadaire.ps1"
$WatchdogScript = Join-Path $ScriptRootResolved "surveiller-service-lomoto.ps1"

foreach ($script in @($BackupScript, $ExternalBackupScript, $WatchdogScript)) {
    if (-not (Test-Path -LiteralPath $script)) {
        throw "Script introuvable: $script"
    }
}

$taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

function New-PowerShellAction {
    param([string]$ScriptPath, [string]$ExtraArguments = "")
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" $ExtraArguments"
    return New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
}

$dailyBackupTask = "Boulangerie Lomoto - Sauvegarde quotidienne"
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At "22:30"
Register-ScheduledTask `
    -TaskName $dailyBackupTask `
    -Action (New-PowerShellAction -ScriptPath $BackupScript) `
    -Trigger $dailyTrigger `
    -Principal $taskPrincipal `
    -Settings $taskSettings `
    -Description "Cree une sauvegarde SQLite quotidienne via le service local Boulangerie Lomoto." `
    -Force | Out-Null

$weeklyBackupTask = "Boulangerie Lomoto - Sauvegarde externe hebdomadaire"
$weeklyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "23:15"
Register-ScheduledTask `
    -TaskName $weeklyBackupTask `
    -Action (New-PowerShellAction -ScriptPath $ExternalBackupScript) `
    -Trigger $weeklyTrigger `
    -Principal $taskPrincipal `
    -Settings $taskSettings `
    -Description "Copie les donnees du serveur vers un disque externe LOMOTO_BACKUP." `
    -Force | Out-Null

$watchdogTask = "Boulangerie Lomoto - Surveillance service"
$watchdogTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask `
    -TaskName $watchdogTask `
    -Action (New-PowerShellAction -ScriptPath $WatchdogScript -ExtraArguments "-CheckPublic") `
    -Trigger $watchdogTrigger `
    -Principal $taskPrincipal `
    -Settings $taskSettings `
    -Description "Verifie le service local, Cloudflare Tunnel et relance la file e-mail." `
    -Force | Out-Null

Write-Host "Taches planifiees installees :" -ForegroundColor Green
Write-Host "- $dailyBackupTask"
Write-Host "- $weeklyBackupTask"
Write-Host "- $watchdogTask"
