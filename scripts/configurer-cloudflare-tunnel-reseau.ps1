param(
    [string]$ProxyUrl = "",
    [switch]$ClearProxy,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`""
    )
    if ($ProxyUrl) {
        $arguments += @("-ProxyUrl", "`"$ProxyUrl`"")
    }
    if ($ClearProxy) {
        $arguments += "-ClearProxy"
    }
    if ($NoRestart) {
        $arguments += "-NoRestart"
    }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments
    exit
}

Write-Host ""
Write-Host "Configuration reseau Cloudflare Tunnel - Boulangerie Lomoto" -ForegroundColor Cyan
Write-Host ""

# HTTP/2 passe mieux avec les VPN, proxys et reseaux qui bloquent QUIC/UDP 7844.
[Environment]::SetEnvironmentVariable("TUNNEL_TRANSPORT_PROTOCOL", "http2", "Machine")

# IPv4 evite les bascules IPv6 instables souvent observees derriere VPN/proxy.
[Environment]::SetEnvironmentVariable("TUNNEL_EDGE_IP_VERSION", "4", "Machine")

if ($ClearProxy) {
    [Environment]::SetEnvironmentVariable("HTTPS_PROXY", $null, "Machine")
    [Environment]::SetEnvironmentVariable("HTTP_PROXY", $null, "Machine")
    Write-Host "Proxy systeme Cloudflare Tunnel : efface." -ForegroundColor Yellow
}
elseif ($ProxyUrl.Trim()) {
    $proxy = $ProxyUrl.Trim()
    [Environment]::SetEnvironmentVariable("HTTPS_PROXY", $proxy, "Machine")
    [Environment]::SetEnvironmentVariable("HTTP_PROXY", $proxy, "Machine")
    Write-Host "Proxy systeme Cloudflare Tunnel : $proxy" -ForegroundColor Green
}

Write-Host "Transport Cloudflare Tunnel : http2" -ForegroundColor Green
Write-Host "Version IP Cloudflare Edge  : IPv4" -ForegroundColor Green

if (-not $NoRestart) {
    Write-Host ""
    Write-Host "Redemarrage du tunnel Cloudflare..." -ForegroundColor Cyan
    Restart-Service -Name Cloudflared -Force
    Start-Sleep -Seconds 8
}

Write-Host ""
Write-Host "Verification des services..." -ForegroundColor Cyan
Get-CimInstance Win32_Service -Filter "Name='Cloudflared' OR Name='BoulangerieLomotoCentralServer'" |
    Select-Object Name, State, StartMode, ProcessId |
    Format-Table -AutoSize

Write-Host ""
Write-Host "Test local..." -ForegroundColor Cyan
try {
    $local = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8787/api/health" -TimeoutSec 8
    Write-Host $local.Content -ForegroundColor Green
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Write-Host ""
Write-Host "Test public..." -ForegroundColor Cyan
try {
    $public = Invoke-WebRequest -UseBasicParsing -Uri "https://boulangerie-lomoto.com/api/health" -TimeoutSec 20
    Write-Host "$($public.StatusCode) $($public.Content)" -ForegroundColor Green
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
}

