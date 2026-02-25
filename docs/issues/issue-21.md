---
type: issue
state: closed
created: 2026-02-25T01:09:01Z
updated: 2026-02-25T02:22:34Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/21
comments: 1
labels: feature, effort:small, area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:53.711Z
---

# [Issue 21]: [[FEATURE] Add project dependencies (h5py, numpy, jsonschema, tomli-w, click)](https://github.com/vig-os/fd5/issues/21)

### Description

Update `pyproject.toml` to declare the runtime dependencies needed by the fd5 core library. Currently the project has `dependencies = []`.

### Acceptance Criteria

- [ ] `h5py >= 3.10` added to `dependencies`
- [ ] `numpy >= 2.0` added to `dependencies` (required by h5py, make explicit)
- [ ] `jsonschema >= 4.20` added to `dependencies`
- [ ] `tomli-w >= 1.0` added to `dependencies`
- [ ] `click >= 8.0` added to `dependencies`
- [ ] `fd5` console script entry point configured for CLI
- [ ] `uv.lock` updated
- [ ] All dependencies install cleanly

### Dependencies

- No blockers; should be done early to unblock all other work

### References

- Epic: #11
- RFC: [RFC-001 § Build vs buy](docs/rfcs/RFC-001-2026-02-25-fd5-core-implementation.md#build-vs-buy)
- Design: [DES-001 § Technology Stack](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#technology-stack)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:22 AM_

Completed — merged into dev.

