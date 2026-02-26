#!/usr/bin/env bash
###############################################################################
# test_devc_remote_preflight.sh — Tests for devc-remote.sh preflight feedback
#
# Validates that remote_preflight() prints per-check status lines, collects
# runtime/compose versions, detects running containers, checks SSH agent
# forwarding, and emits a summary dashboard.
#
# Run:  bash tests/test_devc_remote_preflight.sh
#
# Refs: #149
###############################################################################
set -euo pipefail

PASS=0
FAIL=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEVC_SCRIPT="$PROJECT_ROOT/scripts/devc-remote.sh"

assert_contains() {
    local label="$1" haystack="$2" needle="$3"
    if [[ "$haystack" == *"$needle"* ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        echo "FAIL: $label"
        echo "  expected to contain: $needle"
        echo "  got output (first 500 chars): ${haystack:0:500}"
    fi
}

assert_not_contains() {
    local label="$1" haystack="$2" needle="$3"
    if [[ "$haystack" != *"$needle"* ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        echo "FAIL: $label"
        echo "  expected NOT to contain: $needle"
    fi
}

assert_exit_code() {
    local label="$1" expected="$2" actual="$3"
    if [[ "$actual" == "$expected" ]]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        echo "FAIL: $label"
        echo "  expected exit code: $expected, got: $actual"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a temp script that sources devc-remote.sh (with main disabled),
# overrides ssh() to echo canned data, then calls remote_preflight.
# ─────────────────────────────────────────────────────────────────────────────
build_test_script() {
    local mock_data="$1"
    local tmpscript tmpsrc
    tmpscript=$(mktemp "${TMPDIR:-/tmp}/devc_test.XXXXXX")
    tmpsrc=$(mktemp "${TMPDIR:-/tmp}/devc_src.XXXXXX")

    sed 's/^main "\$@"$/# main disabled/' "$DEVC_SCRIPT" > "$tmpsrc"
    TMPFILES+=("$tmpsrc")

    {
        echo '#!/usr/bin/env bash'
        echo 'set -euo pipefail'
        echo "source \"$tmpsrc\""
        echo 'ssh() {'
        echo "    cat <<'MOCKEOF'"
        echo "$mock_data"
        echo 'MOCKEOF'
        echo '}'
        echo 'SSH_HOST="testhost"'
        echo 'REMOTE_PATH="/home/user/repo"'
        echo 'remote_preflight'
    } > "$tmpscript"

    echo "$tmpscript"
}

TMPFILES=()
cleanup_tmpfiles() { rm -f "${TMPFILES[@]+"${TMPFILES[@]}"}"; }
trap cleanup_tmpfiles EXIT

run_preflight() {
    local mock_data="$1"
    local tmpscript
    tmpscript=$(build_test_script "$mock_data")
    TMPFILES+=("$tmpscript")
    local output rc=0
    output=$(bash "$tmpscript" 2>&1) || rc=$?
    echo "$output"
    return $rc
}

# ─────────────────────────────────────────────────────────────────────────────
# Mock data sets
# ─────────────────────────────────────────────────────────────────────────────
MOCK_HAPPY="RUNTIME=podman
RUNTIME_VERSION=4.9.3
COMPOSE_AVAILABLE=1
COMPOSE_VERSION=2.24.5
GIT_AVAILABLE=1
REPO_PATH_EXISTS=1
DEVCONTAINER_EXISTS=1
DISK_AVAILABLE_GB=42
OS_TYPE=linux
CONTAINER_RUNNING=0
SSH_AUTH_SOCK_FORWARDED=1"

MOCK_CONTAINER_RUNNING="RUNTIME=docker
RUNTIME_VERSION=25.0.3
COMPOSE_AVAILABLE=1
COMPOSE_VERSION=2.24.5
GIT_AVAILABLE=1
REPO_PATH_EXISTS=1
DEVCONTAINER_EXISTS=1
DISK_AVAILABLE_GB=42
OS_TYPE=linux
CONTAINER_RUNNING=1
SSH_AUTH_SOCK_FORWARDED=1"

MOCK_NO_RUNTIME="RUNTIME=
RUNTIME_VERSION=
COMPOSE_AVAILABLE=0
COMPOSE_VERSION=
GIT_AVAILABLE=1
REPO_PATH_EXISTS=1
DEVCONTAINER_EXISTS=0
DISK_AVAILABLE_GB=10
OS_TYPE=linux
CONTAINER_RUNNING=0
SSH_AUTH_SOCK_FORWARDED=0"

MOCK_NO_SSH_AGENT="RUNTIME=podman
RUNTIME_VERSION=4.9.3
COMPOSE_AVAILABLE=1
COMPOSE_VERSION=2.24.5
GIT_AVAILABLE=1
REPO_PATH_EXISTS=1
DEVCONTAINER_EXISTS=1
DISK_AVAILABLE_GB=42
OS_TYPE=linux
CONTAINER_RUNNING=0
SSH_AUTH_SOCK_FORWARDED=0"

MOCK_LOW_DISK="RUNTIME=docker
RUNTIME_VERSION=25.0.3
COMPOSE_AVAILABLE=1
COMPOSE_VERSION=2.24.5
GIT_AVAILABLE=1
REPO_PATH_EXISTS=1
DEVCONTAINER_EXISTS=1
DISK_AVAILABLE_GB=1
OS_TYPE=linux
CONTAINER_RUNNING=0
SSH_AUTH_SOCK_FORWARDED=1"

# ─────────────────────────────────────────────────────────────────────────────
# TEST: Happy path — each check prints a status line
# ─────────────────────────────────────────────────────────────────────────────
test_happy_path_prints_status_lines() {
    local output
    output=$(run_preflight "$MOCK_HAPPY") || true

    assert_contains "repo path reported" "$output" "/home/user/repo"
    assert_contains "runtime detected" "$output" "podman"
    assert_contains "runtime version shown" "$output" "4.9.3"
    assert_contains "compose version shown" "$output" "2.24.5"
    assert_contains "no container running" "$output" "no existing container"
    assert_contains "ssh agent OK" "$output" "SSH agent"
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: Container already running is detected
# ─────────────────────────────────────────────────────────────────────────────
test_container_running_detected() {
    local output
    output=$(run_preflight "$MOCK_CONTAINER_RUNNING") || true

    assert_contains "container running warning" "$output" "container already running"
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: No runtime produces error and exits non-zero
# ─────────────────────────────────────────────────────────────────────────────
test_no_runtime_errors() {
    local output rc=0
    output=$(run_preflight "$MOCK_NO_RUNTIME") || rc=$?

    assert_exit_code "exits non-zero without runtime" "1" "$rc"
    assert_contains "runtime error" "$output" "No container runtime"
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: Missing SSH agent forwarding produces warning
# ─────────────────────────────────────────────────────────────────────────────
test_no_ssh_agent_warns() {
    local output
    output=$(run_preflight "$MOCK_NO_SSH_AGENT") || true

    assert_contains "ssh agent warning" "$output" "SSH agent"
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: Summary dashboard is printed
# ─────────────────────────────────────────────────────────────────────────────
test_summary_dashboard() {
    local output
    output=$(run_preflight "$MOCK_HAPPY") || true

    assert_contains "summary header" "$output" "Preflight Summary"
    assert_contains "summary runtime" "$output" "podman"
    assert_contains "summary compose" "$output" "2.24.5"
    assert_contains "summary repo path" "$output" "/home/user/repo"
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: Low disk triggers warning
# ─────────────────────────────────────────────────────────────────────────────
test_low_disk_warns() {
    local output
    output=$(run_preflight "$MOCK_LOW_DISK") || true

    assert_contains "low disk warning" "$output" "Low disk"
}

# ─────────────────────────────────────────────────────────────────────────────
# RUN ALL
# ─────────────────────────────────────────────────────────────────────────────
echo "=== devc-remote preflight tests ==="
test_happy_path_prints_status_lines
test_container_running_detected
test_no_runtime_errors
test_no_ssh_agent_warns
test_summary_dashboard
test_low_disk_warns

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [[ "$FAIL" -gt 0 ]]; then
    exit 1
else
    echo "All tests passed."
fi
