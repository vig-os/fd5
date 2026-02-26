#!/usr/bin/env bash
###############################################################################
# devc-remote.sh - Remote devcontainer orchestrator
#
# Starts a devcontainer on a remote host via SSH and opens Cursor/VS Code.
# Handles SSH connectivity, pre-flight checks, container state detection,
# and compose lifecycle. URI construction delegated to Python helper.
#
# When no :<path> is given, derives the remote path from the local repo name
# (~/repo-name). If the repo doesn't exist on the remote, clones it. If
# .devcontainer/ is missing, runs init-workspace via the container image.
#
# USAGE:
#   ./scripts/devc-remote.sh [--yes|-y] [--repo <url>] <ssh-host>[:<remote-path>]
#   ./scripts/devc-remote.sh --help
#
# Options:
#   --yes, -y    Auto-accept all interactive prompts (reuse running containers)
#   --repo URL   Specify the git remote URL for cloning
#
# Examples:
#   ./scripts/devc-remote.sh myserver
#   ./scripts/devc-remote.sh user@host:/opt/projects/myrepo
#   ./scripts/devc-remote.sh myserver:/home/user/repo
#   ./scripts/devc-remote.sh --repo git@github.com:org/repo.git myserver
#   ./scripts/devc-remote.sh --yes myserver
#
# Part of #70. See issue #152 for design.
###############################################################################

set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# shellcheck disable=SC2034
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING (matches init.sh patterns)
# ═══════════════════════════════════════════════════════════════════════════════

log_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

log_success() {
    echo -e "${GREEN}✓${NC}  $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

log_error() {
    echo -e "${RED}✗${NC}  $1"
}

show_help() {
    sed -n '/^###############################################################################$/,/^###############################################################################$/p' "$0" | sed '1d;$d'
    exit 0
}

parse_args() {
    SSH_HOST=""
    REMOTE_PATH=""
    REPO_URL=""
    YES_MODE=0
    PATH_AUTO_DERIVED=0
    REPO_URL_SOURCE=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                show_help
                ;;
            --yes|-y)
                YES_MODE=1
                shift
                ;;
            --repo)
                shift
                REPO_URL="${1:-}"
                if [[ -z "$REPO_URL" ]]; then
                    log_error "--repo requires a URL argument"
                    exit 1
                fi
                REPO_URL_SOURCE="flag"
                shift
                ;;
            -*)
                log_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
            *)
                if [[ -n "$SSH_HOST" ]]; then
                    log_error "Unexpected argument: $1"
                    exit 1
                fi
                if [[ "$1" =~ ^([^:]+):(.+)$ ]]; then
                    SSH_HOST="${BASH_REMATCH[1]}"
                    REMOTE_PATH="${BASH_REMATCH[2]}"
                else
                    SSH_HOST="$1"
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$SSH_HOST" ]]; then
        log_error "Missing required argument: <ssh-host>[:<remote-path>]"
        echo "Use --help for usage information"
        exit 1
    fi

    if [[ -z "$REMOTE_PATH" ]]; then
        local local_repo_name
        local_repo_name=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || echo "")
        if [[ -n "$local_repo_name" ]]; then
            # Tilde is intentional; expanded by the remote shell
            # shellcheck disable=SC2088
            REMOTE_PATH="~/${local_repo_name}"
            PATH_AUTO_DERIVED=1
        else
            log_error "No remote path given and not inside a git repository."
            exit 1
        fi
    fi

    if [[ -z "$REPO_URL" ]]; then
        REPO_URL=$(git remote get-url origin 2>/dev/null || echo "")
        if [[ -n "$REPO_URL" ]]; then
            REPO_URL_SOURCE="local"
        fi
    fi
}

detect_editor_cli() {
    if command -v cursor &>/dev/null; then
        # shellcheck disable=SC2034
        EDITOR_CLI="cursor"
    elif command -v code &>/dev/null; then
        # shellcheck disable=SC2034
        EDITOR_CLI="code"
    else
        log_error "Neither cursor nor code CLI found. Install Cursor or VS Code and enable the shell command."
        exit 1
    fi
}

check_ssh() {
    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$SSH_HOST" true 2>/dev/null; then
        log_error "Cannot connect to $SSH_HOST. Check your SSH config and network."
        exit 1
    fi
}

