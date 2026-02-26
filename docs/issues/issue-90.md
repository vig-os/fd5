---
type: issue
state: closed
created: 2026-02-25T07:20:55Z
updated: 2026-02-25T07:58:11Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/90
comments: 1
labels: none
assignees: gerchowl
milestone: Phase 5: Ecosystem & Tooling
projects: none
relationship: none
synced: 2026-02-26T04:15:52.987Z
---

# [Issue 90]: [[FEATURE] Performance benchmarks for create/validate/hash workflows](https://github.com/vig-os/fd5/issues/90)

### Description

Establish baseline performance benchmarks for core fd5 operations to detect regressions and guide optimization.

### Tasks

- [ ] Create `benchmarks/` directory with pytest-benchmark or standalone scripts
- [ ] Benchmark `fd5.create()` for files of varying sizes (1MB, 10MB, 100MB, 1GB)
- [ ] Benchmark `fd5 validate` (schema validation + content_hash verification)
- [ ] Benchmark `compute_content_hash()` alone vs streaming ChunkHasher (if #86 is complete)
- [ ] Benchmark `h5_to_dict` / `dict_to_h5` round-trip for deeply nested metadata
- [ ] Benchmark manifest generation for directories with 10, 100, 1000 files
- [ ] Document results in `docs/benchmarks.md` with hardware specs

### Acceptance Criteria

- [ ] Reproducible benchmark suite that can be run with a single command
- [ ] Baseline numbers documented
- [ ] No performance regressions from current state

### References

- RFC-001 § Risk R5 (performance)
- RFC-001 § Phase 5
- Epic: #85 | Refs: #10
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:58 AM_

Merged — benchmark suite added.

