#!/usr/bin/env bash
# azure-start.sh — bring the Azure deployment up for a demo session (Phase 9.1).
#
# Starts the Postgres Flexible Server (waits until it reports Ready), scales the
# backend Container App to one warm replica so the first request pays no cold
# start, then polls /health until it answers. Reverse with scripts/azure-stop.sh.

set -euo pipefail
# shellcheck source=scripts/azure-common.sh
source "$(dirname "${BASH_SOURCE[0]}")/azure-common.sh"

start_postgres() {
    local server="$1" state
    state="$(az postgres flexible-server show --resource-group "$AZ_RESOURCE_GROUP" \
        --name "$server" --query state -o tsv)"
    if [[ "$state" == "Ready" ]]; then
        info "postgres server '$server' already Ready"
        return 0
    fi
    # `az postgres flexible-server start` blocks until the server reports Ready.
    info "starting postgres server '$server' (state: $state)"
    az postgres flexible-server start --resource-group "$AZ_RESOURCE_GROUP" --name "$server" -o none \
        || die "postgres server '$server' failed to start"
}

main() {
    require_az_login
    require_resource_group

    local app server fqdn
    server="$(postgres_server_name)"
    app="$(container_app_name)"

    start_postgres "$server"

    info "scaling container app '$app' to minReplicas=1"
    az containerapp update --resource-group "$AZ_RESOURCE_GROUP" --name "$app" \
        --min-replicas 1 -o none

    fqdn="$(container_app_fqdn)"
    info "waiting for https://${fqdn}/health"
    wait_for_health "https://${fqdn}/health"
}

main "$@"
