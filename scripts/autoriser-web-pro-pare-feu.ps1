param(
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"
$RuleName = "Boulangerie Lomoto Web Pro $Port"
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
$IsAdmin = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $IsAdmin) {
    $Arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-Port", "$Port"
    )
    Start-Process -FilePath "powershell.exe" -ArgumentList $Arguments -Verb RunAs
    exit
}

Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule -ErrorAction SilentlyContinue

New-NetFirewallRule `
    -DisplayName $RuleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $Port `
    -Profile Private | Out-Null

Write-Host "Accès réseau autorisé pour le port TCP $Port."
Read-Host "Appuyez sur Entrée pour fermer"
