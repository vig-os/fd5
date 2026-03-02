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

# Helper: build a temp script that tests parse_args and globals set by it
build_parse_args_script() {
    local args="$1"
    local tmpscript tmpsrc
    tmpscript=$(mktemp "${TMPDIR:-/tmp}/devc_test.XXXXXX")
    tmpsrc=$(mktemp "${TMPDIR:-/tmp}/devc_src.XXXXXX")

    sed 's/^main "\$@"$/# main disabled/' "$DEVC_SCRIPT" > "$tmpsrc"
    TMPFILES+=("$tmpsrc")

    {
        echo '#!/usr/bin/env bash'
        echo 'set -euo pipefail'
        echo "source \"$tmpsrc\""
        echo "git() { echo /fake/repo; }"
        echo "parse_args $args"
        # shellcheck disable=SC2016
        echo 'echo "YES_MODE=${YES_MODE:-0}"'
        # shellcheck disable=SC2016
        echo 'echo "SSH_HOST=${SSH_HOST:-}"'
        # shellcheck disable=SC2016
        echo 'echo "REMOTE_PATH=${REMOTE_PATH:-}"'
        # shellcheck disable=SC2016
        echo 'echo "PATH_AUTO_DERIVED=${PATH_AUTO_DERIVED:-0}"'
        # shellcheck disable=SC2016
        echo 'echo "REPO_URL_SOURCE=${REPO_URL_SOURCE:-}"'
    } > "$tmpscript"

    echo "$tmpscript"
}

run_parse_args() {
    local args="$1"
    local tmpscript
    tmpscript=$(build_parse_args_script "$args")
    TMPFILES+=("$tmpscript")
    local output rc=0
    output=$(bash "$tmpscript" 2>&1) || rc=$?
    echo "$output"
    return $rc
}

# Helper: build a script that tests check_existing_container
build_container_check_script() {
    local mock_data="$1" yes_mode="${2:-0}"
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
        echo "YES_MODE=$yes_mode"
        echo 'SSH_HOST="testhost"'
        echo 'REMOTE_PATH="/home/user/repo"'
        echo 'COMPOSE_CMD="podman compose"'
        echo 'CONTAINER_RUNNING=1'
        echo 'check_existing_container'
    } > "$tmpscript"

    echo "$tmpscript"
}

run_container_check() {
    local mock_data="$1" yes_mode="${2:-0}"
    local tmpscript
    tmpscript=$(build_container_check_script "$mock_data" "$yes_mode")
    TMPFILES+=("$tmpscript")
    local output rc=0
    output=$(bash "$tmpscript" 2>&1) || rc=$?
    echo "$output"
    return $rc
}

# Helper: build a script that tests resolve_remote_path_absolute
build_resolve_path_script() {
    local input_path="$1" home_path="$2"
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
        echo "    printf '%s' \"$1\" >/dev/null"
        echo "    printf '%s' \"$2\" >/dev/null"
        echo "    echo \"$home_path\""
        echo '}'
        echo 'SSH_HOST="testhost"'
        echo "resolve_remote_path_absolute \"$input_path\""
    } > "$tmpscript"

    echo "$tmpscript"
}

