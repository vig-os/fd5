---
type: issue
state: open
created: 2026-02-25T22:30:33Z
updated: 2026-02-25T22:32:21Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/142
comments: 0
labels: chore, effort:medium, area:core
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:45.662Z
---

# [Issue 142]: [[CHORE] Improve fd5 validate UX: error messages, examples, and trust-building](https://github.com/vig-os/fd5/issues/142)

### Description

`fd5 validate` exists as a CLI command (implemented on the `dev` branch), but its practical usefulness to end users is unclear. Schema validation is only valuable if users trust it catches real problems and understand its output.

This task covers:

1. **Error message quality** — Review all validation error messages. Ensure they identify what's wrong, where in the file, and how to fix it. Avoid raw JSON Schema jargon.
2. **Example gallery** — Create a set of intentionally malformed fd5 files (missing required attrs, wrong types, broken content hash, missing provenance) and document what `fd5 validate` reports for each. This serves as both a test suite and a user reference.
3. **Exit codes and output format** — Ensure the CLI returns appropriate exit codes (0 for valid, non-zero for invalid) and supports both human-readable and machine-readable (JSON) output for CI integration.
4. **Documentation** — Add a "Validating fd5 files" section to the docs showing common validation scenarios and their output.

### Acceptance Criteria

- [ ] At least 5 distinct validation failure cases are documented with example output
- [ ] Error messages include the file path, HDF5 group/attribute path, expected vs actual value, and a remediation hint where possible
- [ ] `fd5 validate` returns exit code 0 for valid files and non-zero for invalid files
- [ ] JSON output mode is available (`fd5 validate --format json`)
- [ ] A malformed-file test fixture set exists in `tests/fixtures/` or equivalent

### Implementation Notes

The JSON Schema validation in `schema.py` provides the foundation. The error message improvements may require wrapping `jsonschema` validation errors with fd5-specific context. The malformed file fixtures can be generated programmatically in a test helper.

### Related Issues

Related to #135 (must be on main to test), #137 (demo notebook should show validation)

### Priority

Medium
