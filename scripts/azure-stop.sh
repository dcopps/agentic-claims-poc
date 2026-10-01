#!/usr/bin/env bash
# azure-stop.sh — park the Azure deployment between demo sessions (Phase 9.1).
#
# Scales the backend Container App to zero replicas, then stops the Postgres
# Flexible Server. Order matters: the app goes first so no replica is left
# failing against a stopping database. Stopped compute is not billed; Postgres
# storage still is. Reverse with scripts/azure-start.sh.
#
# Caveat the service imposes: Azure automatically restarts a stopped Flexible
# Server after seven days. Re-run this script if the pause is longer.

set -euo pipefail
# shellcheck source=scripts/azure-common.sh
source "$(dirname "${BASH_SOURCE[0]}")/azure-common.sh"

main() {
    require_az_login
    require_resource_group

    local app server
    app="$(container_app_name)"
    server="$(postgres_server_name)"

    info "scaling container app '$app' to minReplicas=0"
    az containerapp update --resource-group "$AZ_RESOURCE_GROUP" --name "$app" \
        --min-replicas 0 -o none

    info "stopping postgres server '$server'"
    az postgres flexible-server stop --resource-group "$AZ_RESOURCE_GROUP" --name "$server" -o none

    info "stopped. Azure will auto-start the server after 7 days; re-run to re-stop."
}

main "$@"
