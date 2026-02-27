---
type: issue
state: open
created: 2026-02-26T10:44:02Z
updated: 2026-02-26T10:44:28Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/158
comments: 0
labels: chore, area:workflow, effort:medium
assignees: gerchowl
milestone: none
projects: none
relationship: none
synced: 2026-02-27T04:11:39.605Z
---

# [Issue 158]: [[CHORE] Add opt-in Tailscale SSH to devcontainer](https://github.com/vig-os/fd5/issues/158)

### Chore Type

Configuration change

### Description

Add opt-in Tailscale SSH support to the devcontainer so developers can connect via direct mesh SSH instead of the devcontainer protocol. This is a workaround for Cursor GUI's inability to execute agent shell commands when connected via the devcontainer protocol.

When `TAILSCALE_AUTHKEY` is set (via `docker-compose.local.yaml`), the devcontainer installs Tailscale on first create and connects to the tailnet on every start with SSH enabled. When the env var is unset, the scripts are a no-op — zero impact on normal usage.

### Acceptance Criteria

- [ ] New `setup-tailscale.sh` script with `install` and `start` subcommands
- [ ] `post-create.sh` calls `setup-tailscale.sh install` (no-op without `TAILSCALE_AUTHKEY`)
- [ ] `post-start.sh` calls `setup-tailscale.sh start` (no-op without `TAILSCALE_AUTHKEY`)
- [ ] `.devcontainer/README.md` updated with quick-start instructions
- [ ] Detailed design doc at `docs/tailscale-devcontainer.md` covering architecture decisions, user setup, known gaps, and upstream considerations
- [ ] `uv.lock` updated (incidental dependency sync)

### Implementation Notes

Files changed:
- **New:** `.devcontainer/scripts/setup-tailscale.sh` — single script, two subcommands (`install` / `start`), idempotent, uses userspace networking (`--tun=userspace-networking`)
- **Modified:** `.devcontainer/scripts/post-create.sh` — hooks `setup-tailscale.sh install`
- **Modified:** `.devcontainer/scripts/post-start.sh` — adds `SCRIPT_DIR` resolution, hooks `setup-tailscale.sh start`
- **Modified:** `.devcontainer/README.md` — new "Tailscale SSH" section
- **New:** `docs/tailscale-devcontainer.md` — full design doc with architecture table, setup guide, known gap (git signing), and upstream notes

### Related Issues

None

### Priority

Medium

### Changelog Category

Added
