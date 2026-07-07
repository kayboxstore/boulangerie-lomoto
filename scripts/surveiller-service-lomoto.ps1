param(
    [int]$Port = 8787,
    [switch]$CheckPublic,
    [string]$PublicUrl = "https://boulangerie-lomoto.com/api/health",
    [ValidateRange(2, 12)]
    [int]$PublicFailureThreshold = 3
)

$ErrorActionPreference = "Stop"

$ProgramDataRoot = Join-Path $env:ProgramData "BoulangerieLomoto"
$DataRoot = Join-Path $ProgramDataRoot "central-server-data"
$MaintenanceRoot = Join-Path $ProgramDataRoot "maintenance"
$TokenPath = Join-Path $DataRoot "maintenance-token.txt"
$LogPath = Join-Path $MaintenanceRoot "surveillance-service.log"
$PublicHealthStatePath = Join-Path $MaintenanceRoot "public-health-state.json"
$ServiceName = "BoulangerieLomotoCentralServer"
$CloudflaredServiceName = "cloudflared"

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

function Test-LocalHealth {
    return Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 15
}

function Restart-LomotoService {
    Write-MaintenanceLog "Redemarrage du service $ServiceName."
    Restart-Service -Name $ServiceName -Force
    (Get-Service -Name $ServiceName).WaitForStatus("Running", [TimeSpan]::FromSeconds(60))
    Start-Sleep -Seconds 5
}

function Get-PublicHealthState {
    if (Test-Path -LiteralPath $PublicHealthStatePath) {
        try {
            return Get-Content -LiteralPath $PublicHealthStatePath -Raw -Encoding UTF8 |
                ConvertFrom-Json
        }
        catch {
            Write-MaintenanceLog "Etat de sante publique illisible, compteur reinitialise."
        }
    }
    return [pscustomobject]@{
        consecutiveFailures = 0
        lastFailureAt = ""
        lastSuccessAt = ""
    }
}

function Save-PublicHealthState {
    param(
        [int]$ConsecutiveFailures,
        [string]$LastFailureAt = "",
        [string]$LastSuccessAt = ""
    )
    New-Item -ItemType Directory -Force -Path $MaintenanceRoot | Out-Null
    [ordered]@{
        consecutiveFailures = $ConsecutiveFailures
        lastFailureAt = $LastFailureAt
        lastSuccessAt = $LastSuccessAt
    } | ConvertTo-Json | Set-Content -LiteralPath $PublicHealthStatePath -Encoding UTF8
}

function Restart-CloudflaredService {
    $service = Get-Service -Name $CloudflaredServiceName -ErrorAction Stop
    if ($service.Status -eq "Running") {
        Write-MaintenanceLog "Redemarrage de Cloudflare Tunnel apres $PublicFailureThreshold echecs publics consecutifs."
        Restart-Service -Name $CloudflaredServiceName -Force
    }
    else {
        Write-MaintenanceLog "Demarrage de Cloudflare Tunnel apres echec public."
        Start-Service -Name $CloudflaredServiceName
    }
    (Get-Service -Name $CloudflaredServiceName).WaitForStatus("Running", [TimeSpan]::FromSeconds(60))
    Start-Sleep -Seconds 8
}

try {
    $service = Get-Service -Name $ServiceName -ErrorAction Stop
    if ($service.Status -ne "Running") {
        Write-MaintenanceLog "Service arrete. Demarrage."
        Start-Service -Name $ServiceName
        (Get-Service -Name $ServiceName).WaitForStatus("Running", [TimeSpan]::FromSeconds(60))
        Start-Sleep -Seconds 5
    }

    try {
        $health = Test-LocalHealth
        if (-not $health.ok) {
            throw "Health local non OK."
        }
    }
    catch {
        Write-MaintenanceLog "Health local en echec: $($_.Exception.Message)"
        Restart-LomotoService
        $health = Test-LocalHealth
    }

    $cloudflared = Get-Service -Name $CloudflaredServiceName -ErrorAction SilentlyContinue
    if ($cloudflared -and $cloudflared.Status -ne "Running") {
        Write-MaintenanceLog "Cloudflare Tunnel arrete. Demarrage."
        Start-Service -Name $CloudflaredServiceName
    }

    $token = Get-MaintenanceToken
    try {
        $body = @{ limit = 20 } | ConvertTo-Json -Compress
        Invoke-RestMethod `
            -Uri "http://127.0.0.1:$Port/api/internal/maintenance/email-drain" `
            -Method Post `
            -Headers @{ "X-Lomoto-Maintenance-Token" = $token } `
            -ContentType "application/json" `
            -Body $body `
            -TimeoutSec 30 | Out-Null
    }
    catch {
        Write-MaintenanceLog "Traitement e-mail differe en echec: $($_.Exception.Message)"
    }

    if ($CheckPublic) {
        $publicState = Get-PublicHealthState
        try {
            $publicHealth = Invoke-RestMethod -Uri $PublicUrl -TimeoutSec 25
            if (-not $publicHealth.ok) {
                throw "Health public non OK."
            }
            Save-PublicHealthState `
                -ConsecutiveFailures 0 `
                -LastSuccessAt (Get-Date).ToString("s")
        }
        catch {
            $failureCount = [int]$publicState.consecutiveFailures + 1
            $failureAt = (Get-Date).ToString("s")
            Save-PublicHealthState `
                -ConsecutiveFailures $failureCount `
                -LastFailureAt $failureAt `
                -LastSuccessAt ([string]$publicState.lastSuccessAt)
            Write-MaintenanceLog "Health public inaccessible ($failureCount/$PublicFailureThreshold): $($_.Exception.Message)"

            if ($failureCount -ge $PublicFailureThreshold) {
                try {
                    Restart-CloudflaredService
                    $publicHealth = Invoke-RestMethod -Uri $PublicUrl -TimeoutSec 30
                    if (-not $publicHealth.ok) {
                        throw "Health public non OK apres redemarrage."
                    }
                    Save-PublicHealthState `
                        -ConsecutiveFailures 0 `
                        -LastSuccessAt (Get-Date).ToString("s")
                    Write-MaintenanceLog "Health public retabli apres redemarrage de Cloudflare Tunnel."
                }
                catch {
                    Save-PublicHealthState `
                        -ConsecutiveFailures 0 `
                        -LastFailureAt (Get-Date).ToString("s") `
                        -LastSuccessAt ([string]$publicState.lastSuccessAt)
                    Write-MaintenanceLog "Health public toujours inaccessible apres relance: $($_.Exception.Message)"
                }
            }
        }
    }

    Write-MaintenanceLog "OK: service local $($health.version)."
    exit 0
}
catch {
    Write-MaintenanceLog "ECHEC: $($_.Exception.Message)"
    Write-Error $_.Exception.Message
    exit 1
}
