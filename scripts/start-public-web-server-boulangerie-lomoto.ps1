param(
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"

$ScriptPath = Join-Path $PSScriptRoot "start-web-pro-boulangerie-lomoto.ps1"
& $ScriptPath -Port $Port -HostAddress "0.0.0.0" -NoBrowser

Write-Host ""
Write-Host "Le serveur web local est prêt pour Cloudflare Tunnel."
Write-Host "Service local à exposer : http://127.0.0.1:$Port"
Write-Host "Domaine prévu : https://boulangerie-lomoto.com"
