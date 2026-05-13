param(
    [string]$GitHubUsername = "kayboxstore",
    [string]$AppRepoName = "boulangerie-lomoto",
    [string]$UpdatesRepoName = "boulangerie-lomoto-updates"
)

$ErrorActionPreference = "Stop"

function Resolve-CommandPath {
    param(
        [string]$Name,
        [string[]]$FallbackPaths = @()
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    foreach ($fallbackPath in $FallbackPaths) {
        if (Test-Path $fallbackPath) {
            return $fallbackPath
        }
    }

    return $null
}

function Require-Command {
    param(
        [string]$Name,
        [string[]]$FallbackPaths = @()
    )

    $resolvedPath = Resolve-CommandPath -Name $Name -FallbackPaths $FallbackPaths
    if (-not $resolvedPath) {
        throw "L'outil '$Name' n'est pas installe ou n'est pas disponible dans le PATH."
    }

    Set-Alias -Name $Name -Value $resolvedPath -Scope Script
}

function Get-ProjectRoot {
    Split-Path -Parent $PSScriptRoot
}

function Get-VenvPython {
    $root = Get-ProjectRoot
    $pythonPath = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $pythonPath)) {
        throw "Python du venv introuvable : $pythonPath"
    }
    return $pythonPath
}

function Get-AppVersion {
    $python = Get-VenvPython
    $root = Get-ProjectRoot
    $version = & $python -c "from boulangerie_app.version import APP_VERSION; print(APP_VERSION)" 2>$null
    if (-not $version) {
        throw "Impossible de lire APP_VERSION."
    }
    return $version.Trim()
}

function Ensure-GhAuth {
    $authenticated = $true
    try {
        gh auth status | Out-Null
    }
    catch {
        $authenticated = $false
    }

    if (-not $authenticated) {
        Write-Host "Connexion GitHub requise. Ouverture de l'authentification..." -ForegroundColor Yellow
        gh auth login --web --git-protocol https
        gh auth status | Out-Null
    }
}

function Get-GitHubLogin {
    $login = gh api user --jq ".login"
    if (-not $login) {
        throw "Impossible de lire le nom d'utilisateur GitHub authentifie."
    }
    return $login.Trim()
}

function Get-GitHubUserId {
    $userId = gh api user --jq ".id"
    if (-not $userId) {
        throw "Impossible de lire l'identifiant GitHub authentifie."
    }
    return $userId.ToString().Trim()
}

function Ensure-GitRepo {
    param([string]$RootPath)

    Push-Location $RootPath
    try {
        if (-not (Test-Path (Join-Path $RootPath ".git"))) {
            git init
            git branch -M main
        }
    }
    finally {
        Pop-Location
    }
}

function Ensure-LocalGitIdentity {
    param([string]$RepoPath)

    Push-Location $RepoPath
    try {
        $currentName = (git config user.name) 2>$null
        $currentEmail = (git config user.email) 2>$null

        if ($currentName -and $currentEmail) {
            return
        }

        $login = Get-GitHubLogin
        $userId = Get-GitHubUserId

        if (-not $currentName) {
            git config user.name $login
        }

        if (-not $currentEmail) {
            git config user.email "$userId+$login@users.noreply.github.com"
        }
    }
    finally {
        Pop-Location
    }
}

function Ensure-GhRepo {
    param(
        [string]$RepoName,
        [string]$SourcePath,
        [switch]$PublicRepo
    )

    $visibility = if ($PublicRepo) { "--public" } else { "--private" }

    Push-Location $SourcePath
    try {
        $remote = ""
        try {
            $remote = (git remote get-url origin) 2>$null
        }
        catch {
            $remote = ""
        }

        if (-not $remote) {
            gh repo create "$GitHubUsername/$RepoName" $visibility --source . --remote origin --push
        }
    }
    finally {
        Pop-Location
    }
}

function Commit-And-Push {
    param(
        [string]$RepoPath,
        [string]$Message
    )

    Push-Location $RepoPath
    try {
        git add .

        $status = git status --porcelain
        if ($status) {
            git commit -m $Message
        }

        git branch -M main
        git push -u origin main
    }
    finally {
        Pop-Location
    }
}

