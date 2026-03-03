---
type: issue
state: open
created: 2026-03-02T09:34:11Z
updated: 2026-03-02T09:34:11Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/168
comments: 0
labels: feature, effort:medium, area:core, audit-trail
assignees: none
milestone: none
projects: none
relationship: none
synced: 2026-03-03T04:13:32.412Z
---

# [Issue 168]: [[Rust] Identity system in fd5 crate](https://github.com/vig-os/fd5/issues/168)

Parent: #161

## Goal
Add `identity` module to the `fd5` Rust crate for loading `~/.fd5/identity.toml`.

## Spec
- `Identity` struct (serde): `identity_type: String`, `id: String`, `name: String`
- `load_identity() -> Fd5Result<Identity>` — read `~/.fd5/identity.toml`, anonymous fallback
- `save_identity(identity: &Identity) -> Fd5Result<()>`
- `Identity::anonymous() -> Identity` — default anonymous identity
- `Identity::to_author() -> Author` — convert to Author struct for audit entries

### TOML format
```toml
[identity]
type = "orcid"
id = "0000-0002-1825-0097"
name = "Lars Gerchow"
```

## TDD
- Test load from valid TOML
- Test missing file → anonymous
- Test save + load round-trip
- Test identity type validation
- Test to_author conversion
