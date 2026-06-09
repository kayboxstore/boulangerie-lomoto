$ErrorActionPreference = "Stop"

. "$PSScriptRoot\tool_paths.ps1"

Push-Location "$PSScriptRoot\..\android-apk"
try {
    Invoke-Tool -Candidates @("npm.cmd", "npm") -Arguments @("install")
    Invoke-Tool -Candidates @("npm.cmd", "npm") -Arguments @("run", "build:web")
    Invoke-Tool -Candidates @("npm.cmd", "npm") -Arguments @("run", "add:android")
    Invoke-Tool -Candidates @("npm.cmd", "npm") -Arguments @("run", "sync")
}
finally {
    Pop-Location
}

Write-Host "Projet Android prepare. Ouvrez Android Studio avec : cd android-apk ; npm run open" -ForegroundColor Green