remote_preflight() {
    local preflight_output
    # shellcheck disable=SC2029
    preflight_output=$(ssh "$SSH_HOST" "bash -s" "$REMOTE_PATH" << 'REMOTEEOF'
REPO_PATH="${1:-$HOME}"
if command -v podman &>/dev/null; then
    echo "RUNTIME=podman"
    VER=$(podman --version 2>/dev/null | awk '{print $NF}')
    echo "RUNTIME_VERSION=${VER:-unknown}"
elif command -v docker &>/dev/null; then
    echo "RUNTIME=docker"
    VER=$(docker --version 2>/dev/null | sed 's/.*version \([^,]*\).*/\1/')
    echo "RUNTIME_VERSION=${VER:-unknown}"
else
    echo "RUNTIME="
    echo "RUNTIME_VERSION="
fi
if (command -v podman &>/dev/null && podman compose version &>/dev/null) || \
   (command -v docker &>/dev/null && docker compose version &>/dev/null); then
    echo "COMPOSE_AVAILABLE=1"
    CVER=$(podman compose version 2>/dev/null || docker compose version 2>/dev/null)
    CVER=$(echo "$CVER" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    echo "COMPOSE_VERSION=${CVER:-unknown}"
else
    echo "COMPOSE_AVAILABLE=0"
    echo "COMPOSE_VERSION="
fi
if command -v git &>/dev/null; then
    echo "GIT_AVAILABLE=1"
else
    echo "GIT_AVAILABLE=0"
fi
if [ -d "$REPO_PATH" ]; then
    echo "REPO_PATH_EXISTS=1"
else
    echo "REPO_PATH_EXISTS=0"
fi
if [ -d "$REPO_PATH/.devcontainer" ]; then
    echo "DEVCONTAINER_EXISTS=1"
else
    echo "DEVCONTAINER_EXISTS=0"
fi
AVAIL_GB=$(df -BG "$REPO_PATH" 2>/dev/null | awk 'NR==2 {gsub(/G/,""); print $4}')
echo "DISK_AVAILABLE_GB=${AVAIL_GB:-0}"
if [ "$(uname -s)" = "Darwin" ]; then
    echo "OS_TYPE=macos"
else
    echo "OS_TYPE=linux"
fi
# Check for a running devcontainer (compose project in REPO_PATH)
if command -v podman &>/dev/null && cd "$REPO_PATH" 2>/dev/null && podman compose ps --format json 2>/dev/null | grep -q '"running"'; then
    echo "CONTAINER_RUNNING=1"
elif command -v docker &>/dev/null && cd "$REPO_PATH" 2>/dev/null && docker compose ps --format json 2>/dev/null | grep -q '"running"'; then
    echo "CONTAINER_RUNNING=1"
else
    echo "CONTAINER_RUNNING=0"
fi
# Check SSH agent forwarding via ssh-add
if ssh-add -l &>/dev/null; then
    echo "SSH_AGENT_FWD=1"
else
    echo "SSH_AGENT_FWD=0"
fi
REMOTEEOF
    )

    while IFS= read -r line; do
        [[ "$line" =~ ^([A-Z_]+)=(.*)$ ]] || continue
        case "${BASH_REMATCH[1]}" in
            RUNTIME)                 RUNTIME="${BASH_REMATCH[2]}" ;;
            RUNTIME_VERSION)         RUNTIME_VERSION="${BASH_REMATCH[2]}" ;;
            COMPOSE_AVAILABLE)       COMPOSE_AVAILABLE="${BASH_REMATCH[2]}" ;;
            COMPOSE_VERSION)         COMPOSE_VERSION="${BASH_REMATCH[2]}" ;;
            GIT_AVAILABLE)           GIT_AVAILABLE="${BASH_REMATCH[2]}" ;;
            REPO_PATH_EXISTS)        REPO_PATH_EXISTS="${BASH_REMATCH[2]}" ;;
            DEVCONTAINER_EXISTS)     DEVCONTAINER_EXISTS="${BASH_REMATCH[2]}" ;;
            DISK_AVAILABLE_GB)       DISK_AVAILABLE_GB="${BASH_REMATCH[2]}" ;;
            OS_TYPE)                 OS_TYPE="${BASH_REMATCH[2]}" ;;
            CONTAINER_RUNNING)       CONTAINER_RUNNING="${BASH_REMATCH[2]}" ;;
            SSH_AGENT_FWD)          SSH_AGENT_FWD="${BASH_REMATCH[2]}" ;;
        esac
    done <<< "$preflight_output"

    # ── Per-check status lines ──────────────────────────────────────────
    local repo_status="missing"
    [[ "${REPO_PATH_EXISTS:-0}" == "1" ]] && repo_status="found"
    log_info "Repo path: $REMOTE_PATH ($repo_status)"

    # Hard errors: runtime and compose are always required
    if [[ -z "${RUNTIME:-}" ]]; then
        log_error "No container runtime found on $SSH_HOST. Install podman or docker."
        exit 1
    fi
    log_success "Container runtime: $RUNTIME ${RUNTIME_VERSION:-}"

    if [[ "$RUNTIME" == "podman" ]]; then
        COMPOSE_CMD="podman compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    if [[ "${COMPOSE_AVAILABLE:-0}" != "1" ]]; then
        log_error "Compose not available on $SSH_HOST. Install docker-compose or podman-compose."
        exit 1
    fi
    log_success "Compose: ${COMPOSE_VERSION:-available}"

    if [[ "${CONTAINER_RUNNING:-0}" == "1" ]]; then
        log_warning "A container already running in $REMOTE_PATH"
    else
        log_success "No existing container running"
    fi

    if [[ "${SSH_AGENT_FWD:-0}" == "1" ]]; then
        log_success "SSH agent forwarding: working"
    else
        log_warning "SSH agent forwarding: not available (git signing may fail inside container)"
    fi

    if [[ "${DISK_AVAILABLE_GB:-0}" -lt 2 ]] 2>/dev/null; then
        log_warning "Low disk space on $SSH_HOST (${DISK_AVAILABLE_GB:-0}GB). At least 2GB recommended."
    fi
    if [[ "${OS_TYPE:-}" == "macos" ]]; then
        log_warning "Remote host is macOS. Devcontainer support may be limited."
    fi

    # ── Summary dashboard ───────────────────────────────────────────────
    echo ""
    echo -e "${BLUE}═══ Preflight Summary ═══${NC}"
    echo -e "  Host:      $SSH_HOST"
    echo -e "  Repo:      $REMOTE_PATH"
    echo -e "  Runtime:   $RUNTIME ${RUNTIME_VERSION:-}"
    echo -e "  Compose:   ${COMPOSE_VERSION:-available}"
    echo -e "  Disk:      ${DISK_AVAILABLE_GB:-?}GB available"
    echo -e "${BLUE}═════════════════════════${NC}"
    echo ""
}

