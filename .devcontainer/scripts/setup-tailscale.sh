#!/bin/bash

# Tailscale setup for direct SSH access to the devcontainer.
# Opt-in: only activates when TAILSCALE_AUTHKEY is set (via docker-compose.local.yaml).
#
# Subcommands:
#   install  - install Tailscale binary (idempotent, for post-create)
#   start    - start daemon + connect to tailnet with SSH enabled (for post-start)
#
# Tailscale SSH lets Cursor (or any SSH client) connect directly to the container
# over the tailnet — no jump hosts, no devcontainer protocol.

set -euo pipefail

DEFAULT_HOSTNAME="fd5-devc-$(hostname -s 2>/dev/null || echo unknown)"
TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-$DEFAULT_HOSTNAME}"

cmd_install() {
    if [[ -z "${TAILSCALE_AUTHKEY:-}" ]]; then
        echo "TAILSCALE_AUTHKEY not set, skipping Tailscale install"
        return
    fi

    if command -v tailscale &>/dev/null; then
        echo "Tailscale already installed ($(tailscale version | head -1))"
        return
    fi

    echo "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
    echo "Tailscale installed"
}

cmd_start() {
    if ! command -v tailscaled &>/dev/null; then
        return
    fi

    if [[ -z "${TAILSCALE_AUTHKEY:-}" ]]; then
        echo "TAILSCALE_AUTHKEY not set, skipping Tailscale"
        return
    fi

    if ! pgrep -x tailscaled &>/dev/null; then
        echo "Starting Tailscale daemon..."
        tailscaled --tun=userspace-networking --state=/var/lib/tailscale/tailscaled.state &
        sleep 2
    fi

    echo "Connecting to tailnet as ${TAILSCALE_HOSTNAME}..."
    tailscale up --authkey="$TAILSCALE_AUTHKEY" --ssh --hostname="$TAILSCALE_HOSTNAME"

    local ip
    ip=$(tailscale ip -4 2>/dev/null || echo "unknown")
    echo "Tailscale SSH ready at ${ip} (${TAILSCALE_HOSTNAME})"
}

case "${1:-}" in
    install) cmd_install ;;
    start)   cmd_start ;;
    *)       echo "Usage: $0 {install|start}" >&2; exit 1 ;;
esac