function Update-ManifestFile {
    param(
        [string]$ManifestPath,
        [string]$Version,
        [string]$DownloadUrl
    )

    $payload = @{
        version = $Version
        download_url = $DownloadUrl
        published_at = (Get-Date).ToString("yyyy-MM-dd")
        notes = "Publication de la version $Version."
    }

    $payload | ConvertTo-Json | Set-Content -Path $ManifestPath -Encoding UTF8
}

function Publish-UpdatesRepo {
    param(
        [string]$Version,
        [string]$DownloadUrl
    )

    $root = Get-ProjectRoot
    $publishRoot = Join-Path $root ".github-publish\$UpdatesRepoName"
    $sourceRoot = Join-Path $root "github-pages"

    if (Test-Path $publishRoot) {
        Remove-Item -Recurse -Force $publishRoot
    }

    New-Item -ItemType Directory -Path $publishRoot | Out-Null
    Get-ChildItem -Path $sourceRoot -Force | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $publishRoot -Recurse -Force
    }

    $manifestPath = Join-Path $publishRoot "update.json"
    Update-ManifestFile -ManifestPath $manifestPath -Version $Version -DownloadUrl $DownloadUrl

    Ensure-GitRepo -RootPath $publishRoot
    Ensure-LocalGitIdentity -RepoPath $publishRoot
    Ensure-GhRepo -RepoName $UpdatesRepoName -SourcePath $publishRoot -PublicRepo
    Commit-And-Push -RepoPath $publishRoot -Message "Publish update manifest $Version"
}

function Publish-AppRepo {
    param([string]$Version)

    $root = Get-ProjectRoot
    Ensure-GitRepo -RootPath $root
    Ensure-LocalGitIdentity -RepoPath $root
    Ensure-GhRepo -RepoName $AppRepoName -SourcePath $root -PublicRepo
    Commit-And-Push -RepoPath $root -Message "Publish app version $Version"
}

function Ensure-GitHubPages {
    $apiPath = "repos/$GitHubUsername/$UpdatesRepoName/pages"
    $headers = @(
        "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2026-03-10"
    )

    $siteExists = $true
    try {
        gh api $apiPath @headers | Out-Null
    }
    catch {
        $siteExists = $false
    }

    if ($siteExists) {
        gh api --method PUT $apiPath @headers --field "source[branch]=main" --field "source[path]=/"
    }
    else {
        gh api --method POST $apiPath @headers --field "source[branch]=main" --field "source[path]=/"
    }
}

function Publish-Release {
    param([string]$Version)

    $root = Get-ProjectRoot
    $setupPath = Join-Path $root "installer\output\BoulangerieLomotoSetup.exe"

    if (-not (Test-Path $setupPath)) {
        Write-Warning "Setup introuvable : $setupPath"
        Write-Warning "La release GitHub ne sera pas creee tant que le setup n'existe pas."
        return
    }

    Push-Location $root
    try {
        $tag = "v$Version"
        $releaseViewSucceeded = $true
        try {
            gh release view $tag | Out-Null
        }
        catch {
            $releaseViewSucceeded = $false
        }

        if (-not $releaseViewSucceeded) {
            gh release create $tag $setupPath --title $tag --notes "Publication de la version $Version"
        }
        else {
            gh release upload $tag $setupPath --clobber
        }
    }
    finally {
        Pop-Location
    }
}

Require-Command git -FallbackPaths @("C:\Program Files\Git\cmd\git.exe")
Require-Command gh -FallbackPaths @("C:\Program Files\GitHub CLI\gh.exe")
Ensure-GhAuth

$version = Get-AppVersion
$downloadUrl = "https://github.com/$GitHubUsername/$AppRepoName/releases/latest/download/BoulangerieLomotoSetup.exe"

Publish-AppRepo -Version $version
Publish-Release -Version $version
Publish-UpdatesRepo -Version $version -DownloadUrl $downloadUrl
Ensure-GitHubPages

Write-Host ""
Write-Host "Publication terminee." -ForegroundColor Green
Write-Host "Application : https://github.com/$GitHubUsername/$AppRepoName"
Write-Host "Manifeste : https://$GitHubUsername.github.io/$UpdatesRepoName/update.json"
