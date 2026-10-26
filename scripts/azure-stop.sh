#!/usr/bin/env bash
# azure-stop.sh — park the Azure deployment between demo sessions (Phase 9.1,
# replica drain added in 9.2).
#
# Sets the backend Container App's minReplicas to 0, waits until no replica is
# running, then stops the Postgres Flexible Server. Stopped compute is not
# billed; Postgres storage still is. Reverse with scripts/azure-start.sh.
#
# Why the wait: minReplicas=0 permits scale-to-zero; it does not stop a running
# replica. The one that served recent traffic drains only after the scale
# rule's cooldown (300 s since its last request). On the first round trip
# (1 October 2026) it outlived the Postgres stop by about five minutes — idle,
# but a request arriving in that window would have reached a live app with no
# database. The script now stops Postgres only once the replica is gone, and
# aborts (leaving Postgres running) if it has not drained within the bounded
# wait in azure-common.sh.
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

    info "waiting for the last replica of '$app' to drain"
    wait_for_zero_replicas "$app"

    info "stopping postgres server '$server'"
    az postgres flexible-server stop --resource-group "$AZ_RESOURCE_GROUP" --name "$server" -o none

    info "stopped. Azure will auto-start the server after 7 days; re-run to re-stop."
}

main "$@"
