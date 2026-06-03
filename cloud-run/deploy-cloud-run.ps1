param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [string]$Region = "europe-west1",
    [string]$Repository = "boulangerie-lomoto",
    [string]$Service = "boulangerie-lomoto-api",
    [string]$Token = "",
    [int]$MaxInstances = 1
)

$ErrorActionPreference = "Stop"

gcloud config set project $ProjectId
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

$repos = gcloud artifacts repositories list --location $Region --format="value(name)"
if ($repos -notcontains $Repository) {
    gcloud artifacts repositories create $Repository --repository-format=docker --location=$Region --description="Images Boulangerie Lomoto"
}

$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/${Service}:latest"
gcloud builds submit --config cloud-run/cloudbuild.yaml --substitutions "_REGION=$Region,_REPOSITORY=$Repository,_SERVICE=$Service" .

$envVars = "BOULANGERIE_APP_NAME=Boulangerie Lomoto,BOULANGERIE_APP_VERSION=1.3.18,BOULANGERIE_REQUIRE_SESSION_AUTH=1"
if ($Token.Trim()) {
    $envVars = "$envVars,BOULANGERIE_API_TOKEN=$Token"
}

gcloud run deploy $Service `
    --image $image `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --cpu-throttling `
    --min-instances 0 `
    --max-instances $MaxInstances `
    --concurrency 20 `
    --memory 512Mi `
    --set-env-vars $envVars

Write-Host ""
Write-Host "API Cloud Run publiee avec garde-fous de cout : min=0, max=$MaxInstances, facturation a la requete." -ForegroundColor Green
Write-Host "Copiez l'URL affichee par gcloud et collez-la dans web-mobile-app/.env.production."
