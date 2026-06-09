param(
    [string]$Repository = "kayboxstore/boulangerie-lomoto-updates"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$sourcePath = Join-Path $root "outputs\cloudflared-temporary-tunnel.json"
if (-not (Test-Path $sourcePath)) {
    throw "Lancez d'abord start-temporary-cloudflare-tunnel.ps1."
}

$content = Get-Content -LiteralPath $sourcePath -Raw
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($content))
$existing = gh api "repos/$Repository/contents/server.json" | ConvertFrom-Json
gh api `
    --method PUT `
    "repos/$Repository/contents/server.json" `
    -f message="Publier le serveur Internet temporaire" `
    -f content="$encoded" `
    -f sha="$($existing.sha)" `
    -f branch="main"
