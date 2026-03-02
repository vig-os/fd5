---
type: issue
state: open
created: 2026-02-25T23:58:54Z
updated: 2026-02-25T23:59:12Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/150
comments: 0
labels: chore
assignees: gerchowl
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:43.235Z
---

# [Issue 150]: [[CHORE] Wire up worktree recipes in justfile and fix solve-and-pr prompt typo](https://github.com/vig-os/fd5/issues/150)

### Chore Type

Configuration change

### Description

The main `justfile` is missing the `import '.devcontainer/justfile.worktree'` line, so worktree recipes (`worktree-start`, `worktree-attach`, `worktree-list`, `worktree-stop`) are not available from the project root. Additionally, the `solve-and-pr` skill references the wrong prompt path (`/worktree-solve-and-pr` instead of `/worktree_solve-and-pr`).

### Acceptance Criteria

- [ ] `justfile` imports `.devcontainer/justfile.worktree`
- [ ] `just --list` shows worktree recipes
- [ ] `.cursor/skills/solve-and-pr/SKILL.md` references `/worktree_solve-and-pr` (underscore)

### Implementation Notes

Two files:
- `justfile`: add `import '.devcontainer/justfile.worktree'` after the existing imports
- `.cursor/skills/solve-and-pr/SKILL.md`: fix `/worktree-solve-and-pr` → `/worktree_solve-and-pr`

### Related Issues

_None_

### Priority

Low

### Changelog Category

No changelog needed
