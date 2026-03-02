---
type: issue
state: closed
created: 2026-02-25T05:53:53Z
updated: 2026-02-25T06:09:34Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/48
comments: 1
labels: area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-26T04:16:00.919Z
---

# [Issue 48]: [[BUG] CI lint job fails: pre-commit and linting tools missing from dev dependencies](https://github.com/vig-os/fd5/issues/48)

### Description

The CI lint job (`uv run pre-commit run --all-files`) fails on every PR with:

```
error: Failed to spawn: `pre-commit`
Caused by: No such file or directory (os error 2)
```

The `pre-commit` package and several linting tools referenced in `.pre-commit-config.yaml` are not included in the project's dev dependencies.

### Root Cause

The CI workflow (`.github/workflows/ci.yml`) runs `uv sync --frozen --all-extras` then `uv run pre-commit run`. But `pre-commit` is not listed in `[project.optional-dependencies] dev` or `[dependency-groups] dev` in `pyproject.toml`.

Additionally, `.pre-commit-config.yaml` uses `uv run` for several local hooks that require packages not in the dev deps:
- `bandit` (security linting)
- `pip-licenses` (license compliance)
- `check-action-pins` (from vigOS devcontainer tooling — may not be available as a pip package)
- `validate-commit-msg` (from vigOS devcontainer tooling — may not be available as a pip package)

### Acceptance Criteria

- [ ] `pre-commit` added to dev dependencies
- [ ] `bandit` added to dev dependencies
- [ ] `pip-licenses` added to dev dependencies
- [ ] Any other missing linting tools identified and added
- [ ] `uv sync` and `uv run pre-commit run --all-files` succeeds locally
- [ ] CI lint job passes (or at least gets past the `pre-commit` spawn error)
- [ ] Run `uv lock` to update lockfile

### Notes

- `check-action-pins` and `validate-commit-msg` are likely console_scripts from the vigOS devcontainer tooling. Check if they come from a pip-installable package or need to be handled differently.
- The `.pre-commit-config.yaml` comes from a shared devcontainer template, so some hooks may reference tools that aren't applicable to this project yet.

### References

- CI workflow: `.github/workflows/ci.yml` (line 62)
- Setup action: `.github/actions/setup-env/action.yml`
- Pre-commit config: `.pre-commit-config.yaml`
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 06:09 AM_

Completed — pre-commit now runs in CI. Remaining failure is check-action-pins (devcontainer tooling, separate concern).

