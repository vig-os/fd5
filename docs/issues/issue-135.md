---
type: issue
state: open
created: 2026-02-25T22:28:42Z
updated: 2026-02-25T22:28:42Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/135
comments: 0
labels: chore, priority:high, area:core
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:47.729Z
---

# [Issue 135]: [[CHORE] Merge dev branch to main, tag v0.1.0, and publish to PyPI](https://github.com/vig-os/fd5/issues/135)

### Chore Type

General task

### Description

The `dev` branch contains 126 commits and ~29K lines of implementation code (36 Python modules covering core primitives, imaging schemas, CLI, RO-Crate/DataCite export, DataLad hooks, ingest loaders, and benchmarks). The `main` branch contains only the whitepaper and an empty `__init__.py`.

No installable package exists — `pip install fd5` does not work. The README is a single heading (`# README`).

This task covers:
1. Review and merge the `dev` branch into `main`
2. Resolve any conflicts with recent `main` changes
3. Tag the merge as `v0.1.0`
4. Set up PyPI publishing (via the existing `release.yml` workflow or equivalent)
5. Verify `pip install fd5` works from PyPI

### Acceptance Criteria

- [ ] `dev` branch merged into `main`
- [ ] All CI checks pass on `main` after merge
- [ ] Git tag `v0.1.0` exists on `main`
- [ ] Package is published to PyPI (or TestPyPI as a first step)
- [ ] `pip install fd5` installs the package with core dependencies
- [ ] `pip install fd5[science]` and `pip install fd5[dev]` extras work
- [ ] README on `main` reflects the current state of the project

### Implementation Notes

The `release.yml` workflow already exists in `.github/workflows/`. Verify it is configured for PyPI publishing (trusted publisher or token-based). Consider whether TestPyPI should be used first. The `pyproject.toml` build system uses hatchling.

### Related Issues

Blocks all downstream adoption and testing work.

### Priority

High

### Changelog Category

No changelog needed
