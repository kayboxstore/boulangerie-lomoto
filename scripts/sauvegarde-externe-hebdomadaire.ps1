param(
    [string]$DestinationRoot = ""
)

$ErrorActionPreference = "Stop"

$ProgramDataRoot = "C:\ProgramData\BoulangerieLomoto"
$SourceRoot = Join-Path $ProgramDataRoot "central-server-data"
$LogPath = Join-Path $ProgramDataRoot "sauvegarde-externe-hebdomadaire.log"
$RetentionCount = 12

function Write-BackupLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "[$timestamp] $Message"
}

function Get-DriveRoot {
    param([string]$DriveLetter)
    return "${DriveLetter}:\"
}

function Resolve-DestinationRoot {
    param([string]$RequestedRoot)

    if (-not [string]::IsNullOrWhiteSpace($RequestedRoot)) {
        New-Item -ItemType Directory -Force -Path $RequestedRoot | Out-Null
        return (Resolve-Path -LiteralPath $RequestedRoot).Path
    }

    $preferredLabels = @("LOMOTO_BACKUP", "BOULANGERIE_BACKUP")
    $volumes = @(Get-Volume -ErrorAction SilentlyContinue | Where-Object { $_.DriveLetter })

    foreach ($label in $preferredLabels) {
        $volume = $volumes | Where-Object { $_.FileSystemLabel -eq $label } | Select-Object -First 1
        if ($volume) {
            return (Get-DriveRoot $volume.DriveLetter)
        }
    }

    foreach ($volume in $volumes) {
        if ($volume.DriveLetter -eq "C") {
            continue
        }
        $root = Get-DriveRoot $volume.DriveLetter
        $backupFolder = Join-Path $root "BoulangerieLomoto-Backups"
        if (Test-Path -LiteralPath $backupFolder) {
            return (Resolve-Path -LiteralPath $backupFolder).Path
        }
        if (Test-Path -LiteralPath (Join-Path $root "LOMOTO_BACKUP.marker")) {
            return $root
        }
    }

    $removable = Get-CimInstance Win32_LogicalDisk |
        Where-Object { $_.DriveType -eq 2 -and $_.DeviceID -ne "C:" } |
        Select-Object -First 1
    if ($removable) {
        return "$($removable.DeviceID)\"
    }

    throw "Aucun disque externe detecte. Branchez un disque USB nomme LOMOTO_BACKUP ou indiquez -DestinationRoot."
}

try {
    New-Item -ItemType Directory -Force -Path $ProgramDataRoot | Out-Null
    Write-BackupLog "Demarrage de la sauvegarde hebdomadaire externe."

    if (-not (Test-Path -LiteralPath $SourceRoot)) {
        throw "Dossier source introuvable: $SourceRoot"
    }

    $destinationRoot = Resolve-DestinationRoot $DestinationRoot
    $backupRoot = Join-Path $destinationRoot "BoulangerieLomoto\SauvegardesHebdomadaires"
    $timestamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
    $target = Join-Path $backupRoot $timestamp
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    $items = @(
        "boulangerie.db",
        "rapports",
        "sauvegardes",
        "cloudflare-tunnel",
        "email-settings.json"
    )

    foreach ($item in $items) {
        $source = Join-Path $SourceRoot $item
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
        }
    }

    $serverSettings = Join-Path $ProgramDataRoot "server-host-settings.json"
    if (Test-Path -LiteralPath $serverSettings) {
        Copy-Item -LiteralPath $serverSettings -Destination $target -Force
    }

    $hashes = @()
    Get-ChildItem -LiteralPath $target -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $relativePath = $_.FullName.Substring($target.Length).TrimStart("\")
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        $hashes += [ordered]@{
            path = $relativePath
            sha256 = $hash.Hash
            bytes = $_.Length
        }
    }

    $manifest = [ordered]@{
        createdAt = (Get-Date).ToString("s")
        computer = $env:COMPUTERNAME
        source = $SourceRoot
        destination = $target
        retentionCount = $RetentionCount
        fileHashes = $hashes
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $target "manifest.json") -Encoding UTF8

    $oldBackups = Get-ChildItem -LiteralPath $backupRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $RetentionCount
    foreach ($oldBackup in $oldBackups) {
        Remove-Item -LiteralPath $oldBackup.FullName -Recurse -Force
        Write-BackupLog "Ancienne sauvegarde supprimee: $($oldBackup.FullName)"
    }

    Write-BackupLog "Sauvegarde terminee: $target"
    Write-Output "Sauvegarde terminee: $target"
    exit 0
}
catch {
    Write-BackupLog "ECHEC: $($_.Exception.Message)"
    Write-Error $_.Exception.Message
    exit 1
}
