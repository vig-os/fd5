---
type: issue
state: closed
created: 2026-02-25T05:58:00Z
updated: 2026-02-25T07:01:09Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/59
comments: 1
labels: area:core
assignees: gerchowl
milestone: Phase 4: FAIR Export Layer
projects: none
relationship: none
synced: 2026-02-26T04:15:57.226Z
---

# [Issue 59]: [[FEATURE] Implement RO-Crate JSON-LD export (fd5.rocrate)](https://github.com/vig-os/fd5/issues/59)

### Description

Implement `fd5.rocrate` module to generate `ro-crate-metadata.json` conforming to the RO-Crate 1.2 specification from fd5 manifest and HDF5 metadata.

See `white-paper.md` § `ro-crate-metadata.json` (line ~1473) for the mapping specification.

### Schema.org mapping

- `study/license` → `license`
- `study/creators/` → `author` (as `Person` entities with ORCID)
- `id` → `identifier` (as `PropertyValue` with `propertyID: "sha256"`)
- `timestamp` → `dateCreated`
- `provenance/ingest/` → `CreateAction` with `SoftwareApplication`
- `sources/` DAG → `isBasedOn` references
- Each `.h5` file → `File` (MediaObject) with `encodingFormat: "application/x-hdf5"`

### Acceptance Criteria

- [ ] `generate(manifest_path) -> dict` produces valid RO-Crate 1.2 JSON-LD
- [ ] `write(manifest_path, output_path)` writes the JSON-LD file
- [ ] Maps all fields listed in the white paper
- [ ] CLI command `fd5 rocrate <dir>` added
- [ ] >= 90% test coverage
- [ ] Output validates against RO-Crate profile (if a validator exists)

### Dependencies

- #20 (manifest) — completed
- All core modules — completed

### References

- `white-paper.md` § `ro-crate-metadata.json`
- [RO-Crate 1.2 spec](https://w3id.org/ro/crate/1.2)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:01 AM_

Merged — RO-Crate export implemented with tests.

