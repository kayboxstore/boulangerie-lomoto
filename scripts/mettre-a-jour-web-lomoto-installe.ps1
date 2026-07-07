$ErrorActionPreference = "Stop"

function Test-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
  $scriptPath = $PSCommandPath
  if (-not $scriptPath) {
    $scriptPath = $MyInvocation.MyCommand.Path
  }
  Start-Process `
    -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath) `
    -Verb RunAs
  return
}

$source = "A:\Mon application python\boulangerie_web_pro\static"
$destination = "C:\Program Files\Boulangerie Lomoto\_internal\boulangerie_web_pro\static"
$log = "A:\Mon application python\logs\mise-a-jour-web-lomoto-installe.log"
$serviceName = "BoulangerieLomotoCentralServer"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Mise a jour des fichiers web installes." | Out-File -LiteralPath $log -Encoding UTF8

if (-not (Test-Path -LiteralPath $destination)) {
  throw "Dossier web installe introuvable : $destination"
}

$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
$wasRunning = $false
if ($service -and $service.Status -eq "Running") {
  $wasRunning = $true
  "Arret du service $serviceName..." | Out-File -LiteralPath $log -Encoding UTF8 -Append
  Stop-Service -Name $serviceName -Force
  (Get-Service -Name $serviceName).WaitForStatus("Stopped", "00:00:20")
}

try {
  foreach ($file in @("app.js", "styles.css", "index.html", "service-worker.js", "manifest.webmanifest", "politique-confidentialite.html")) {
    $sourceFile = Join-Path $source $file
    if (Test-Path -LiteralPath $sourceFile) {
      Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $destination $file) -Force
      "Copie: $file" | Out-File -LiteralPath $log -Encoding UTF8 -Append
    }
  }
} finally {
  if ($service -and $wasRunning) {
    "Redemarrage du service $serviceName..." | Out-File -LiteralPath $log -Encoding UTF8 -Append
    Start-Service -Name $serviceName
    (Get-Service -Name $serviceName).WaitForStatus("Running", "00:00:30")
    "Service $serviceName redemarre." | Out-File -LiteralPath $log -Encoding UTF8 -Append
  }
}

"Mise a jour terminee." | Out-File -LiteralPath $log -Encoding UTF8 -Append
