param(
    [int]$ApiPort = 8765,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $Root "web-mobile-app"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

function Test-PortOpen {
    param([int]$Port)
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $result = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $success = $result.AsyncWaitHandle.WaitOne(400)
        if ($success) {
            $client.EndConnect($result)
        }
        $client.Close()
        return $success
    } catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $WebRoot)) {
    throw "Le dossier web-mobile-app est introuvable : $WebRoot"
}

if (-not (Test-PortOpen -Port $ApiPort)) {
    $apiCommand = "Set-Location '$Root'; & '$Python' serveur_central.py --host 0.0.0.0 --port $ApiPort"
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $apiCommand) -WindowStyle Minimized
    Write-Host "Serveur central en démarrage sur http://127.0.0.1:$ApiPort"
} else {
    Write-Host "Serveur central déjà actif sur http://127.0.0.1:$ApiPort"
}

if (-not (Test-Path -LiteralPath (Join-Path $WebRoot "node_modules"))) {
    Write-Host "Installation des dépendances web..."
    Push-Location $WebRoot
    npm.cmd install
    Pop-Location
}

$webCommand = "Set-Location '$WebRoot'; npm.cmd run dev -- --host 0.0.0.0 --port $WebPort"
Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $webCommand) -WindowStyle Minimized

Start-Sleep -Seconds 4
$url = "http://127.0.0.1:$WebPort"
Start-Process $url
Write-Host "Version web ouverte : $url"
Write-Host "Identifiant admin : a.kayembe"
Write-Host "Mot de passe admin : 010203"
