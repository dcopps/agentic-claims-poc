#!/usr/bin/env bash
# azure-common.sh — shared helpers for the Azure scripts (Phase 9.1, extended in 9.2).
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

# How long azure-start.sh (and the deploy workflow's rollout check) waits for
# /health: 36 × 5 s = 3 min, which covers a cold image pull plus Python start
# with margin.
HEALTH_RETRIES=36
HEALTH_INTERVAL_S=5

# How long azure-stop.sh waits for the last replica to drain before stopping
# Postgres: the scale rule's cooldown is 300 s after the last request; 420 s
# leaves margin for a slow poll.
REPLICA_DRAIN_TIMEOUT_S=420
REPLICA_POLL_INTERVAL_S=15

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

# Poll /health until it answers 200 *with the expected version*, or the budget
# is spent. Used by the deploy workflow: a 200 alone could come from the
# previous revision, which keeps serving until the new one is ready.
wait_for_health_version() {
    local url="$1" expected="$2" attempt body="" version
    for attempt in $(seq 1 "$HEALTH_RETRIES"); do
        if body="$(curl -fsS --max-time 10 "$url" 2>/dev/null)"; then
            version="$(jq -r '.version // empty' <<<"$body")"
            if [[ "$version" == "$expected" ]]; then
                info "healthy with version ${version} after ${attempt} attempt(s)"
                return 0
            fi
        fi
        sleep "$HEALTH_INTERVAL_S"
    done
    die "$url did not report version '$expected' within $((HEALTH_RETRIES * HEALTH_INTERVAL_S)) s (last response: ${body:-none})"
}

# Assert that the Container App's latest revision is ready and runs IMAGE.
# /health cannot distinguish two builds of the same version; the revision can.
# Takes the app name as an argument because the deploy workflow's identity may
# not list the resource group (its roles are scoped to the app and registry).
require_active_image() {
    local app="$1" image="$2" attempt latest="" ready="" active_image
    for attempt in $(seq 1 "$HEALTH_RETRIES"); do
        # join(): with -o tsv an array prints one element per line, and read
        # would see only the first; one space-joined line splits into both.
        read -r latest ready < <(az containerapp show --resource-group "$AZ_RESOURCE_GROUP" --name "$app" \
            --query "join(' ', [properties.latestRevisionName, properties.latestReadyRevisionName])" -o tsv)
        if [[ -n "$latest" && "$latest" == "$ready" ]]; then
            active_image="$(az containerapp revision show --resource-group "$AZ_RESOURCE_GROUP" --name "$app" \
                --revision "$latest" --query 'properties.template.containers[0].image' -o tsv)"
            [[ "$active_image" == "$image" ]] \
                || die "ready revision '$latest' runs '$active_image', expected '$image'"
            info "revision ${latest} is ready and runs ${image}"
            return 0
        fi
        sleep "$HEALTH_INTERVAL_S"
    done
    die "latest revision '${latest}' of '$app' did not become ready within $((HEALTH_RETRIES * HEALTH_INTERVAL_S)) s"
}

# Wait until the Container App has no running replica. minReplicas=0 only
# permits scale-to-zero; the replica that served the last request stays up for
# the cooldown, so azure-stop.sh must not stop Postgres until it is gone.
wait_for_zero_replicas() {
    local app="$1" waited=0 count
    while (( waited < REPLICA_DRAIN_TIMEOUT_S )); do
        count="$(az containerapp replica list --resource-group "$AZ_RESOURCE_GROUP" --name "$app" \
            --query 'length(@)' -o tsv)"
        if [[ "$count" == "0" ]]; then
            info "no replicas running (after ${waited} s)"
            return 0
        fi
        info "${count} replica(s) still running; waiting (${waited} s of ${REPLICA_DRAIN_TIMEOUT_S} s)"
        sleep "$REPLICA_POLL_INTERVAL_S"
        waited=$((waited + REPLICA_POLL_INTERVAL_S))
    done
    die "${count} replica(s) of '$app' still running after ${REPLICA_DRAIN_TIMEOUT_S} s; Postgres left running — investigate before stopping it"
}
