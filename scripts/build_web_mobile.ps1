$ErrorActionPreference = "Stop"

. "$PSScriptRoot\tool_paths.ps1"

Push-Location "$PSScriptRoot\..\web-mobile-app"
try {
    Invoke-Tool -Candidates @("npm.cmd", "npm") -Arguments @("install")
    Invoke-Tool -Candidates @("npm.cmd", "npm") -Arguments @("run", "build")
}
finally {
    Pop-Location
}

Write-Host "Build web termine : web-mobile-app\dist" -ForegroundColor Green
