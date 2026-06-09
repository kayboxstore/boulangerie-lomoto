param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$ConfigureScript = Join-Path $PSScriptRoot "configure_production_cloudflare.py"

Set-Location $Root

Write-Host ""
Write-Host "Deploiement public de Boulangerie Lomoto" -ForegroundColor Cyan
Write-Host "Le jeton reste uniquement en memoire pendant cette operation."
Write-Host ""

Write-Host "1. Dans Cloudflare, copiez le jeton complet avec le bouton Copier."
Write-Host "2. Revenez dans cette fenetre."
Write-Host "3. Ne collez rien ici : appuyez simplement sur Entree." -ForegroundColor Yellow
Write-Host ""
Read-Host "Appuyez sur Entree quand le jeton est dans le presse-papiers"

try {
    $clipboardToken = (Get-Clipboard -Raw).Trim()
    if ($clipboardToken -match "\s") {
        throw "Le presse-papiers contient des espaces ou plusieurs lignes. Recopiez uniquement le jeton Cloudflare."
    }
    if ($clipboardToken.Length -lt 40) {
        throw "Le jeton copie semble incomplet ($($clipboardToken.Length) caracteres). Recopiez-le depuis Cloudflare."
    }

    $env:CLOUDFLARE_API_TOKEN = $clipboardToken
    $env:BOULANGERIE_SKIP_CLOUDFLARED_SERVICE = "1"
    if (-not (Test-Path -LiteralPath $Python)) {
        throw "Python du projet introuvable : $Python"
    }

    & $Python $ConfigureScript
    if ($LASTEXITCODE -ne 0) {
        throw "La configuration Cloudflare a echoue."
    }

    Write-Host ""
    Write-Host "Le domaine est relie au tunnel Cloudflare." -ForegroundColor Green
    Write-Host "Adresse principale : https://app.boulangerie-lomoto.com"
    Write-Host "Adresse courte      : https://boulangerie-lomoto.com"
}
catch {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Aucun jeton n'a ete enregistre dans le projet." -ForegroundColor Yellow
}
finally {
    Set-Clipboard -Value ""
    Remove-Item Env:CLOUDFLARE_API_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:BOULANGERIE_SKIP_CLOUDFLARED_SERVICE -ErrorAction SilentlyContinue
    $clipboardToken = $null
    [GC]::Collect()
}

Write-Host ""
Read-Host "Appuyez sur Entree pour fermer cette fenetre"
