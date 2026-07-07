param(
    [switch]$Force,
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"

$ProgramDataRoot = Join-Path $env:ProgramData "BoulangerieLomoto"
$DataRoot = Join-Path $ProgramDataRoot "central-server-data"
$MaintenanceRoot = Join-Path $ProgramDataRoot "maintenance"
$TokenPath = Join-Path $DataRoot "maintenance-token.txt"
$LogPath = Join-Path $MaintenanceRoot "sauvegarde-automatique-quotidienne.log"
$ServiceName = "BoulangerieLomotoCentralServer"

function Write-MaintenanceLog {
    param([string]$Message)
    New-Item -ItemType Directory -Force -Path $MaintenanceRoot | Out-Null
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "[$timestamp] $Message"
}

function New-UrlSafeToken {
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    return ([Convert]::ToBase64String($bytes)).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Get-MaintenanceToken {
    New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
    if (Test-Path -LiteralPath $TokenPath) {
        $token = (Get-Content -LiteralPath $TokenPath -Raw -Encoding UTF8).Trim()
        if ($token.Length -ge 32) {
            return $token
        }
    }

    $token = New-UrlSafeToken
    Set-Content -LiteralPath $TokenPath -Value $token -Encoding UTF8
    & icacls.exe $TokenPath /inheritance:r /grant:r "SYSTEM:(F)" "Administrators:(F)" | Out-Null
    return $token
}

function Invoke-BackupApi {
    param([string]$Token)
    $body = @{ force = [bool]$Force } | ConvertTo-Json -Compress
    return Invoke-RestMethod `
        -Uri "http://127.0.0.1:$Port/api/internal/maintenance/automatic-backup" `
        -Method Post `
        -Headers @{ "X-Lomoto-Maintenance-Token" = $Token } `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 30
}

try {
    Write-MaintenanceLog "Demarrage sauvegarde quotidienne. Force=$([bool]$Force)."
    $token = Get-MaintenanceToken
    try {
        $result = Invoke-BackupApi -Token $token
    }
    catch {
        Write-MaintenanceLog "Premier appel API en echec: $($_.Exception.Message)"
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service -and $service.Status -ne "Running") {
            Start-Service -Name $ServiceName
            (Get-Service -Name $ServiceName).WaitForStatus("Running", [TimeSpan]::FromSeconds(45))
            Start-Sleep -Seconds 5
        }
        $result = Invoke-BackupApi -Token $token
    }

    Write-MaintenanceLog "OK: $($result.message) $($result.path)"
    $result | ConvertTo-Json -Depth 5
    exit 0
}
catch {
    Write-MaintenanceLog "ECHEC: $($_.Exception.Message)"
    Write-Error $_.Exception.Message
    exit 1
}
