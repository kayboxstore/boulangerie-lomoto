$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$versionFile = Join-Path $root "boulangerie_app\version.py"
$content = Get-Content -Raw -LiteralPath $versionFile
if ($content -notmatch 'APP_VERSION\s*=\s*os\.environ\.get\("[^"]+",\s*"([^"]+)"\)') {
    throw "Version de l'application introuvable."
}

$version = $matches[1]
$apk = Join-Path $root "installer\output\android\$version\BoulangerieLomoto-$version-debug.apk"
if (-not (Test-Path $apk)) {
    throw "APK debug introuvable. Lancez d'abord .\scripts\build_android_apk.ps1."
}

$adbCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"),
    "adb.exe",
    "adb"
)

$adb = $null
foreach ($candidate in $adbCandidates) {
    if (Test-Path $candidate) {
        $adb = $candidate
        break
    }
    $command = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
        $adb = $command.Source
        break
    }
}

if (-not $adb) {
    throw "adb introuvable. Activez le SDK Android ou ouvrez Android Studio."
}

& $adb devices
& $adb install -r $apk
if ($LASTEXITCODE -ne 0) {
    throw "Installation Android echouee. Verifiez que le telephone est branche, deverrouille, et que le debogage USB est autorise."
}

Write-Host "APK installe sur le telephone Android connecte." -ForegroundColor Green