remote_clone_if_needed() {
    [[ "${REPO_PATH_EXISTS:-0}" == "1" ]] && return 0

    if [[ -z "$REPO_URL" ]]; then
        log_error "Repository not found at $REMOTE_PATH on $SSH_HOST and no repo URL available."
        log_error "Provide a path (host:path) or use --repo <url>."
        exit 1
    fi
    if [[ "${GIT_AVAILABLE:-0}" != "1" ]]; then
        log_error "git not found on $SSH_HOST. Install git to enable auto-clone."
        exit 1
    fi

    log_info "Cloning $REPO_URL to $REMOTE_PATH on $SSH_HOST..."
    # shellcheck disable=SC2029
    if ! ssh "$SSH_HOST" "git clone '$REPO_URL' '$REMOTE_PATH'"; then
        log_error "git clone failed on $SSH_HOST."
        exit 1
    fi
    log_success "Repository cloned to $REMOTE_PATH"
    REPO_PATH_EXISTS=1
}

remote_init_if_needed() {
    [[ "${DEVCONTAINER_EXISTS:-0}" == "1" ]] && return 0

    local project_name
    project_name=$(basename "$REMOTE_PATH" | tr '[:upper:]' '[:lower:]' | sed 's/[ -]/_/g; s/[^a-z0-9_]/_/g')

    log_info "No .devcontainer/ found. Running init-workspace for '$project_name'..."
    # shellcheck disable=SC2029
    if ! ssh "$SSH_HOST" "$RUNTIME run --rm \
        -e SHORT_NAME='$project_name' \
        -e ORG_NAME='vigOS' \
        -v '$REMOTE_PATH:/workspace' \
        ghcr.io/vig-os/devcontainer:latest \
        /root/assets/init-workspace.sh --no-prompts --force"; then
        log_error "init-workspace failed on $SSH_HOST."
        exit 1
    fi
    log_success "Workspace initialized"
    DEVCONTAINER_EXISTS=1
}

compose_ps_json() {
    # shellcheck disable=SC2029
    ssh "$SSH_HOST" "cd $REMOTE_PATH && $COMPOSE_CMD ps --format json 2>/dev/null" || true
}

