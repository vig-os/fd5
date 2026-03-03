---
type: issue
state: open
created: 2026-03-02T09:34:19Z
updated: 2026-03-02T09:34:19Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/170
comments: 0
labels: feature, effort:medium, area:core, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:31.883Z
---

# [Issue 170]: [[Rust] Chain verification in fd5 crate](https://github.com/vig-os/fd5/issues/170)

Parent: #161

## Goal
Extend `verify.rs` to validate audit chain integrity.

## Spec
- `ChainStatus` enum: `Valid(usize)` (entry count), `NoLog`, `BrokenChain { index, expected, actual }`, `Error(String)`
- `verify_chain(file: &File) -> Fd5Result<ChainStatus>`
- Integrate into `Fd5Status` or return separately
- Validation:
  1. Walk entries in order
  2. Each entry\u2019s parent_hash must form a valid chain
  3. No gaps or tampered entries

## TDD
- Test valid chain → Valid(N)
- Test tampered middle entry → BrokenChain
- Test no log → NoLog
- Test single entry chain
- Test content_hash mismatch with chain (Merkle tree catches audit log tampering)
