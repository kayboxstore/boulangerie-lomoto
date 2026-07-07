param(
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$serviceName = "BoulangerieLomotoCentralServer"
$sourceCandidates = @(
    (Join-Path $root "dist\Boulangerie Lomoto\Boulangerie Lomoto Service.exe"),
    (Join-Path $root "dist\Boulangerie Lomoto Service.exe")
)
$source = $sourceCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
$installDir = "C:\Program Files\Boulangerie Lomoto"
$target = Join-Path $installDir "Boulangerie Lomoto Service.exe"

if (-not $source) {
    throw "Service compile introuvable. Chemins testes : $($sourceCandidates -join ', ')"
}
if (-not (Test-Path -LiteralPath $installDir)) {
    throw "Dossier d'installation introuvable : $installDir"
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-NoPause"
    )
    Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments
    exit
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = "$target.$timestamp.bak"
$staging = "$target.new"

Write-Host "Mise a jour du service Boulangerie Lomoto..." -ForegroundColor Cyan
try {
    $serviceInfo = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
    $serviceProcessId = [int]$serviceInfo.ProcessId

    Stop-Service -Name $serviceName -Force
    $service = Get-Service -Name $serviceName
    $service.WaitForStatus("Stopped", [TimeSpan]::FromSeconds(30))

    if ($serviceProcessId -gt 0) {
        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Process -Id $serviceProcessId -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 500
        }
        if (Get-Process -Id $serviceProcessId -ErrorAction SilentlyContinue) {
            throw "Le processus du service ne s'est pas ferme dans le delai prevu."
        }
    }

    Copy-Item -LiteralPath $source -Destination $staging -Force
    Copy-Item -LiteralPath $target -Destination $backup -Force
    Copy-Item -LiteralPath $staging -Destination $target -Force
    Remove-Item -LiteralPath $staging -Force -ErrorAction SilentlyContinue

    Start-Service -Name $serviceName
    $service = Get-Service -Name $serviceName
    $service.WaitForStatus("Running", [TimeSpan]::FromSeconds(45))

    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8787/" -UseBasicParsing -TimeoutSec 20
    if ($response.StatusCode -ne 200) {
        throw "Le service a redemarre, mais le controle HTTP a echoue."
    }
}
catch {
    Remove-Item -LiteralPath $staging -Force -ErrorAction SilentlyContinue
    if ((Get-Service -Name $serviceName).Status -ne "Running") {
        Start-Service -Name $serviceName -ErrorAction SilentlyContinue
    }
    throw
}

Write-Host "Service mis a jour et site operationnel." -ForegroundColor Green
Write-Host "Sauvegarde de l'ancien service : $backup" -ForegroundColor DarkGray

if (-not $NoPause) {
    Read-Host "Appuyez sur Entree pour fermer"
}
