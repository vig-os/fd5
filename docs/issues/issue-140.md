---
type: issue
state: open
created: 2026-02-25T22:30:08Z
updated: 2026-02-25T22:30:08Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/140
comments: 0
labels: docs, area:docs, effort:large, area:core
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:46.221Z
---

# [Issue 140]: [[DOCS] Add user-facing documentation: quickstart guide, API reference, migration guide](https://github.com/vig-os/fd5/issues/140)

### Description

The project's primary documentation is a ~2000-line whitepaper (`white-paper.md`) that serves as a format specification. There is no user-facing documentation aimed at someone who wants to use fd5 in their workflow.

The following documentation is needed:

1. **Quickstart guide** — "I have DICOMs, now what?" Install fd5, ingest a file, inspect the result. 5 minutes to first value.
2. **API reference** — generated from docstrings, covering `fd5.create()`, CLI commands, schema validation, export functions, and (once available) the read API.
3. **Migration guide** — practical guidance for users currently working with NIfTI + sidecar JSON, raw HDF5 layouts, or DICOM-only workflows. What changes, what stays the same.
4. **Conceptual overview** — a 1-page explanation of fd5's core ideas (immutability, provenance DAG, embedded schema, content hashing) for users who don't want to read the full whitepaper.

### Documentation Type

Add new documentation

### Target Files

- `docs/quickstart.md` (new)
- `docs/concepts.md` (new)
- `docs/migration.md` (new)
- `docs/api/` (new, generated — e.g., via sphinx-autodoc or mkdocstrings)
- `README.md` (update — currently just `# README`)

### Related Code Changes

Depends on #135 (merge dev to main) for the codebase to document. Benefits from #136 (read API) for the quickstart.

### Acceptance Criteria

- [ ] README.md includes project description, install instructions, and a minimal usage example
- [ ] Quickstart guide walks through install → ingest → inspect in under 5 minutes of reading
- [ ] Conceptual overview explains core ideas without requiring the whitepaper
- [ ] Migration guide covers at least NIfTI and raw-DICOM workflows
- [ ] API reference is generated from source and covers public modules
- [ ] Documentation builds without errors (if using a doc site generator)

### Changelog Category

Added
