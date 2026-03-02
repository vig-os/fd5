---
type: issue
state: closed
created: 2026-02-25T07:02:50Z
updated: 2026-02-25T07:15:49Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/80
comments: 1
labels: none
assignees: gerchowl
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:55.559Z
---

# [Issue 80]: [[CHORE] Add pytest coverage configuration and reach 100% on all modules](https://github.com/vig-os/fd5/issues/80)

### Description

Current state: 791 tests pass, 98% overall coverage. Several modules have minor gaps:

| Module | Coverage | Missing lines |
|--------|----------|---------------|
| `cli.py` | 94% | 140-144, 156 |
| `create.py` | 95% | 128, 146, 215, 226, 229-230 |
| `datacite.py` | 93% | 84, 123, 125, 130-131 |
| `h5io.py` | 97% | 86, 97 |
| `hash.py` | 96% | 78, 85, 175 |
| `imaging/calibration.py` | 99% | 326 |
| `imaging/listmode.py` | 96% | 154, 160 |
| `imaging/sim.py` | 98% | 130 |
| `imaging/spectrum.py` | 98% | 179, 183, 185 |
| `rocrate.py` | 98% | 113, 119 |

13 modules already at 100%.

### Tasks

- [ ] Add `[tool.coverage.run]` and `[tool.coverage.report]` to `pyproject.toml` with `fail_under = 95`
- [ ] Add tests for uncovered lines in the modules listed above
- [ ] Target 100% on all modules where feasible; document exclusions with `# pragma: no cover` only for genuinely untestable code (e.g., `if TYPE_CHECKING`)
- [ ] Ensure `pytest --cov=fd5 --cov-report=term-missing` runs cleanly with no failures
- [ ] Do NOT modify pyproject.toml entry points, uv.lock, or any source module logic — only add coverage config and new test cases

### Acceptance Criteria

- [ ] All modules >= 98% coverage
- [ ] `[tool.coverage]` config added to `pyproject.toml`
- [ ] No test regressions (all existing 791 tests still pass)

### References

- Refs: #10
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:15 AM_

Merged — coverage config added, gaps closed.

