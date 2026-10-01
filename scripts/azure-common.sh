#!/usr/bin/env bash
# azure-common.sh — shared helpers for the Azure scripts (Phase 9.1).
#
# Sourced, not executed. Resolves the resource group from the same prefix /
# environment pair as infra/bicep/main.bicepparam, and looks resource names up
# from the group at run time so nothing generated (the uniqueString suffix) is
# ever hardcoded here. Every helper either returns a value or dies with a
# diagnostic — no helper returns an empty string for the caller to trip on.

# shellcheck shell=bash

AZ_PREFIX="${AZURE_NAME_PREFIX:-claimsai}"
AZ_ENV="${AZURE_ENVIRONMENT:-dev}"
AZ_LOCATION="${AZURE_LOCATION:-northeurope}"
AZ_RESOURCE_GROUP="rg-${AZ_PREFIX}-${AZ_ENV}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BICEP_PARAMS="${REPO_ROOT}/infra/bicep/main.bicepparam"

# How long azure-start.sh waits for /health after scaling up: 36 × 5 s = 3 min,
# which covers a cold image pull plus Python start with margin.
HEALTH_RETRIES=36
HEALTH_INTERVAL_S=5

die() { echo "error: $*" >&2; exit 1; }
info() { echo "→ $*"; }

require_az_login() {
    command -v az >/dev/null 2>&1 || die "az CLI not on PATH (brew install azure-cli)"
    az account show -o none 2>/dev/null \
        || die "not logged in to Azure — run: az login"
}

require_resource_group() {
    az group show --name "$AZ_RESOURCE_GROUP" -o none 2>/dev/null \
        || die "resource group '$AZ_RESOURCE_GROUP' does not exist — run scripts/azure-deploy.sh deploy first"
}

# Name of the single resource of a given type in the group. The Bicep template
# creates exactly one of each, so [0] is unambiguous; an empty result means the
# deployment has not happened, which is an abort, not a default.
first_resource_name() {
    local resource_type="$1" name
    name="$(az resource list --resource-group "$AZ_RESOURCE_GROUP" \
        --resource-type "$resource_type" --query '[0].name' -o tsv 2>/dev/null)"
    [[ -n "$name" ]] || die "no $resource_type found in '$AZ_RESOURCE_GROUP'"
    printf '%s\n' "$name"
}

postgres_server_name() { first_resource_name Microsoft.DBforPostgreSQL/flexibleServers; }
container_app_name()   { first_resource_name Microsoft.App/containerApps; }
key_vault_name()       { first_resource_name Microsoft.KeyVault/vaults; }
registry_name()        { first_resource_name Microsoft.ContainerRegistry/registries; }

container_app_fqdn() {
    local app fqdn
    app="$(container_app_name)"
    fqdn="$(az containerapp show --resource-group "$AZ_RESOURCE_GROUP" --name "$app" \
        --query properties.configuration.ingress.fqdn -o tsv 2>/dev/null)"
    [[ -n "$fqdn" ]] || die "container app '$app' has no ingress FQDN"
    printf '%s\n' "$fqdn"
}

# Poll /health until it answers 200 or the retry budget is spent.
wait_for_health() {
    local url="$1" attempt
    for attempt in $(seq 1 "$HEALTH_RETRIES"); do
        if curl -fsS --max-time 10 "$url" >/dev/null 2>&1; then
            info "healthy after ${attempt} attempt(s): $(curl -fsS --max-time 10 "$url")"
            return 0
        fi
        sleep "$HEALTH_INTERVAL_S"
    done
    die "$url did not return 200 within $((HEALTH_RETRIES * HEALTH_INTERVAL_S)) s"
}
