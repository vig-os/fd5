---
type: issue
state: closed
created: 2026-02-25T05:58:01Z
updated: 2026-02-25T07:01:11Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/60
comments: 1
labels: area:core
assignees: gerchowl
milestone: Phase 4: FAIR Export Layer
projects: none
relationship: none
synced: 2026-02-26T04:15:56.836Z
---

# [Issue 60]: [[FEATURE] Implement DataCite metadata export (fd5.datacite)](https://github.com/vig-os/fd5/issues/60)

### Description

Implement `fd5.datacite` module to generate `datacite.yml` metadata for data catalogs and discovery. Generated from manifest and HDF5 metadata.

See `white-paper.md` § `datacite.yml` (line ~1453) for the specification.

### Acceptance Criteria

- [ ] `generate(manifest_path) -> dict` produces DataCite-compatible YAML structure
- [ ] `write(manifest_path, output_path)` writes datacite.yml
- [ ] Maps title, creators, dates, resourceType, subjects from fd5 metadata
- [ ] CLI command `fd5 datacite <dir>` added
- [ ] >= 90% test coverage

### Dependencies

- #20 (manifest) — completed

### References

- `white-paper.md` § `datacite.yml`
- [DataCite Metadata Schema](https://schema.datacite.org/)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:01 AM_

Merged — DataCite export implemented with tests.

