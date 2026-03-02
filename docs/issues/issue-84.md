---
type: issue
state: closed
created: 2026-02-25T07:16:18Z
updated: 2026-02-25T07:29:23Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/84
comments: 1
labels: none
assignees: gerchowl
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:54.908Z
---

# [Issue 84]: [[CHORE] Fix audit findings: missing dependency, py.typed, default attr, units convention, re-exports](https://github.com/vig-os/fd5/issues/84)

### Description

Implementation audit (#81) identified several small gaps. This issue addresses the quick-fix items.

### Tasks

1. **Add `pyyaml>=6.0` to `[project.dependencies]` in `pyproject.toml`** — `src/fd5/datacite.py` imports `yaml` but the dependency is undeclared. This will break clean installs.

2. **Create `src/fd5/py.typed`** — empty PEP 561 marker file for type checker support. DES-001 specifies this.

3. **Add `default` root attribute to all product schemas** — white-paper specifies a `default` attr pointing to the "best" dataset. Add to `write()` in each schema:
   - `recon`: `"volume"`
   - `listmode`: `"raw_data"`
   - `sinogram`: `"sinogram"`
   - `sim`: `"phantom"` or `"volume"`
   - `transform`: `"matrix"` or `"field"`
   - `calibration`: already has it
   - `spectrum`: already has it
   - `roi`: `"contours"` or `"mask"`
   - `device_data`: `"channels"`

4. **Fix listmode units convention** — `z_min`, `z_max`, `duration`, `table_pos` in `src/fd5/imaging/listmode.py` should use `write_quantity()` from `fd5.units` (sub-group pattern with value/units/unitSI) instead of flat `np.float64` attrs.

5. **Add public re-exports in `src/fd5/__init__.py`** — export `create`, `validate`, `verify`, `generate_filename` for ergonomic top-level imports.

### Acceptance Criteria

- [ ] `pyyaml` declared in dependencies
- [ ] `py.typed` exists
- [ ] All schemas write `default` attr
- [ ] `listmode` uses units sub-group pattern for z_min/z_max/duration/table_pos
- [ ] `from fd5 import create, validate, verify` works
- [ ] All existing tests still pass (no regressions)
- [ ] Run `pytest --cov=fd5 --cov-report=term-missing` to confirm no coverage regression

### References

- Audit report: #81
- Refs: #10
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:29 AM_

Merged — all audit quick-fixes applied.

