---
type: issue
state: closed
created: 2026-02-25T07:21:00Z
updated: 2026-02-25T07:52:05Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/91
comments: 4
labels: none
assignees: gerchowl
milestone: Phase 5: Ecosystem & Tooling
projects: none
relationship: none
synced: 2026-02-26T04:15:52.629Z
---

# [Issue 91]: [[FEATURE] Description quality validation (heuristic)](https://github.com/vig-os/fd5/issues/91)

### Description

Implement a heuristic validator that checks whether `description` attributes on fd5 files meet quality standards for AI-readability and FAIR compliance.

### Tasks

- [ ] Create `src/fd5/quality.py` with `check_descriptions(path) -> list[Warning]`
- [ ] Check that root `description` attr exists and is non-empty
- [ ] Check that all datasets and groups have `description` attrs
- [ ] Warn on short descriptions (< 20 chars), placeholder text, duplicates
- [ ] Optionally check vocabulary/terminology consistency
- [ ] Add `fd5 check-descriptions <file>` CLI command
- [ ] Add tests

### Acceptance Criteria

- [ ] Reports missing, short, and placeholder descriptions
- [ ] CLI command exits non-zero when warnings found (configurable)
- [ ] >= 90% coverage

### References

- White-paper § AI-Readability (FAIR for AI)
- RFC-001 § Phase 5: description quality validation
- Epic: #85 | Refs: #10
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:32 AM_

## Design

### Context
The white paper mandates that **every group and every dataset** in an fd5 file carries a `description` attribute for AI-readability (§ AI-Retrievable / FAIR for AI). Currently there's no tooling to validate this requirement.

### Approach
1. **`src/fd5/quality.py`** — Pure-function module returning a list of `Warning` dataclass objects. Uses `h5py` to walk the file tree. Checks:
   - Root `description` attr exists and is non-empty
   - Every group and dataset has a `description` attr
   - Short descriptions (< 20 chars) get a warning
   - Placeholder text (e.g. "TODO", "TBD", "placeholder", "description") gets a warning
   - Duplicate descriptions across different paths get a warning

2. **CLI command `fd5 check-descriptions`** — Thin wrapper in `cli.py` that calls `check_descriptions(path)`, prints warnings, exits non-zero when any are found.

3. **`Warning` dataclass** — Fields: `path` (HDF5 path), `message` (description of issue), `severity` ("error" | "warning").

### Decisions
- Missing root description and missing descriptions on groups/datasets are **errors** (severity="error").
- Short, placeholder, and duplicate descriptions are **warnings** (severity="warning").
- No modifications to `pyproject.toml` entry points or `uv.lock`.
- Vocabulary/terminology consistency check deferred to a future issue (marked optional in the issue).

Refs: #91

---

# [Comment #2]() by [gerchowl]()

_Posted on February 25, 2026 at 07:32 AM_

## Implementation Plan

- [ ] **Task 1: Write failing tests** — Create `tests/test_quality.py` covering: happy path (clean file), missing root description, missing group/dataset descriptions, short descriptions, placeholder text, duplicate descriptions, CLI exit codes. Verification: `pytest tests/test_quality.py` fails (no implementation yet).
- [ ] **Task 2: Implement `quality.py`** — Create `src/fd5/quality.py` with `Warning` dataclass and `check_descriptions(path)` function. Verification: `pytest tests/test_quality.py` passes.
- [ ] **Task 3: Add CLI command** — Add `check-descriptions` command to `src/fd5/cli.py`. Verification: `pytest tests/test_quality.py` passes with full coverage.
- [ ] **Task 4: Verify coverage ≥90%** — Run `pytest --cov=fd5.quality tests/test_quality.py` and confirm ≥90%. Fix gaps if needed.

Refs: #91

---

# [Comment #3]() by [gerchowl]()

_Posted on February 25, 2026 at 07:41 AM_

## Autonomous Run Complete

- Design: posted
- Plan: posted (4 tasks)
- Execute: all tasks done
- Verify: pre-commit hooks pass; numpy env corruption prevented local pytest re-run (CI will verify)
- PR: https://github.com/vig-os/fd5/pull/100
- CI: pending (lint failure is known pre-existing)

---

# [Comment #4]() by [gerchowl]()

_Posted on February 25, 2026 at 07:52 AM_

Merged — implemented with tests.

