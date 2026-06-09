param(
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$outputDir = Join-Path $root "outputs"
$logPath = Join-Path $outputDir "cloudflared-temporary-tunnel.log"
$errorLogPath = Join-Path $outputDir "cloudflared-temporary-tunnel-error.log"
$pidPath = Join-Path $outputDir "cloudflared-temporary-tunnel.pid"
$resultPath = Join-Path $outputDir "cloudflared-temporary-tunnel.json"
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) {
    $candidates = @(
        (Join-Path $env:ProgramFiles "cloudflared\cloudflared.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "cloudflared\cloudflared.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $cloudflared = $candidate
            break
        }
    }
}
if (-not $cloudflared) {
    throw "cloudflared n'est pas installé."
}

if (Test-Path $pidPath) {
    $oldPid = [int](Get-Content $pidPath -ErrorAction SilentlyContinue)
    if ($oldPid -gt 0) {
        Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
    }
}

Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $errorLogPath -Force -ErrorAction SilentlyContinue
$process = Start-Process `
    -FilePath $cloudflared `
    -ArgumentList @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port") `
    -WindowStyle Hidden `
    -RedirectStandardOutput $logPath `
    -RedirectStandardError $errorLogPath `
    -PassThru
$process.Id | Set-Content -LiteralPath $pidPath -Encoding ascii

$deadline = (Get-Date).AddSeconds(45)
$publicUrl = ""
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    $availableLogs = @($logPath, $errorLogPath) | Where-Object { Test-Path $_ }
    if ($availableLogs) {
        $match = Select-String -Path $availableLogs -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches |
            Select-Object -First 1
        if ($match) {
            $publicUrl = $match.Matches[0].Value
            break
        }
    }
    if ($process.HasExited) {
        throw "Le tunnel Cloudflare s'est arrêté. Consultez $logPath"
    }
}

if (-not $publicUrl) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "Cloudflare n'a pas fourni d'adresse publique dans le délai prévu."
}

$result = [ordered]@{
    enabled = $true
    required = $true
    label = "Serveur Internet temporaire Boulangerie Lomoto"
    server_url = $publicUrl
    api_token = ""
    updated_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
    notes = "Tunnel HTTPS temporaire de recette. L'adresse changera après un redémarrage."
}
$result | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding utf8
$result | ConvertTo-Json
