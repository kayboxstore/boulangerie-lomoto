param(
    [string]$Version = "1.5.7",
    [switch]$TasksOnly,
    [switch]$NoElevate
)

$ErrorActionPreference = "Stop"

$ProgramDataRoot = Join-Path $env:ProgramData "BoulangerieLomoto"
$MaintenanceRoot = Join-Path $ProgramDataRoot "maintenance"
$ResultPath = Join-Path $MaintenanceRoot "dernier-deploiement-production.json"
$ServiceName = "BoulangerieLomotoCentralServer"
$InstallRoot = Join-Path $env:ProgramFiles "Boulangerie Lomoto"

function Write-DeploymentResult {
    param(
        [string]$Status,
        [string]$Message,
        [hashtable]$Details = @{}
    )
    New-Item -ItemType Directory -Force -Path $MaintenanceRoot | Out-Null
    $payload = [ordered]@{
        status = $Status
        version = $Version
        message = $Message
        completedAt = (Get-Date).ToString("s")
        details = $Details
    }
    $payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
}

function Wait-ServiceExecutableReleased {
    param([int]$TimeoutSeconds = 45)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $processes = @(Get-CimInstance Win32_Process -Filter "Name='Boulangerie Lomoto Service.exe'" -ErrorAction SilentlyContinue)
    while ($processes.Count -gt 0 -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $processes = @(Get-CimInstance Win32_Process -Filter "Name='Boulangerie Lomoto Service.exe'" -ErrorAction SilentlyContinue)
    }
    if ($processes.Count -gt 0) {
        $processes | ForEach-Object {
            Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction Stop
        }
        Start-Sleep -Milliseconds 750
    }
    $remaining = @(Get-CimInstance Win32_Process -Filter "Name='Boulangerie Lomoto Service.exe'" -ErrorAction SilentlyContinue)
    if ($remaining.Count -gt 0) {
        throw "Le processus du service conserve encore le fichier executable."
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ($NoElevate) {
        throw "Execution administrateur requise pour mettre a jour le service et les taches."
    }
    $elevationArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-Version", "`"$Version`"",
        "-NoElevate"
    )
    if ($TasksOnly) {
        $elevationArguments += "-TasksOnly"
    }
    Start-Process powershell.exe `
        -Verb RunAs `
        -WindowStyle Hidden `
        -ArgumentList $elevationArguments
    Write-Host "Demande d'elevation Windows envoyee. Acceptez la fenetre UAC pour continuer." -ForegroundColor Yellow
    exit 0
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceService = Join-Path $root "dist\Boulangerie Lomoto\Boulangerie Lomoto Service.exe"
$targetService = Join-Path $InstallRoot "Boulangerie Lomoto Service.exe"
$targetScriptsRoot = Join-Path $InstallRoot "scripts"
$activeDatabase = Join-Path $ProgramDataRoot "central-server-data\boulangerie.db"
$backupScript = Join-Path $PSScriptRoot "sauvegarde-automatique-quotidienne.ps1"
$taskInstallerName = "installer-taches-production-lomoto.ps1"
$scriptNames = @(
    "sauvegarde-automatique-quotidienne.ps1",
    "sauvegarde-externe-hebdomadaire.ps1",
    "surveiller-service-lomoto.ps1",
    $taskInstallerName,
    "tester-restauration-sauvegarde-lomoto.ps1",
    "verifier-taches-production-lomoto.ps1"
)

if (([IO.Path]::GetFullPath($InstallRoot)).TrimEnd("\") -ne "C:\Program Files\Boulangerie Lomoto") {
    throw "Dossier d'installation inattendu : $InstallRoot"
}
foreach ($requiredPath in @($sourceService, $targetService, $activeDatabase, $backupScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Fichier requis introuvable : $requiredPath"
    }
}
foreach ($scriptName in $scriptNames) {
    $sourceScript = Join-Path $PSScriptRoot $scriptName
    if (-not (Test-Path -LiteralPath $sourceScript)) {
        throw "Script requis introuvable : $sourceScript"
    }
}

if ($TasksOnly) {
    try {
        Write-DeploymentResult -Status "running" -Message "Installation des taches de production en cours."
        New-Item -ItemType Directory -Force -Path $targetScriptsRoot | Out-Null
        foreach ($scriptName in $scriptNames) {
            Copy-Item -LiteralPath (Join-Path $PSScriptRoot $scriptName) -Destination (Join-Path $targetScriptsRoot $scriptName) -Force
        }
        & (Join-Path $targetScriptsRoot $taskInstallerName) -NoElevate
        $taskNames = @(
            "Boulangerie Lomoto - Sauvegarde quotidienne",
            "Boulangerie Lomoto - Sauvegarde externe hebdomadaire",
            "Boulangerie Lomoto - Surveillance service",
            "Boulangerie Lomoto - Test restauration hebdomadaire"
        )
        $missingTasks = @($taskNames | Where-Object { -not (Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue) })
        if ($missingTasks.Count -gt 0) {
            throw "Taches absentes apres installation : $($missingTasks -join ', ')"
        }
        $validationResults = @()
        $validationTaskNames = @(
            "Boulangerie Lomoto - Sauvegarde quotidienne",
            "Boulangerie Lomoto - Test restauration hebdomadaire",
            "Boulangerie Lomoto - Surveillance service"
        )
        foreach ($taskName in $validationTaskNames) {
            Start-ScheduledTask -TaskName $taskName
            $deadline = (Get-Date).AddSeconds(90)
            do {
                Start-Sleep -Seconds 1
                $task = Get-ScheduledTask -TaskName $taskName
            } while ($task.State -eq "Running" -and (Get-Date) -lt $deadline)
            if ($task.State -eq "Running") {
                throw "La validation de la tache '$taskName' a depasse 90 secondes."
            }
            $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
            $validationResults += [ordered]@{
                taskName = $taskName
                lastRunTime = $taskInfo.LastRunTime
                lastResult = $taskInfo.LastTaskResult
                nextRunTime = $taskInfo.NextRunTime
            }
            if ($taskInfo.LastTaskResult -ne 0) {
                throw "La validation de la tache '$taskName' a echoue (code $($taskInfo.LastTaskResult))."
            }
        }
        Write-DeploymentResult `
            -Status "ok" `
            -Message "Les quatre taches sont installees; sauvegarde, restauration et surveillance validees." `
            -Details @{ validation = $validationResults }
        exit 0
    }
    catch {
        Write-DeploymentResult -Status "error" -Message $_.Exception.Message
        throw
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$deploymentBackupRoot = Join-Path $ProgramDataRoot "deployment-backups\avant-$Version-$timestamp"
$serviceBackup = Join-Path $deploymentBackupRoot "Boulangerie Lomoto Service.exe"
$stagingService = Join-Path $InstallRoot "Boulangerie Lomoto Service.exe.new"
$details = @{
    backupRoot = $deploymentBackupRoot
    sourceService = $sourceService
    targetService = $targetService
}

try {
    Write-DeploymentResult -Status "running" -Message "Deploiement $Version en cours." -Details $details

    & $sourceService --check-sqlite $activeDatabase
    if ($LASTEXITCODE -ne 0) {
        throw "Le binaire $Version refuse la base active au controle SQLite."
    }

    $backupProcess = Start-Process powershell.exe `
        -WindowStyle Hidden `
        -Wait `
        -PassThru `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$backupScript`"",
            "-Force"
        )
    if ($backupProcess.ExitCode -ne 0) {
        throw "La sauvegarde de securite avant deploiement a echoue."
    }

    New-Item -ItemType Directory -Force -Path $deploymentBackupRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $targetScriptsRoot | Out-Null
    Copy-Item -LiteralPath $targetService -Destination $serviceBackup -Force
    foreach ($scriptName in $scriptNames) {
        $installedScript = Join-Path $targetScriptsRoot $scriptName
        if (Test-Path -LiteralPath $installedScript) {
            Copy-Item -LiteralPath $installedScript -Destination (Join-Path $deploymentBackupRoot $scriptName) -Force
        }
    }

    Stop-Service -Name $ServiceName -Force
    (Get-Service -Name $ServiceName).WaitForStatus("Stopped", [TimeSpan]::FromSeconds(45))
    Wait-ServiceExecutableReleased
    Copy-Item -LiteralPath $sourceService -Destination $stagingService -Force
    Copy-Item -LiteralPath $stagingService -Destination $targetService -Force
    Remove-Item -LiteralPath $stagingService -Force

    foreach ($scriptName in $scriptNames) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $scriptName) -Destination (Join-Path $targetScriptsRoot $scriptName) -Force
    }

    Start-Service -Name $ServiceName
    (Get-Service -Name $ServiceName).WaitForStatus("Running", [TimeSpan]::FromSeconds(45))

    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8787/api/health" -TimeoutSec 30
    if (-not $health.ok -or [string]$health.version -ne $Version) {
        throw "Le service a redemarre, mais la version attendue $Version n'est pas active."
    }

    $installedTaskScript = Join-Path $targetScriptsRoot $taskInstallerName
    & $installedTaskScript -NoElevate

    $details["serviceSha256"] = (Get-FileHash -LiteralPath $targetService -Algorithm SHA256).Hash
    $details["healthVersion"] = [string]$health.version
    Write-DeploymentResult -Status "ok" -Message "Service $Version et taches de production installes." -Details $details
}
catch {
    $failure = $_.Exception.Message
    try {
        if (Test-Path -LiteralPath $serviceBackup) {
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            (Get-Service -Name $ServiceName).WaitForStatus("Stopped", [TimeSpan]::FromSeconds(30))
            Wait-ServiceExecutableReleased -TimeoutSeconds 30
            Copy-Item -LiteralPath $serviceBackup -Destination $targetService -Force
            Start-Service -Name $ServiceName
            (Get-Service -Name $ServiceName).WaitForStatus("Running", [TimeSpan]::FromSeconds(45))
            $details["rollback"] = "ancien service restaure"
        }
    }
    catch {
        $details["rollback"] = "echec du retour arriere : $($_.Exception.Message)"
    }
    Write-DeploymentResult -Status "error" -Message $failure -Details $details
    throw
}
