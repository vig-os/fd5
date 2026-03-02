---
type: issue
state: closed
created: 2026-02-25T01:08:15Z
updated: 2026-02-25T02:22:31Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/17
comments: 1
labels: feature, effort:small, area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:54.980Z
---

# [Issue 17]: [[FEATURE] Implement product schema registry with entry point discovery](https://github.com/vig-os/fd5/issues/17)

### Description

Implement the `fd5.registry` module: discover product schemas from `importlib.metadata` entry points, look up schema by product type string, and provide a manual `register_schema()` escape hatch for testing.

### Acceptance Criteria

- [ ] `get_schema(product_type) -> ProductSchema` returns registered schema or raises `ValueError`
- [ ] `list_schemas() -> list[str]` returns all registered product type strings
- [ ] `register_schema(product_type, schema)` allows dynamic registration (for testing)
- [ ] Entry point group is `fd5.schemas`
- [ ] `ProductSchema` protocol defined with: `product_type`, `schema_version`, `json_schema()`, `required_root_attrs()`, `write()`, `id_inputs()`
- [ ] ≥ 90% test coverage

### Dependencies

- No blockers; this is a leaf module (uses only `importlib.metadata` stdlib)

### References

- Epic: #11
- Design: [DES-001 § fd5.registry](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5registry--product-schema-registry)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:22 AM_

Completed — merged into dev.

