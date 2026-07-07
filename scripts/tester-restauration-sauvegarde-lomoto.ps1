param(
    [string]$BackupPath = ""
)

$ErrorActionPreference = "Stop"

$ProgramDataRoot = Join-Path $env:ProgramData "BoulangerieLomoto"
$BackupRoot = Join-Path $ProgramDataRoot "central-server-data\sauvegardes"
$MaintenanceRoot = Join-Path $ProgramDataRoot "maintenance"
$LogPath = Join-Path $MaintenanceRoot "test-restauration.log"

function Write-MaintenanceLog {
    param([string]$Message)
    New-Item -ItemType Directory -Force -Path $MaintenanceRoot | Out-Null
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "[$timestamp] $Message"
}

try {
    if ([string]::IsNullOrWhiteSpace($BackupPath)) {
        $latest = Get-ChildItem -LiteralPath $BackupRoot -Filter "*.db" -File -ErrorAction Stop |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if (-not $latest) {
            throw "Aucune sauvegarde .db trouvee dans $BackupRoot."
        }
        $BackupPath = $latest.FullName
    }
    if (-not (Test-Path -LiteralPath $BackupPath)) {
        throw "Sauvegarde introuvable: $BackupPath"
    }

    $testDir = Join-Path $env:TEMP ("lomoto-restore-test-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Force -Path $testDir | Out-Null
    $copyPath = Join-Path $testDir "boulangerie-test.db"
    Copy-Item -LiteralPath $BackupPath -Destination $copyPath -Force

    $python = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $python) {
        $python = Get-Command py -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if (-not $python) {
        throw "Python introuvable pour verifier l'integrite SQLite."
    }

    $checkCode = @"
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(db)
try:
    result = con.execute("PRAGMA integrity_check").fetchone()[0]
    tables = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
finally:
    con.close()
if result != "ok" or tables < 5:
    raise SystemExit(f"Integrity={result}; tables={tables}")
print(f"OK integrity={result}; tables={tables}")
"@
    $checkFile = Join-Path $testDir "check_sqlite.py"
    Set-Content -LiteralPath $checkFile -Value $checkCode -Encoding UTF8
    if ($python.Name -eq "py.exe") {
        & $python.Source -3 $checkFile $copyPath
    }
    else {
        & $python.Source $checkFile $copyPath
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Controle SQLite echoue."
    }

    Write-MaintenanceLog "OK test restauration: $BackupPath"
    Write-Host "Test de restauration OK : $BackupPath" -ForegroundColor Green
    Write-Host "Copie controlee : $copyPath"
    exit 0
}
catch {
    Write-MaintenanceLog "ECHEC: $($_.Exception.Message)"
    Write-Error $_.Exception.Message
    exit 1
}
