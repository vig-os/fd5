---
type: issue
state: closed
created: 2026-02-25T01:08:05Z
updated: 2026-02-25T02:35:52Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/16
comments: 1
labels: feature, effort:medium, area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:55.265Z
---

# [Issue 16]: [[FEATURE] Implement provenance group writers (sources/, provenance/)](https://github.com/vig-os/fd5/issues/16)

### Description

Implement the `fd5.provenance` module: write `sources/` group with HDF5 external links and metadata attrs, write `provenance/original_files` compound dataset, and write `provenance/ingest/` attrs.

### Acceptance Criteria

- [ ] `write_sources(file, sources_list)` creates `sources/` group with sub-groups per source, each containing `id`, `product`, `file`, `content_hash`, `role`, `description` attrs and an HDF5 external link
- [ ] `write_original_files(file, file_records)` creates `provenance/original_files` compound dataset with `(path, sha256, size_bytes)` columns
- [ ] `write_ingest(file, tool, version, timestamp)` writes `provenance/ingest/` group attrs
- [ ] External links use relative paths
- [ ] ≥ 90% test coverage

### Dependencies

- Depends on #12 (`h5io`) for attr writing

### References

- Epic: #11
- Design: [DES-001 § fd5.provenance](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5provenance--provenance-groups)
- Whitepaper: [§ sources/ group](white-paper.md#sources-group----provenance-dag), [§ provenance/ group](white-paper.md#provenance-group----original-file-provenance)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:35 AM_

Completed — merged into dev.

