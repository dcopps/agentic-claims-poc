#!/usr/bin/env bash
# azure-deploy.sh — provision, build and redeploy the Azure prototype (Phase 9.1).
#
#   scripts/azure-deploy.sh what-if [IMAGE]   preview the Bicep delta (group must exist)
#   scripts/azure-deploy.sh deploy  [IMAGE]   create the group if needed, deploy main.bicep
#   scripts/azure-deploy.sh build             build the backend image in ACR, print its reference
#
# IMAGE is the full reference (<acr>.azurecr.io/claims-backend:<sha>). Without
# it the deployment creates everything except the Container App (pass 1); with
# it the Container App is created or updated (pass 2).
#
# Strategy: sanitise → validate → abort → execute. Every secret the Bicep
# parameter file reads with readEnvironmentVariable() is resolved into this
# process's environment here — API keys from the shell or the local .env, the
# Postgres admin password from Key Vault if one exists (so a redeploy never
# rotates it) or freshly generated — and only *names* are ever echoed.

set -euo pipefail
# shellcheck source=scripts/azure-common.sh
source "$(dirname "${BASH_SOURCE[0]}")/azure-common.sh"

IMAGE_REPOSITORY="claims-backend"
# Hex alphabet: URL-safe, so the composed DATABASE_URL needs no percent-encoding.
PASSWORD_BYTES=24

usage() { die "usage: $0 what-if [IMAGE] | deploy [IMAGE] | build"; }

# Read KEY from the environment, else from the repo's .env; die if neither has it.
resolve_from_env_or_dotenv() {
    local key="$1" value="${!1:-}"
    if [[ -z "$value" && -f "$REPO_ROOT/.env" ]]; then
        value="$(grep -E "^${key}=" "$REPO_ROOT/.env" | head -1 | cut -d= -f2- | tr -d '"'"'")"
    fi
    [[ -n "$value" ]] || die "$key is not set in the environment or .env"
    export "$key=$value"
}

# Reuse the existing admin password when the vault already holds one, so a
# redeploy is a no-op for Postgres and the stored DATABASE_URL stays valid.
resolve_postgres_password() {
    if [[ -n "${POSTGRES_ADMIN_PASSWORD:-}" ]]; then
        info "POSTGRES_ADMIN_PASSWORD taken from the environment"
        return 0
    fi
    local vault existing=""
    vault="$(az resource list --resource-group "$AZ_RESOURCE_GROUP" \
        --resource-type Microsoft.KeyVault/vaults --query '[0].name' -o tsv 2>/dev/null || true)"
    if [[ -n "$vault" ]]; then
        existing="$(az keyvault secret show --vault-name "$vault" --name postgres-admin-password \
            --query value -o tsv 2>/dev/null || true)"
    fi
    if [[ -n "$existing" ]]; then
        info "reusing postgres admin password from vault '$vault'"
        export POSTGRES_ADMIN_PASSWORD="$existing"
    else
        info "generating a new postgres admin password"
        export POSTGRES_ADMIN_PASSWORD="$(openssl rand -hex "$PASSWORD_BYTES")"
    fi
}

resolve_deployer_identity() {
    if [[ -z "${DEPLOYER_CLIENT_IP:-}" ]]; then
        DEPLOYER_CLIENT_IP="$(curl -fsS --max-time 10 https://api.ipify.org)" \
            || die "could not determine public IP; set DEPLOYER_CLIENT_IP"
    fi
    [[ "$DEPLOYER_CLIENT_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] \
        || die "DEPLOYER_CLIENT_IP must be a dotted IPv4 address, got '$DEPLOYER_CLIENT_IP'"
    export DEPLOYER_CLIENT_IP

    if [[ -z "${DEPLOYER_PRINCIPAL_ID:-}" ]]; then
        DEPLOYER_PRINCIPAL_ID="$(az ad signed-in-user show --query id -o tsv)" \
            || die "could not resolve the signed-in user's object id; set DEPLOYER_PRINCIPAL_ID"
    fi
    [[ "$DEPLOYER_PRINCIPAL_ID" =~ ^[0-9a-fA-F-]{36}$ ]] \
        || die "DEPLOYER_PRINCIPAL_ID must be a GUID, got '$DEPLOYER_PRINCIPAL_ID'"
    export DEPLOYER_PRINCIPAL_ID
    info "deployer client IP $DEPLOYER_CLIENT_IP, principal $DEPLOYER_PRINCIPAL_ID"
}

# Validate the optional image reference and export it for the parameter file.
resolve_container_image() {
    local image="${1:-}"
    if [[ -n "$image" ]]; then
        [[ "$image" =~ ^[a-z0-9]+\.azurecr\.io/${IMAGE_REPOSITORY}:[A-Za-z0-9._-]+$ ]] \
            || die "IMAGE must look like <acr>.azurecr.io/${IMAGE_REPOSITORY}:<tag>, got '$image'"
        info "container image: $image (Container App will be deployed)"
    else
        info "no image given: deploying infrastructure only (pass 1)"
    fi
    export CONTAINER_IMAGE="$image"
}

resolve_parameters() {
    resolve_from_env_or_dotenv ANTHROPIC_API_KEY
    resolve_from_env_or_dotenv MISTRAL_API_KEY
    resolve_postgres_password
    resolve_deployer_identity
    resolve_container_image "${1:-}"
}

cmd_what_if() {
    require_resource_group
    resolve_parameters "${1:-}"
    info "what-if against '$AZ_RESOURCE_GROUP'"
    az deployment group what-if --resource-group "$AZ_RESOURCE_GROUP" --parameters "$BICEP_PARAMS"
}

cmd_deploy() {
    resolve_parameters "${1:-}"
    info "ensuring resource group '$AZ_RESOURCE_GROUP' in $AZ_LOCATION"
    az group create --name "$AZ_RESOURCE_GROUP" --location "$AZ_LOCATION" -o none
    local name
    name="${AZ_PREFIX}-${AZ_ENV}-$(git -C "$REPO_ROOT" rev-parse --short HEAD)-$(date -u +%Y%m%dT%H%M%SZ)"
    info "deploying '$name'"
    az deployment group create --resource-group "$AZ_RESOURCE_GROUP" --name "$name" \
        --parameters "$BICEP_PARAMS" --query properties.outputs -o json
}

# Build in-registry from the committed tree so the SHA tag is truthful.
cmd_build() {
    require_resource_group
    [[ -z "$(git -C "$REPO_ROOT" status --porcelain)" ]] \
        || die "working tree is dirty; commit first so the image tag matches the source"
    local registry login_server tag
    registry="$(registry_name)"
    login_server="$(az acr show --name "$registry" --query loginServer -o tsv)"
    tag="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
    info "building ${IMAGE_REPOSITORY}:${tag} in registry '$registry' (linux/amd64)"
    az acr build --registry "$registry" --platform linux/amd64 --file "$REPO_ROOT/Dockerfile" \
        --image "${IMAGE_REPOSITORY}:${tag}" --image "${IMAGE_REPOSITORY}:latest" "$REPO_ROOT"
    echo
    info "image: ${login_server}/${IMAGE_REPOSITORY}:${tag}"
}

main() {
    require_az_login
    case "${1:-}" in
        what-if) cmd_what_if "${2:-}" ;;
        deploy)  cmd_deploy "${2:-}" ;;
        build)   [[ $# -eq 1 ]] || usage; cmd_build ;;
        *)       usage ;;
    esac
}

main "$@"
