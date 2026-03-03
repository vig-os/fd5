---
type: issue
state: open
created: 2026-03-02T09:33:29Z
updated: 2026-03-02T09:33:29Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/161
comments: 0
labels: priority:high, epic, area:core, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:34.378Z
---

# [Issue 161]: [[EPIC] Audit trail: git-like edit history with identity for fd5 files](https://github.com/vig-os/fd5/issues/161)

## Summary

Transform fd5's `edit` capability into a **tamper-evident audit trail** embedded inside the HDF5 file. Every attribute change becomes a logged, immutable entry — like git commits for HDF5 metadata — optionally tied to verified identity (ORCID, GitHub, email).

## Design

### Audit log storage
- Root attribute `_fd5_audit_log`: JSON array of commit entries
- Included in the Merkle tree hash (NOT in `EXCLUDED_ATTRS`) → tamper-evident automatically
- Each entry records `parent_hash` (content_hash before the edit), NOT the new hash (avoids circular dependency)

### Commit entry schema
```json
{
  "parent_hash": "sha256:abc...",
  "timestamp": "2026-03-02T14:30:00Z",
  "author": {
    "type": "orcid",
    "id": "0000-0002-1825-0097",
    "name": "Lars Gerchow"
  },
  "message": "Updated calibration factor",
  "changes": [
    {
      "action": "edit",
      "path": "/sensors/temperature",
      "attr": "calibration_factor",
      "old": "1.0",
      "new": "1.05"
    }
  ]
}
```

### Hash chain
```
State S0 ──edit──▶ State S1 ──edit──▶ State S2
 H0                 H1                 H2 (= current content_hash)
```
- Entry N records `parent_hash = H_{N-1}`
- The new hash H_N is implicitly the next entry's parent_hash, or the current content_hash

### Identity (`~/.fd5/identity.toml`)
```toml
[identity]
type = "orcid"
id = "0000-0002-1825-0097"
name = "Lars Gerchow"
```
Supported types: `orcid`, `github`, `email`, `anonymous`

### Chain verification
Extend `verify` to validate audit chain integrity:
1. Walk entries, check parent_hash continuity
2. Final entry's implicit new hash = current content_hash
3. Detect gaps, tampered entries, broken chains

## Sub-issues
- [ ] **Python**: Audit log data model + read/write
- [ ] **Python**: Identity system (`~/.fd5/identity.toml`)
- [ ] **Python**: `fd5 edit` CLI command with audit logging
- [ ] **Python**: `fd5 log` CLI command
- [ ] **Python**: Chain verification in `fd5 validate`
- [ ] **Rust**: Audit log data model + read/write in fd5 crate
- [ ] **Rust**: Identity system
- [ ] **Rust**: Edit with audit logging in fd5 crate
- [ ] **Rust**: Chain verification in fd5 crate
- [ ] **h5v**: `:log` command to display audit history
- [ ] **h5v**: `:edit` with audit trail integration
- [ ] **h5v**: `:identity` command

## Approach
- RED-GREEN TDD: write failing tests first, then implement
- Python and Rust tracks in parallel (same spec, independent implementations)
- h5v depends on Rust fd5 crate changes
