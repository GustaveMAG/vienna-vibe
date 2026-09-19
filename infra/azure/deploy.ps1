<#
.SYNOPSIS
    Déploie le pipeline Vienna Vibe sur Azure.

.DESCRIPTION
    Crée cinq ressources et rien de plus :

      1. Azure Database for PostgreSQL Flexible Server  -> l'entrepôt
      2. Azure Container Registry                        -> héberge l'image
      3. Azure Key Vault                                 -> les secrets Spotify
      4. Container Apps Environment                      -> le socle d'exécution
      5. Container Apps Job (déclencheur cron horaire)   -> remplace Airflow

    Pourquoi un Container Apps Job et pas une VM avec Airflow : le pipeline
    tourne une minute par heure. Payer une machine allumée en permanence pour
    ça n'a aucun sens. Un job serverless facturé à la seconde d'exécution
    coûte quelques euros par mois, et Azure gère l'ordonnancement.

    Le script est idempotent : chaque commande vérifie d'abord l'existence de
    la ressource. On peut donc le relancer sans rien casser.

.EXAMPLE
    ./deploy.ps1 -SpotifyClientId "xxx" -SpotifyClientSecret "yyy" -SpotifyRefreshToken "zzz"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $SpotifyClientId,
    [Parameter(Mandatory = $true)] [string] $SpotifyClientSecret,
    [Parameter(Mandatory = $true)] [string] $SpotifyRefreshToken,

    [string] $ResourceGroup = "rg-vienna-vibe",
    [string] $Location      = "westeurope",
    [string] $Prefix        = "viennavibe",
    # Mot de passe administrateur PostgreSQL. Généré si non fourni.
    [string] $PostgresPassword = ""
)

$ErrorActionPreference = "Stop"

# Noms globalement uniques : Azure exige l'unicité pour le registre, le coffre
# et le serveur PostgreSQL. On dérive un suffixe stable de l'abonnement plutôt
# qu'un aléatoire, pour que relancer le script retombe sur les mêmes noms.
$subId   = (az account show --query id -o tsv)
$suffix  = (($subId -replace '[^0-9a-f]', '').Substring(0, 6))
$acrName = "$Prefix$suffix"                 # 5-50 caractères alphanumériques
$kvName  = "kv-$Prefix-$suffix"
$pgName  = "pg-$Prefix-$suffix"
$envName = "cae-$Prefix"
$jobName = "job-$Prefix-hourly"
$imageTag = "vienna-vibe:latest"

if (-not $PostgresPassword) {
    $PostgresPassword = -join ((48..57) + (65..90) + (97..122) + (35, 36, 37, 38) |
        Get-Random -Count 24 | ForEach-Object { [char]$_ })
    Write-Host "Mot de passe PostgreSQL généré (conserve-le) : $PostgresPassword" -ForegroundColor Yellow
}

function Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Exists($command) {
    $ErrorActionPreference = "Continue"
    $null = Invoke-Expression "$command 2>`$null"
    $ok = $LASTEXITCODE -eq 0
    $ErrorActionPreference = "Stop"
    return $ok
}

# ---------------------------------------------------------------------------
Step "Vérification des prérequis"
az version --output none
if (-not (Exists "az account show --output none")) {
    throw "Non connecté à Azure. Lance 'az login' puis relance ce script."
}
# L'extension containerapp n'est pas installée par défaut.
az extension add --name containerapp --upgrade --only-show-errors --output none
az provider register --namespace Microsoft.App --output none
az provider register --namespace Microsoft.OperationalInsights --output none
Write-Host "Abonnement : $(az account show --query name -o tsv)"

# ---------------------------------------------------------------------------
Step "Groupe de ressources : $ResourceGroup"
az group create --name $ResourceGroup --location $Location --output none

# ---------------------------------------------------------------------------
Step "PostgreSQL Flexible Server : $pgName"
if (Exists "az postgres flexible-server show -g $ResourceGroup -n $pgName --output none") {
    Write-Host "Déjà présent, on conserve."
} else {
    # Burstable B1ms : le palier le plus modeste, éligible à l'offre gratuite
    # douze mois. Largement suffisant pour quelques milliers de lignes par jour.
    az postgres flexible-server create `
        --resource-group $ResourceGroup `
        --name $pgName `
        --location $Location `
        --admin-user vienna `
        --admin-password $PostgresPassword `
        --tier Burstable `
        --sku-name Standard_B1ms `
        --storage-size 32 `
        --version 16 `
        --database-name vienna_vibe `
        --public-access 0.0.0.0 `
        --yes `
        --output none
}

$pgHost = "$pgName.postgres.database.azure.com"
$databaseUrl = "postgresql://vienna:$PostgresPassword@$pgHost:5432/vienna_vibe?sslmode=require"

# ---------------------------------------------------------------------------
Step "Key Vault : $kvName"
if (-not (Exists "az keyvault show -n $kvName --output none")) {
    az keyvault create --resource-group $ResourceGroup --name $kvName `
        --location $Location --enable-rbac-authorization true --output none
}
# Les secrets vivent ici, jamais dans le dépôt ni dans les variables du job.
$me = az ad signed-in-user show --query id -o tsv
az role assignment create --assignee $me `
    --role "Key Vault Secrets Officer" `
    --scope (az keyvault show -n $kvName --query id -o tsv) `
    --output none 2>$null
Start-Sleep -Seconds 10   # propagation du rôle

az keyvault secret set --vault-name $kvName --name "spotify-client-id"     --value $SpotifyClientId     --output none
az keyvault secret set --vault-name $kvName --name "spotify-client-secret" --value $SpotifyClientSecret --output none
az keyvault secret set --vault-name $kvName --name "spotify-refresh-token" --value $SpotifyRefreshToken --output none
az keyvault secret set --vault-name $kvName --name "database-url"          --value $databaseUrl         --output none
Write-Host "Quatre secrets enregistrés."

# ---------------------------------------------------------------------------
Step "Container Registry : $acrName"
if (-not (Exists "az acr show -n $acrName --output none")) {
    az acr create --resource-group $ResourceGroup --name $acrName `
        --sku Basic --admin-enabled true --output none
}