run_resolve_path() {
    local input_path="$1" home_path="$2"
    local tmpscript
    tmpscript=$(build_resolve_path_script "$input_path" "$home_path")
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
SSH_AGENT_FWD=1"

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
SSH_AGENT_FWD=1"

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
SSH_AGENT_FWD=0"

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
SSH_AGENT_FWD=0"

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
SSH_AGENT_FWD=1"

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
    assert_contains "no container running" "$output" "No existing container"
    assert_contains "ssh agent OK" "$output" "SSH agent forwarding: working"
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

    assert_contains "ssh agent warning" "$output" "SSH agent forwarding: not available"
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
# TEST: --yes flag is parsed and sets YES_MODE=1
# ─────────────────────────────────────────────────────────────────────────────
test_yes_flag_long() {
    local output
    output=$(run_parse_args "--yes myhost") || true

    assert_contains "YES_MODE set to 1" "$output" "YES_MODE=1"
    assert_contains "SSH_HOST set" "$output" "SSH_HOST=myhost"
}

test_yes_flag_short() {
    local output
    output=$(run_parse_args "-y myhost") || true

    assert_contains "YES_MODE set to 1 (short)" "$output" "YES_MODE=1"
}

test_yes_flag_default() {
    local output
    output=$(run_parse_args "myhost") || true

    assert_contains "YES_MODE default 0" "$output" "YES_MODE=0"
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: Path and repo URL feedback with auto-derived annotation
# ─────────────────────────────────────────────────────────────────────────────
test_path_auto_derived_annotation() {
    local output
    output=$(run_parse_args "myhost") || true

    assert_contains "path auto-derived" "$output" "PATH_AUTO_DERIVED=1"
}

test_path_explicit_annotation() {
    local output
    output=$(run_parse_args "myhost:/opt/proj") || true

    assert_contains "path explicit" "$output" "PATH_AUTO_DERIVED=0"
}

test_repo_url_source_local() {
    local output
    output=$(run_parse_args "myhost") || true

    assert_contains "repo url source local" "$output" "REPO_URL_SOURCE=local"
}

test_repo_url_source_flag() {
    local output
    output=$(run_parse_args "--repo git@github.com:o/r.git myhost") || true

    assert_contains "repo url source flag" "$output" "REPO_URL_SOURCE=flag"
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: Container-already-running with --yes auto-reuses
# ─────────────────────────────────────────────────────────────────────────────
MOCK_COMPOSE_PS_RUNNING='[{"State":"running","Health":"healthy"}]'
# shellcheck disable=SC2034
MOCK_COMPOSE_PS_EMPTY='[]'

test_container_check_yes_reuses() {
    local output
    output=$(run_container_check "$MOCK_COMPOSE_PS_RUNNING" 1) || true

    assert_contains "reuse msg" "$output" "Reusing existing container"
}

test_container_check_skip_when_not_running() {
    local tmpscript tmpsrc
    tmpscript=$(mktemp "${TMPDIR:-/tmp}/devc_test.XXXXXX")
    tmpsrc=$(mktemp "${TMPDIR:-/tmp}/devc_src.XXXXXX")
    sed 's/^main "\$@"$/# main disabled/' "$DEVC_SCRIPT" > "$tmpsrc"
    TMPFILES+=("$tmpsrc" "$tmpscript")
    {
        echo '#!/usr/bin/env bash'
        echo 'set -euo pipefail'
        echo "source \"$tmpsrc\""
        echo 'ssh() { echo "[]"; }'
        echo 'YES_MODE=0'
        echo 'SSH_HOST="testhost"'
        echo 'REMOTE_PATH="/home/user/repo"'
        echo 'COMPOSE_CMD="podman compose"'
        echo 'CONTAINER_RUNNING=0'
        echo 'check_existing_container'
    } > "$tmpscript"

    local output rc=0
    output=$(bash "$tmpscript" 2>&1) || rc=$?

    assert_not_contains "no reuse when not running" "$output" "Reusing"
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: SSH agent check uses ssh-add -l output
# ─────────────────────────────────────────────────────────────────────────────
MOCK_SSH_ADD_OK="RUNTIME=podman
RUNTIME_VERSION=4.9.3
COMPOSE_AVAILABLE=1
COMPOSE_VERSION=2.24.5
GIT_AVAILABLE=1
REPO_PATH_EXISTS=1
DEVCONTAINER_EXISTS=1
DISK_AVAILABLE_GB=42
OS_TYPE=linux
CONTAINER_RUNNING=0
SSH_AGENT_FWD=1"

MOCK_SSH_ADD_FAIL="RUNTIME=podman
RUNTIME_VERSION=4.9.3
COMPOSE_AVAILABLE=1
COMPOSE_VERSION=2.24.5
GIT_AVAILABLE=1
REPO_PATH_EXISTS=1
DEVCONTAINER_EXISTS=1
DISK_AVAILABLE_GB=42
OS_TYPE=linux
CONTAINER_RUNNING=0
SSH_AGENT_FWD=0"

test_ssh_agent_fwd_ok() {
    local output
    output=$(run_preflight "$MOCK_SSH_ADD_OK") || true

    assert_contains "ssh agent working" "$output" "SSH agent forwarding"
}

test_ssh_agent_fwd_fail() {
    local output
    output=$(run_preflight "$MOCK_SSH_ADD_FAIL") || true

    assert_contains "ssh agent warning" "$output" "SSH agent"
    assert_contains "ssh agent not available" "$output" "not available"
}

# ─────────────────────────────────────────────────────────────────────────────
# TEST: Tilde paths are resolved for editor URI construction
# ─────────────────────────────────────────────────────────────────────────────
test_resolve_remote_path_tilde_prefix() {
    local output
    # shellcheck disable=SC2088
    output=$(run_resolve_path "~/fd5" "/home/user") || true

    assert_contains "tilde prefix resolved" "$output" "/home/user/fd5"
}

test_resolve_remote_path_tilde_only() {
    local output
    output=$(run_resolve_path "~" "/home/user") || true

    assert_contains "tilde only resolved" "$output" "/home/user"
}

test_resolve_remote_path_absolute_passthrough() {
    local output
    output=$(run_resolve_path "/opt/fd5" "/home/user") || true

    assert_contains "absolute path unchanged" "$output" "/opt/fd5"
}

test_resolve_remote_path_relative_prefix() {
    local output
    output=$(run_resolve_path "fd5" "/home/user") || true

    assert_contains "relative path resolved under home" "$output" "/home/user/fd5"
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
test_yes_flag_long
test_yes_flag_short
test_yes_flag_default
test_path_auto_derived_annotation
test_path_explicit_annotation
test_repo_url_source_local
test_repo_url_source_flag
test_container_check_yes_reuses
test_container_check_skip_when_not_running
test_ssh_agent_fwd_ok
test_ssh_agent_fwd_fail
test_resolve_remote_path_tilde_prefix
test_resolve_remote_path_tilde_only
test_resolve_remote_path_absolute_passthrough
test_resolve_remote_path_relative_prefix

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [[ "$FAIL" -gt 0 ]]; then
    exit 1
else
    echo "All tests passed."
fi
