---
type: issue
state: closed
created: 2026-02-25T06:21:21Z
updated: 2026-02-25T06:26:57Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/65
comments: 1
labels: area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-26T04:15:55.907Z
---

# [Issue 65]: [[DOCS] Update README with project overview, quickstart, and API reference](https://github.com/vig-os/fd5/issues/65)

### Description

The README is empty (`# README`) and the CHANGELOG is missing entries for most implemented modules. The RFC success criteria requires: "README with quickstart; API docstrings on all public functions."

### Acceptance Criteria

#### README.md

- [ ] Project title and one-line description
- [ ] Badges (CI status, Python version, license)
- [ ] What is fd5? (2-3 paragraphs summarizing the FAIR data format)
- [ ] Key features list (self-describing, immutable, content-hashed, etc.)
- [ ] Installation: `pip install fd5`
- [ ] Quickstart example showing `fd5.create()` usage with the recon schema
- [ ] CLI usage examples (`fd5 validate`, `fd5 info`, `fd5 schema-dump`, `fd5 manifest`)
- [ ] Architecture overview (link to DES-001)
- [ ] Extending with domain schemas (link to ProductSchema Protocol)
- [ ] Development setup (uv sync, pre-commit, pytest)
- [ ] Links to RFC, Design doc, white paper
- [ ] License

#### CHANGELOG.md

- [ ] Entries under `## Unreleased` for ALL implemented modules:
  - Dependencies (#21)
  - `fd5.h5io` (#12)
  - `fd5.units` (#13)
  - `fd5.hash` (#14)
  - `fd5.schema` (#15)
  - `fd5.provenance` (#16)
  - `fd5.registry` (#17)
  - `fd5.naming` (#18)
  - `fd5.create` (#19)
  - `fd5.manifest` (#20) — already present
  - `fd5_imaging.recon` (#22)
  - `fd5.cli` (#23)
  - Integration tests (#49)
  - CI lint fix (#48)
- [ ] Follow the changelog format from `.cursor/rules/changelog.mdc`

### References

- RFC success criteria: "README with quickstart; API docstrings on all public functions"
- Changelog rules: `.cursor/rules/changelog.mdc`
- Existing docs: `docs/rfcs/RFC-001-*.md`, `docs/designs/DES-001-*.md`
- White paper: `white-paper.md`
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 06:26 AM_

Completed — README and CHANGELOG updated.