check_existing_container() {
    [[ "${CONTAINER_RUNNING:-0}" != "1" ]] && return 0

    local ps_output state
    ps_output=$(compose_ps_json)
    state=$(echo "$ps_output" | grep -o '"State":"[^"]*"' | head -1 | cut -d'"' -f4)

    if [[ "$state" != "running" ]]; then
        return 0
    fi

    if [[ "${YES_MODE:-0}" == "1" ]]; then
        log_info "Reusing existing container (--yes)"
        SKIP_COMPOSE_UP=1
        return 0
    fi

    echo ""
    log_info "Container for $REMOTE_PATH is already running on $SSH_HOST."
    echo "  [R]euse (default)  [r]ecreate  [a]bort"
    local choice
    read -r -n 1 -p "  > " choice </dev/tty || choice="R"
    echo ""

    case "${choice:-R}" in
        R|r)
            if [[ "${choice:-R}" == "r" ]]; then
                log_info "Recreating container..."
                # shellcheck disable=SC2029
                ssh "$SSH_HOST" "cd $REMOTE_PATH && $COMPOSE_CMD down" || true
                SKIP_COMPOSE_UP=0
            else
                log_info "Reusing existing container"
                SKIP_COMPOSE_UP=1
            fi
            ;;
        a|A)
            log_info "Aborted by user."
            exit 0
            ;;
        *)
            log_info "Reusing existing container"
            SKIP_COMPOSE_UP=1
            ;;
    esac
}

remote_compose_up() {
    if [[ "${SKIP_COMPOSE_UP:-0}" == "1" ]]; then
        log_success "Devcontainer already running on $SSH_HOST. Opening..."
        return 0
    fi

    log_info "Starting devcontainer on $SSH_HOST..."
    # shellcheck disable=SC2029
    if ! ssh "$SSH_HOST" "cd $REMOTE_PATH && $COMPOSE_CMD up -d"; then
        log_error "Failed to start devcontainer on $SSH_HOST."
        log_error "Run 'ssh $SSH_HOST \"cd $REMOTE_PATH && $COMPOSE_CMD logs\"' for details."
        exit 1
    fi
    sleep 2
}

open_editor() {
    local container_workspace uri
    # Read workspaceFolder from devcontainer.json on remote host
    # shellcheck disable=SC2029
    container_workspace=$(ssh "$SSH_HOST" \
        "grep -o '\"workspaceFolder\"[[:space:]]*:[[:space:]]*\"[^\"]*\"' \
         ${REMOTE_PATH}/.devcontainer/devcontainer.json 2>/dev/null" \
        | sed 's/.*: *"//;s/"//' || echo "/workspace")

    # Default to /workspace if workspaceFolder not found
    container_workspace="${container_workspace:-/workspace}"

    # Build URI using Python helper
    if ! uri=$(python3 "$SCRIPT_DIR/devc_remote_uri.py" \
        "$REMOTE_PATH" \
        "$SSH_HOST" \
        "$container_workspace"); then
        log_error "Failed to build editor URI. Is devc_remote_uri.py present in $SCRIPT_DIR?"
        exit 1
    fi

    if ! "$EDITOR_CLI" --folder-uri "$uri"; then
        log_error "Failed to open $EDITOR_CLI. URI: $uri"
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

main() {
    parse_args "$@"

    local path_annotation="explicit"
    [[ "${PATH_AUTO_DERIVED:-0}" == "1" ]] && path_annotation="auto-derived from local repo"
    log_success "Remote path: $REMOTE_PATH ($path_annotation)"

    if [[ -n "${REPO_URL:-}" ]]; then
        log_success "Repo URL: $REPO_URL (from ${REPO_URL_SOURCE:-unknown})"
    else
        log_warning "Repo URL: not available (clone will fail if repo missing on remote)"
    fi

    log_info "Detecting local editor CLI..."
    detect_editor_cli
    log_success "Using $EDITOR_CLI"

    log_info "Checking SSH connectivity to $SSH_HOST..."
    check_ssh
    log_success "SSH connection OK"

    log_info "Running pre-flight checks on $SSH_HOST..."
    remote_preflight
    log_success "Pre-flight OK (runtime: $RUNTIME)"

    remote_clone_if_needed
    remote_init_if_needed
    SKIP_COMPOSE_UP=0
    check_existing_container
    remote_compose_up
    open_editor

    log_success "Done — opened $EDITOR_CLI for $SSH_HOST:$REMOTE_PATH"
}

main "$@"
