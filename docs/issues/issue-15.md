---
type: issue
state: closed
created: 2026-02-25T01:07:54Z
updated: 2026-02-25T02:35:51Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/15
comments: 1
labels: feature, effort:medium, area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:55.596Z
---

# [Issue 15]: [[FEATURE] Implement JSON Schema embedding and validation](https://github.com/vig-os/fd5/issues/15)

### Description

Implement the `fd5.schema` module: embed `_schema` JSON attribute at file root, validate files against their embedded schema, generate JSON Schema from product schema definitions, and dump schemas.

### Acceptance Criteria

- [ ] `embed_schema(file, schema_dict)` writes `_schema` attr as JSON string and `_schema_version` as int
- [ ] `validate(path) -> list[ValidationError]` validates file structure against embedded schema
- [ ] `dump_schema(path) -> dict` extracts and parses `_schema` from a file
- [ ] `generate_schema(product_type) -> dict` produces a valid JSON Schema Draft 2020-12 document
- [ ] Schema is human-readable via `h5dump -A`
- [ ] ≥ 90% test coverage

### Dependencies

- Depends on #12 (`h5io`) for reading attrs
- Depends on product schema registry (#17) for `generate_schema`

### References

- Epic: #11
- Design: [DES-001 § fd5.schema](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5schema--schema-embedding-and-validation)
- Whitepaper: [§ Embedded schema definition](white-paper.md#9-embedded-schema-definition)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:35 AM_

Completed — merged into dev.

