---
type: issue
state: open
created: 2026-03-02T09:33:45Z
updated: 2026-03-02T09:33:45Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/163
comments: 0
labels: feature, effort:medium, area:core, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:33.800Z
---

# [Issue 163]: [[Python] Identity system (~/.fd5/identity.toml)](https://github.com/vig-os/fd5/issues/163)

Parent: #161

## Goal
Create `fd5.identity` module for loading and managing user identity from `~/.fd5/identity.toml`.

## Spec
- `Identity` dataclass: `type` (orcid/github/email/anonymous), `id` (string), `name` (string)
- `load_identity() -> Identity` — read from `~/.fd5/identity.toml`, return anonymous if missing
- `save_identity(identity: Identity)` — write to `~/.fd5/identity.toml`
- `identity_to_dict(identity: Identity) -> dict` — for embedding in audit entries
- Support for `type` values: `orcid`, `github`, `email`, `anonymous`

### TOML format
```toml
[identity]
type = "orcid"
id = "0000-0002-1825-0097"
name = "Lars Gerchow"
```

## TDD
- Test load from valid TOML file
- Test load returns anonymous when file missing
- Test save + load round-trip
- Test validation of identity types
- Test ORCID format validation (XXXX-XXXX-XXXX-XXXX)
