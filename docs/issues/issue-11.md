---
type: issue
state: closed
created: 2026-02-25T01:07:00Z
updated: 2026-02-25T02:48:48Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/11
comments: 1
labels: epic, area:core
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-02-25T04:19:57.105Z
---

# [Issue 11]: [[EPIC] fd5 Core Implementation (Phases 1–2)](https://github.com/vig-os/fd5/issues/11)

## fd5 Core Implementation

Implement the fd5 Python SDK: core library (Phase 1) and first domain schema + CLI (Phase 2).

### References

- **RFC:** [RFC-001](docs/rfcs/RFC-001-2026-02-25-fd5-core-implementation.md) — problem, scope, phasing, success criteria
- **Design:** [DES-001](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md) — architecture, components, data flow
- **Whitepaper:** [white-paper.md](white-paper.md) — full format specification

### Phase 1: Core SDK

- [ ] #21 — Add project dependencies
- [ ] #12 — `h5_to_dict` / `dict_to_h5` metadata helpers
- [ ] #13 — Physical units convention helpers
- [ ] #24 — [SPIKE] Validate h5py streaming chunk write + inline hashing
- [ ] #14 — Merkle tree hashing and `content_hash` computation
- [ ] #15 — JSON Schema embedding and validation
- [ ] #16 — Provenance group writers (`sources/`, `provenance/`)
- [ ] #17 — Product schema registry with entry point discovery
- [ ] #18 — Filename generation utility
- [ ] #20 — TOML manifest generation and parsing
- [ ] #19 — `fd5.create()` builder / context-manager API

### Phase 2: Recon Schema + CLI

- [ ] #22 — `recon` product schema (`fd5-imaging`)
- [ ] #23 — CLI commands (`validate`, `info`, `schema-dump`, `manifest`)

### Dependency order

```
#21 (deps) ──→ all modules
#12 (h5io) ──→ #14 (hash), #15 (schema), #16 (provenance), #20 (manifest)
#13 (units) ──→ #19 (create)
#24 (spike) ──→ #14 (hash)
#17 (registry) ──→ #15 (schema), #19 (create)
#18 (naming) ──→ #19 (create)
#19 (create) ──→ #22 (recon), #23 (cli)
```

### Success Criteria

See [RFC-001 § Success Criteria](docs/rfcs/RFC-001-2026-02-25-fd5-core-implementation.md#success-criteria).
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:48 AM_

All Phase 1 and Phase 2 sub-issues completed and merged into dev. Epic complete.

