---
type: issue
state: open
created: 2026-03-02T09:33:56Z
updated: 2026-03-02T09:33:56Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/165
comments: 0
labels: feature, effort:small, area:core, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:33.220Z
---

# [Issue 165]: [[Python] fd5 log CLI command](https://github.com/vig-os/fd5/issues/165)

Parent: #161

## Goal
Add `fd5 log` CLI subcommand to display the audit trail.

## Spec
- `fd5 log <file>` — display audit history, newest first
- Output format (git-log style):
  ```
  commit sha256:def456...
  Parent: sha256:abc123...
  Author: Lars Gerchow <orcid:0000-0002-1825-0097>
  Date:   2026-03-02T14:30:00Z

      Updated calibration factor

      M /sensors/temperature.calibration_factor  1.0 → 1.05
  ```
- `fd5 log <file> --json` — machine-readable JSON output
- Exit 0 if log exists, exit 1 if no audit log

## TDD
- Test output format matches spec
- Test empty log
- Test --json flag
- Test multiple entries display in reverse order
