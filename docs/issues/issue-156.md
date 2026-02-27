---
type: issue
state: open
created: 2026-02-26T08:09:28Z
updated: 2026-02-26T08:09:45Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/156
comments: 0
labels: bug, area:workflow, effort:small, semver:patch
assignees: gerchowl
milestone: none
projects: none
relationship: none
synced: 2026-02-27T04:11:40.009Z
---

# [Issue 156]: [[BUG] devc-remote.sh compose commands run from repo root instead of .devcontainer/](https://github.com/vig-os/fd5/issues/156)

## Description

`scripts/devc-remote.sh` runs all `podman compose` / `docker compose` commands from `$REMOTE_PATH` (the repo root, e.g. `~/fd5`), but the compose files (`docker-compose.yml`, `docker-compose.project.yaml`, `docker-compose.local.yaml`) live in `$REMOTE_PATH/.devcontainer/`. The standalone `docker-compose` binary (used as podman's external compose provider) fails with "no configuration file provided: not found".

## Steps to Reproduce

1. Run `just devc-remote ksb-meatgrinder:~/fd5`
2. Pre-flight passes successfully
3. `remote_compose_up()` executes `cd ~/fd5 && podman compose up -d`
4. `docker-compose` (external provider) can't find any compose file in `~/fd5`

## Expected Behavior

Compose commands should `cd` into `$REMOTE_PATH/.devcontainer` where the compose files reside, so `podman compose up -d` succeeds.

## Actual Behavior

```
>>>> Executing external compose provider "/usr/local/bin/docker-compose". <<<<
no configuration file provided: not found
Error: executing /usr/local/bin/docker-compose up -d: exit status 1
```

## Environment

- **OS**: macOS 24.5.0 (host) → Linux (remote: ksb-meatgrinder)
- **Container Runtime**: Podman 4.9.3 (remote)
- **Compose**: docker-compose v5.1.0 (standalone, used as podman's external compose provider)

## Additional Context

All compose-related SSH commands in the script use `cd $REMOTE_PATH` instead of `cd $REMOTE_PATH/.devcontainer`:
- Line 218/220 (preflight container check)
- Line 351 (`compose_ps_json`)
- Line 383 (`check_existing_container` down)
- Line 409 (`remote_compose_up`)
- Line 411 (error hint message)

## Possible Solution

Change all `cd $REMOTE_PATH` to `cd $REMOTE_PATH/.devcontainer` in compose-related commands.

## Changelog Category

Fixed

- [ ] TDD compliance (see .cursor/rules/tdd.mdc)
