param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [string]$Region = "europe-west1",
    [string]$Repository = "boulangerie-lomoto",
    [string]$Service = "boulangerie-lomoto-api",
    [string]$SecretName = "boulangerie-api-token",
    [string]$ServiceAccount = "",
    [int]$MaxInstances = 1,
    [switch]$RotateApiToken,
    [switch]$AllowEphemeralSqlite
)

$ErrorActionPreference = "Stop"

function Assert-LastCommandSucceeded {
    param([string]$Action)
    if ($LASTEXITCODE -ne 0) {
        throw "$Action a echoue (code $LASTEXITCODE)."
    }
}

function New-UrlSafeToken {
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    return ([Convert]::ToBase64String($bytes)).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Get-ApplicationVersion {
    $versionFile = Join-Path (Split-Path -Parent $PSScriptRoot) "boulangerie_app\version.py"
    $content = Get-Content -LiteralPath $versionFile -Raw -Encoding UTF8
    if ($content -notmatch 'BOULANGERIE_APP_VERSION"\s*,\s*"([0-9]+\.[0-9]+\.[0-9]+)"') {
        throw "Impossible de lire la version de l'application dans $versionFile."
    }
    return $matches[1]
}

if (-not $AllowEphemeralSqlite) {
    throw (
        "Deploiement bloque : SQLite sur Cloud Run n'est pas un stockage persistant. " +
        "Utilisez -AllowEphemeralSqlite uniquement pour une recette jetable, jamais pour les donnees de production."
    )
}
if ($MaxInstances -lt 1 -or $MaxInstances -gt 10) {
    throw "MaxInstances doit etre compris entre 1 et 10."
}
if ([string]::IsNullOrWhiteSpace($SecretName)) {
    throw "SecretName est obligatoire."
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$appVersion = Get-ApplicationVersion
$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/${Service}:$appVersion"

Push-Location $root
try {
    & gcloud config set project $ProjectId
    Assert-LastCommandSucceeded "La selection du projet Google Cloud"

    & gcloud services enable `
        run.googleapis.com `
        cloudbuild.googleapis.com `
        artifactregistry.googleapis.com `
        secretmanager.googleapis.com
    Assert-LastCommandSucceeded "L'activation des API Google Cloud"

    $repos = @(& gcloud artifacts repositories list --location $Region --format="value(name)")
    Assert-LastCommandSucceeded "La lecture des depots Artifact Registry"
    if ($repos -notcontains $Repository) {
        & gcloud artifacts repositories create $Repository `
            --repository-format=docker `
            --location=$Region `
            --description="Images Boulangerie Lomoto"
        Assert-LastCommandSucceeded "La creation du depot Artifact Registry"
    }

    & gcloud secrets describe $SecretName --format="value(name)" 2>$null | Out-Null
    $secretExists = $LASTEXITCODE -eq 0
    if (-not $secretExists) {
        $newToken = New-UrlSafeToken
        $newToken | & gcloud secrets create $SecretName `
            --replication-policy=automatic `
            --data-file=- | Out-Null
        Assert-LastCommandSucceeded "La creation du secret API"
        $newToken = $null
    }
    elseif ($RotateApiToken) {
        $newToken = New-UrlSafeToken
        $newToken | & gcloud secrets versions add $SecretName --data-file=- | Out-Null
        Assert-LastCommandSucceeded "La rotation du secret API"
        $newToken = $null
    }

    $secretVersion = (& gcloud secrets versions list $SecretName `
        --filter="state=ENABLED" `
        --sort-by="~createTime" `
        --limit=1 `
        --format="value(name)").Trim()
    Assert-LastCommandSucceeded "La lecture de la version du secret API"
    if ([string]::IsNullOrWhiteSpace($secretVersion)) {
        throw "Le secret $SecretName ne contient aucune version active."
    }
    if ($secretVersion.Contains("/")) {
        $secretVersion = $secretVersion.Split("/")[-1]
    }

    if ([string]::IsNullOrWhiteSpace($ServiceAccount)) {
        $projectNumber = (& gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
        Assert-LastCommandSucceeded "La lecture du numero de projet"
        $ServiceAccount = "$projectNumber-compute@developer.gserviceaccount.com"
    }

    & gcloud secrets add-iam-policy-binding $SecretName `
        --member="serviceAccount:$ServiceAccount" `
        --role="roles/secretmanager.secretAccessor" | Out-Null
    Assert-LastCommandSucceeded "L'autorisation Secret Manager du compte de service"

    & gcloud builds submit `
        --config cloud-run/cloudbuild.yaml `
        --substitutions "_REGION=$Region,_REPOSITORY=$Repository,_SERVICE=$Service,_TAG=$appVersion" `
        .
    Assert-LastCommandSucceeded "La construction de l'image Cloud Run"

    $envVars = "BOULANGERIE_APP_VERSION=$appVersion,BOULANGERIE_REQUIRE_SESSION_AUTH=1,BOULANGERIE_REQUIRE_CONFIGURED_API_TOKEN=1"
    $secretBinding = "BOULANGERIE_API_TOKEN=${SecretName}:$secretVersion"
    & gcloud run deploy $Service `
        --image $image `
        --region $Region `
        --platform managed `
        --service-account $ServiceAccount `
        --allow-unauthenticated `
        --cpu-throttling `
        --min-instances 0 `
        --max-instances $MaxInstances `
        --concurrency 20 `
        --memory 512Mi `
        --set-env-vars $envVars `
        --set-secrets $secretBinding
    Assert-LastCommandSucceeded "Le deploiement Cloud Run"
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "API Cloud Run de recette publiee en version $appVersion." -ForegroundColor Green
Write-Host "Jeton stocke dans Secret Manager : $SecretName (version $secretVersion)."
Write-Host "SQLite reste ephemere : ne saisissez aucune donnee reelle dans cette instance." -ForegroundColor Yellow
