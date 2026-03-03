---
type: issue
state: open
created: 2026-03-02T09:34:02Z
updated: 2026-03-02T09:34:02Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/166
comments: 0
labels: feature, effort:medium, area:core, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:32.939Z
---

# [Issue 166]: [[Python] Chain verification in fd5 validate](https://github.com/vig-os/fd5/issues/166)

Parent: #161

## Goal
Extend `fd5 validate` to verify audit chain integrity alongside the Merkle tree.

## Spec
- `verify_chain(file: h5py.File) -> ChainStatus`
- ChainStatus: `Valid`, `NoLog`, `BrokenChain(index, expected, actual)`, `Error(msg)`
- Validation rules:
  1. Each entry's parent_hash must equal the previous entry's implicit new hash
  2. The first entry's parent_hash should be a valid sha256: prefixed hash
  3. No duplicate timestamps with identical changes
- Integrate into `fd5 validate` output: show "Audit chain: N entries, valid" or error
- `verify()` function already exists — add chain check as separate function, call from CLI

## TDD
- Test valid chain passes
- Test tampered entry detected (modify middle entry)
- Test missing entry detected (gap in chain)
- Test file with no log returns NoLog
- Test single-entry chain
