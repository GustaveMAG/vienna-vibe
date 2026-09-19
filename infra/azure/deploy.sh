#!/usr/bin/env bash
# Équivalent Linux/macOS de deploy.ps1. Mêmes ressources, même logique.
# Usage : SPOTIFY_CLIENT_ID=... SPOTIFY_CLIENT_SECRET=... SPOTIFY_REFRESH_TOKEN=... ./deploy.sh
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-vienna-vibe}"
LOCATION="${LOCATION:-westeurope}"
PREFIX="${PREFIX:-viennavibe}"

: "${SPOTIFY_CLIENT_ID:?variable requise}"
: "${SPOTIFY_CLIENT_SECRET:?variable requise}"
: "${SPOTIFY_REFRESH_TOKEN:?variable requise}"

SUB_ID=$(az account show --query id -o tsv)
SUFFIX=$(echo "$SUB_ID" | tr -dc '0-9a-f' | cut -c1-6)
ACR_NAME="${PREFIX}${SUFFIX}"
KV_NAME="kv-${PREFIX}-${SUFFIX}"
PG_NAME="pg-${PREFIX}-${SUFFIX}"
ENV_NAME="cae-${PREFIX}"
JOB_NAME="job-${PREFIX}-hourly"
IMAGE_TAG="vienna-vibe:latest"
PG_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)}"

step() { printf "\n==> %s\n" "$1"; }

step "Prérequis"
az extension add --name containerapp --upgrade --only-show-errors --output none
az provider register --namespace Microsoft.App --output none

step "Groupe de ressources"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

step "PostgreSQL Flexible Server : $PG_NAME"
az postgres flexible-server show -g "$RESOURCE_GROUP" -n "$PG_NAME" --output none 2>/dev/null || \
az postgres flexible-server create \
    --resource-group "$RESOURCE_GROUP" --name "$PG_NAME" --location "$LOCATION" \
    --admin-user vienna --admin-password "$PG_PASSWORD" \
    --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 \
    --database-name vienna_vibe --public-access 0.0.0.0 --yes --output none

PG_HOST="${PG_NAME}.postgres.database.azure.com"
DATABASE_URL="postgresql://vienna:${PG_PASSWORD}@${PG_HOST}:5432/vienna_vibe?sslmode=require"

step "Key Vault : $KV_NAME"
az keyvault show -n "$KV_NAME" --output none 2>/dev/null || \
az keyvault create -g "$RESOURCE_GROUP" -n "$KV_NAME" -l "$LOCATION" \
    --enable-rbac-authorization true --output none
ME=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --assignee "$ME" --role "Key Vault Secrets Officer" \
    --scope "$(az keyvault show -n "$KV_NAME" --query id -o tsv)" --output none 2>/dev/null || true
sleep 10
for pair in "spotify-client-id:$SPOTIFY_CLIENT_ID" \
            "spotify-client-secret:$SPOTIFY_CLIENT_SECRET" \
            "spotify-refresh-token:$SPOTIFY_REFRESH_TOKEN" \
            "database-url:$DATABASE_URL"; do
    az keyvault secret set --vault-name "$KV_NAME" \
        --name "${pair%%:*}" --value "${pair#*:}" --output none
done

step "Container Registry et image"
az acr show -n "$ACR_NAME" --output none 2>/dev/null || \
az acr create -g "$RESOURCE_GROUP" -n "$ACR_NAME" --sku Basic --admin-enabled true --output none
(cd "$(dirname "$0")/../.." && az acr build --registry "$ACR_NAME" --image "$IMAGE_TAG" --file Dockerfile . --output none)
ACR_SERVER=$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)
ACR_USER=$(az acr credential show -n "$ACR_NAME" --query username -o tsv)
ACR_PASS=$(az acr credential show -n "$ACR_NAME" --query "passwords[0].value" -o tsv)

step "Container Apps Environment"
az containerapp env show -g "$RESOURCE_GROUP" -n "$ENV_NAME" --output none 2>/dev/null || \
az containerapp env create -g "$RESOURCE_GROUP" -n "$ENV_NAME" -l "$LOCATION" --output none

step "Job horaire : $JOB_NAME"
az containerapp job show -g "$RESOURCE_GROUP" -n "$JOB_NAME" --output none 2>/dev/null && \
az containerapp job update -g "$RESOURCE_GROUP" -n "$JOB_NAME" --image "$ACR_SERVER/$IMAGE_TAG" --output none || \
az containerapp job create \
    --resource-group "$RESOURCE_GROUP" --name "$JOB_NAME" --environment "$ENV_NAME" \
    --trigger-type Schedule --cron-expression "0 * * * *" \
    --replica-timeout 1200 --replica-retry-limit 2 --parallelism 1 \
    --image "$ACR_SERVER/$IMAGE_TAG" --cpu 0.5 --memory 1Gi \
    --registry-server "$ACR_SERVER" --registry-username "$ACR_USER" --registry-password "$ACR_PASS" \
    --secrets "database-url=$DATABASE_URL" \
              "spotify-client-id=$SPOTIFY_CLIENT_ID" \
              "spotify-client-secret=$SPOTIFY_CLIENT_SECRET" \
              "spotify-refresh-token=$SPOTIFY_REFRESH_TOKEN" \
    --env-vars "DATABASE_URL=secretref:database-url" \
               "SPOTIFY_CLIENT_ID=secretref:spotify-client-id" \
               "SPOTIFY_CLIENT_SECRET=secretref:spotify-client-secret" \
               "SPOTIFY_REFRESH_TOKEN=secretref:spotify-refresh-token" \
    --command "vienna-vibe" --args "run" --output none

printf "\n=== Déploiement terminé ===\n"
echo "PostgreSQL : $PG_HOST"
echo "Job        : $JOB_NAME (cron 0 * * * *)"
echo "Mot de passe PostgreSQL : $PG_PASSWORD"
