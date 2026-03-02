---
type: issue
state: closed
created: 2026-02-25T07:21:07Z
updated: 2026-02-25T07:52:07Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/92
comments: 1
labels: none
assignees: gerchowl
milestone: Phase 5: Ecosystem & Tooling
projects: none
relationship: none
synced: 2026-02-26T04:15:52.286Z
---

# [Issue 92]: [[FEATURE] DataLad integration hooks](https://github.com/vig-os/fd5/issues/92)

### Description

Provide hooks for DataLad to track fd5 files as annexed content, enabling version-controlled datasets with fd5 metadata.

### Tasks

- [ ] Create `src/fd5/datalad.py` with integration utilities
- [ ] `register_with_datalad(path, dataset_path)` — register an fd5 file with a DataLad dataset
- [ ] `extract_metadata(path) -> dict` — extract fd5 metadata in DataLad-compatible format
- [ ] Support DataLad custom metadata extractor protocol
- [ ] Add `fd5 datalad-register <file> [--dataset <path>]` CLI command
- [ ] Add tests (mock DataLad if not installed)

### Acceptance Criteria

- [ ] Works when DataLad is installed, graceful degradation when not
- [ ] Metadata extraction produces valid DataLad metadata format
- [ ] >= 90% coverage

### References

- White-paper § Scope and Non-Goals (DataLad integration)
- RFC-001 § Phase 5
- Issue #1 comment (file signing / DataLad)
- Epic: #85 | Refs: #10
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 07:52 AM_

Merged — implemented with tests.

