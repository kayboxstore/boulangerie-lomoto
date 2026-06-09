$ErrorActionPreference = "Continue"

. "$PSScriptRoot\tool_paths.ps1"

function Test-Tool {
    param(
        [string]$Name,
        [string[]]$Candidates,
        [string[]]$Arguments = @()
    )

    Write-Host ""
    Write-Host "[$Name]"
    try {
        Invoke-Tool -Candidates $Candidates -Arguments $Arguments
        Write-Host "OK" -ForegroundColor Green
    }
    catch {
        Write-Host "Manquant ou inutilisable : $($_.Exception.Message)" -ForegroundColor Red
    }
}

Test-Tool "Node.js" @("node.exe", "node") @("--version")
Test-Tool "npm" @("npm.cmd", "npm") @("--version")
Test-Tool "Google Cloud CLI" @("gcloud.cmd", "gcloud") @("--version")
Test-Tool "Firebase CLI" @("firebase.cmd", "firebase") @("--version")
Test-Tool "Java" @("java.exe", "java") @("-version")

Write-Host ""
Write-Host "Pour generer l'APK, Android Studio et le SDK Android doivent aussi etre installes." -ForegroundColor Yellow
