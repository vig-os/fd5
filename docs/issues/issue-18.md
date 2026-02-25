---
type: issue
state: closed
created: 2026-02-25T01:08:25Z
updated: 2026-02-25T02:22:32Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/18
comments: 1
labels: feature, effort:small, area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:54.676Z
---

# [Issue 18]: [[FEATURE] Implement filename generation utility](https://github.com/vig-os/fd5/issues/18)

### Description

Implement the `fd5.naming` module: generate filenames following the `YYYY-MM-DD_HH-MM-SS_<product>-<id>_<descriptors>.h5` convention.

### Acceptance Criteria

- [ ] `generate_filename(product, id_hash, timestamp, descriptors) -> str` produces correctly formatted filenames
- [ ] Timestamp formatted as `YYYY-MM-DD_HH-MM-SS`
- [ ] `id_hash` truncated to first 8 hex chars (after `sha256:` prefix)
- [ ] Descriptors joined with underscores
- [ ] Products without timestamp (simulations, synthetic) omit the datetime prefix
- [ ] ≥ 90% test coverage

### Dependencies

- No blockers; this is a leaf module (stdlib only)

### References

- Epic: #11
- Design: [DES-001 § fd5.naming](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5naming--filename-generation)
- Whitepaper: [§ File Naming Convention](white-paper.md#file-naming-convention)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:22 AM_

Completed — merged into dev.

