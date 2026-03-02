---
type: issue
state: closed
created: 2026-02-25T06:17:53Z
updated: 2026-02-25T06:23:30Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/63
comments: 1
labels: area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-26T04:15:56.198Z
---

# [Issue 63]: [[BUG] CI lint fails: check-action-pins and validate-commit-msg unavailable outside devcontainer](https://github.com/vig-os/fd5/issues/63)

### Description

The CI lint job now runs `pre-commit` successfully (#48 fixed the spawn error), but fails on two local hooks that depend on `vig-utils` — a package only available inside the vigOS devcontainer:

```
check-action-pins (verify SHA-pinned actions)....Failed
error: Failed to spawn: `check-action-pins`
  Caused by: No such file or directory (os error 2)
```

The affected hooks:
- `check-action-pins` — calls `uv run check-action-pins` (from `vig_utils.check_action_pins`)
- `validate-commit-msg` — calls `uv run validate-commit-msg` (from `vig_utils`)

Both are entry points from `vig-utils` (v0.1.0), which is installed system-wide in the devcontainer but is not on PyPI.

### Fix

Add `vig-utils` to the project's dev dependencies so `uv sync` installs it in CI. The package has no external dependencies and is MIT licensed.

If `vig-utils` is not on any pip-installable registry, the alternative is to install it from the devcontainer's wheel/sdist in the CI setup action, or skip these hooks in CI with `SKIP=check-action-pins,validate-commit-msg`.

### Acceptance Criteria

- [ ] `uv run pre-commit run --all-files` passes in CI (no spawn errors)
- [ ] `check-action-pins` hook either runs or is cleanly skipped
- [ ] `validate-commit-msg` hook either runs or is cleanly skipped
- [ ] CI lint job goes green

### References

- `vig-utils` package: `/usr/local/lib/python3.12/site-packages/vig_utils/`
- `.pre-commit-config.yaml` lines 102-109 and 131-145
- CI failure: https://github.com/vig-os/fd5/actions/runs/22384324406
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 06:23 AM_

Completed — CI lint now passes. vig-utils hooks skipped in CI with SKIP env var.