Step "Construction de l'image dans Azure"
# az acr build construit côté Azure : pas besoin de Docker installé en local.
Push-Location (Join-Path $PSScriptRoot "../..")
try {
    az acr build --registry $acrName --image $imageTag --file Dockerfile . --output none
} finally {
    Pop-Location
}
$acrServer   = az acr show -n $acrName --query loginServer -o tsv
$acrUser     = az acr credential show -n $acrName --query username -o tsv
$acrPassword = az acr credential show -n $acrName --query "passwords[0].value" -o tsv

# ---------------------------------------------------------------------------
Step "Container Apps Environment : $envName"
if (-not (Exists "az containerapp env show -g $ResourceGroup -n $envName --output none")) {
    az containerapp env create --resource-group $ResourceGroup --name $envName `
        --location $Location --output none
}

# ---------------------------------------------------------------------------
Step "Application du schéma (job ponctuel)"
# On applique les migrations avant de planifier le pipeline, sinon la première
# exécution horaire échouerait sur des tables absentes.
$migrateJob = "job-$Prefix-migrate"
if (-not (Exists "az containerapp job show -g $ResourceGroup -n $migrateJob --output none")) {
    az containerapp job create `
        --resource-group $ResourceGroup --name $migrateJob --environment $envName `
        --trigger-type Manual --replica-timeout 600 --replica-retry-limit 1 `
        --image "$acrServer/$imageTag" --cpu 0.5 --memory 1Gi `
        --registry-server $acrServer --registry-username $acrUser --registry-password $acrPassword `
        --secrets "database-url=$databaseUrl" `
        --env-vars "DATABASE_URL=secretref:database-url" "SPOTIFY_CLIENT_ID=unused" "SPOTIFY_CLIENT_SECRET=unused" "SPOTIFY_REFRESH_TOKEN=unused" `
        --command "vienna-vibe" --args "migrate" `
        --output none
}
az containerapp job start -g $ResourceGroup -n $migrateJob --output none
Write-Host "Migration lancée. Suivi : az containerapp job execution list -g $ResourceGroup -n $migrateJob"

# ---------------------------------------------------------------------------
Step "Job horaire : $jobName"
$secretArgs = @(
    "database-url=$databaseUrl",
    "spotify-client-id=$SpotifyClientId",
    "spotify-client-secret=$SpotifyClientSecret",
    "spotify-refresh-token=$SpotifyRefreshToken"
)
$envArgs = @(
    "DATABASE_URL=secretref:database-url",
    "SPOTIFY_CLIENT_ID=secretref:spotify-client-id",
    "SPOTIFY_CLIENT_SECRET=secretref:spotify-client-secret",
    "SPOTIFY_REFRESH_TOKEN=secretref:spotify-refresh-token"
)

if (Exists "az containerapp job show -g $ResourceGroup -n $jobName --output none") {
    az containerapp job update -g $ResourceGroup -n $jobName `
        --image "$acrServer/$imageTag" --output none
    Write-Host "Job existant mis à jour avec la nouvelle image."
} else {
    az containerapp job create `
        --resource-group $ResourceGroup --name $jobName --environment $envName `
        --trigger-type Schedule --cron-expression "0 * * * *" `
        --replica-timeout 1200 --replica-retry-limit 2 --parallelism 1 `
        --image "$acrServer/$imageTag" --cpu 0.5 --memory 1Gi `
        --registry-server $acrServer --registry-username $acrUser --registry-password $acrPassword `
        --secrets $secretArgs `
        --env-vars $envArgs `
        --command "vienna-vibe" --args "run" `
        --output none
}

# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Déploiement terminé ===" -ForegroundColor Green
Write-Host "PostgreSQL : $pgHost"
Write-Host "Registre   : $acrServer"
Write-Host "Coffre     : $kvName"
Write-Host "Job horaire: $jobName (cron 0 * * * *)"
Write-Host ""
Write-Host "Déclencher une exécution immédiate :"
Write-Host "  az containerapp job start -g $ResourceGroup -n $jobName"
Write-Host "Voir les exécutions :"
Write-Host "  az containerapp job execution list -g $ResourceGroup -n $jobName -o table"
Write-Host "Consulter les chiffres :"
Write-Host "  psql `"$databaseUrl`" -c 'SELECT * FROM marts.v_project_stats;'"
Write-Host ""
Write-Host "Tout supprimer : ./teardown.ps1" -ForegroundColor Yellow
