param(
    [int]$Port = 8787,
    [string]$HostAddress = "0.0.0.0",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

Set-Location $Root

Start-Process -FilePath $Python -ArgumentList @(
    "-m",
    "boulangerie_web_pro.server",
    "--host",
    $HostAddress,
    "--port",
    "$Port"
) -WindowStyle Hidden

Start-Sleep -Seconds 2
$Url = "http://127.0.0.1:$Port"
if (-not $NoBrowser) {
    Start-Process $Url
}

Write-Host "Version web professionnelle ouverte : $Url"
Write-Host "Adresse d'écoute : http://$HostAddress`:$Port"
Write-Host "Domaine prévu après configuration Cloudflare : https://boulangerie-lomoto.com"
$LanAddresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.AddressState -eq "Preferred"
    } |
    Select-Object -ExpandProperty IPAddress -Unique
foreach ($LanAddress in $LanAddresses) {
    Write-Host "Téléphone/tablette sur le même réseau : http://$LanAddress`:$Port"
}
