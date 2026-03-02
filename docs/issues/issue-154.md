---
type: issue
state: open
created: 2026-02-26T01:03:41Z
updated: 2026-02-26T01:03:41Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/154
comments: 0
labels: docs, priority:high, area:docs, effort:medium, area:core
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:42.930Z
---

# [Issue 154]: [[DOCS] Extract fd5 format specification as a standalone language-neutral document](https://github.com/vig-os/fd5/issues/154)

### Parent

Prerequisite for #144 — Multi-language fd5 bindings

### Description

Extract the fd5 HDF5 layout conventions from the white paper and Python reference implementation into a standalone, versioned format specification document. This spec should be the canonical definition of what makes an HDF5 file a valid fd5 file — independent of any programming language.

### Motivation

Today the fd5 format is defined implicitly by the white paper (prose) and the Python code (implementation). To build bindings in Rust (#145), Julia (#146), C/C++ (#147), and TypeScript (#148), each team needs an unambiguous, machine-testable spec to implement against — not reverse-engineering from Python source.

### Proposed Content

The spec document should cover:

1. **File-level requirements** — required root attributes (`id`, `_type`, `_version`, `created`, `product_type`, `_schema`), naming conventions, HDF5 version constraints
2. **Group structure** — required and optional groups (`metadata/`, `sources/`, `precomputed/`), nesting rules
3. **Dataset conventions** — required attributes (`@units`, `@unitSI`, `description`), dtype constraints, chunking recommendations, compression
4. **Schema embedding** — JSON Schema format, `_schema` attribute location and structure
5. **Content hashing** — algorithm (SHA-256), which bytes are included/excluded, attribute name and format for the stored hash
6. **Provenance model** — `sources/` group structure, link format, DAG rules
7. **Product type system** — how `product_type` maps to structural requirements, extensibility via product schemas
8. **Metadata conventions** — ISO 8601 timestamps, vocabulary/code attributes, unit conventions (NeXus/OpenPMD alignment)
9. **Immutability contract** — write-once semantics, what "sealed" means

### Format

- Markdown document in `docs/spec/` (versioned alongside the code)
- Normative language (MUST, SHOULD, MAY per RFC 2119)
- Include example `h5dump -A` output for a minimal valid fd5 file
- Include a JSON Schema for the root-level `_schema` attribute itself (meta-schema)

### Acceptance Criteria

- [ ] Spec document is sufficient for an implementer to write a valid fd5 file without reading any Python code
- [ ] All MUST/SHOULD/MAY requirements are testable (can be verified programmatically)
- [ ] The Python reference implementation passes all MUST requirements in the spec
- [ ] Reviewed by at least one person who has not read the Python source

### Additional Context

- The white paper (`white-paper.md`) contains most of the design rationale but mixes normative requirements with motivation and examples — the spec should be the distilled, normative subset
- This is a prerequisite for the cross-language conformance test suite (#144)
