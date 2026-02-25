---
type: issue
state: closed
created: 2026-02-25T01:07:18Z
updated: 2026-02-25T02:22:27Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/12
comments: 4
labels: feature, effort:medium, area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:56.595Z
---

# [Issue 12]: [[FEATURE] Implement h5_to_dict / dict_to_h5 metadata helpers](https://github.com/vig-os/fd5/issues/12)

### Description

Implement the `fd5.h5io` module: lossless round-trip conversion between Python dicts and HDF5 groups/attrs.

This is the foundation of all metadata I/O in fd5. The type mapping follows [white-paper.md § Implementation Notes](white-paper.md#h5_to_dict--dict_to_h5-type-mapping).

### Acceptance Criteria

- [ ] `dict_to_h5(group, d)` writes nested dicts as HDF5 groups with attrs
- [ ] `h5_to_dict(group) -> dict` reads groups/attrs back to dicts
- [ ] Round-trip property: `h5_to_dict(dict_to_h5(d)) == d` for all supported types
- [ ] Type mapping covers: str, int, float, bool, list[number], list[str], list[bool], None, dict (recursive)
- [ ] `None` values are skipped (absent attr); absent attrs read back as missing keys
- [ ] Datasets are never read by `h5_to_dict` (attrs only)
- [ ] Keys are written in sorted order (determinism for hashing)
- [ ] ≥ 90% test coverage

### Dependencies

- No blockers; this is a leaf module

### References

- Epic: #11
- Design: [DES-001 § fd5.h5io](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5h5io--hdf5-metadata-io)
- Whitepaper: [§ Implementation Notes](white-paper.md#h5_to_dict--dict_to_h5-type-mapping)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 01:23 AM_

## Design

### Architecture

The `fd5.h5io` module exposes two public functions:

- `dict_to_h5(group: h5py.Group, d: dict) -> None` — writes a Python dict as HDF5 attrs/sub-groups
- `h5_to_dict(group: h5py.Group) -> dict` — reads HDF5 attrs/sub-groups back to a Python dict

Both live in `src/fd5/h5io.py` with no additional internal modules.

### Type Mapping

Follows [white-paper.md § Implementation Notes](white-paper.md#h5_to_dict--dict_to_h5-type-mapping) exactly:

**Writing (`dict_to_h5`):**
| Python type | HDF5 storage |
|---|---|
| `dict` | Sub-group (recursive) |
| `str` | Attr (UTF-8 string) |
| `int` | Attr (int64) |
| `float` | Attr (float64) |
| `bool` | Attr (numpy.bool_) |
| `list[int\|float]` | Attr (numpy array) |
| `list[str]` | Attr (vlen string array via `h5py.special_dtype(vlen=str)`) |
| `list[bool]` | Attr (numpy bool array) |
| `None` | Skipped (absent attr) |

**Reading (`h5_to_dict`):**
- Sub-groups → `dict` (recursive)
- Scalar attrs → native Python types (`str`, `int`, `float`, `bool`)
- Array attrs (numeric) → `list` via `.tolist()`
- Array attrs (string) → `list[str]`
- Datasets → **skipped entirely** (never read)
- Absent attrs → missing keys (caller handles)

### Key Decisions

1. **Sorted keys**: `dict_to_h5` iterates `sorted(d.keys())` for deterministic HDF5 layout (critical for hashing).
2. **None → skip**: `None` values are not written. On read, missing keys simply don't appear in the dict.
3. **Attrs only**: `h5_to_dict` ignores all datasets in the group.
4. **Bool before int**: Type dispatch checks `bool` before `int` (since `bool` is a subclass of `int` in Python).
5. **bytes type**: Out of scope for this issue (the white-paper mentions it as "rare"). Can be added in a follow-up.
6. **numpy.ndarray → dataset**: Out of scope — this issue covers attrs-only metadata helpers.

### Dependencies

- `h5py` and `numpy` must be added to `pyproject.toml` `[project.dependencies]`.

### Testing Strategy

- Use `tmp_path` (pytest) + `h5py.File` in-memory or on-disk for each test.
- Test each type individually, then test round-trip with a complex nested dict.
- Edge cases: empty dict, empty lists, deeply nested dicts, unicode strings.
- Verify datasets are skipped by `h5_to_dict`.
- Target ≥ 90% coverage.

### Error Handling

- Invalid types in dict values raise `TypeError` with a clear message.
- No silent coercion.

---

# [Comment #2]() by [gerchowl]()

_Posted on February 25, 2026 at 01:23 AM_

## Implementation Plan

Issue: #12
Branch: feature/12-h5io-dict-helpers

### Tasks

- [ ] Task 1: Add h5py and numpy to pyproject.toml dependencies — `pyproject.toml` — verify: `uv sync && python -c "import h5py; import numpy"`
- [ ] Task 2: Create design doc stub at docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md with fd5.h5io section — `docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md` — verify: file exists
- [ ] Task 3: Write failing tests for dict_to_h5 (str, int, float, bool, None, nested dict, sorted keys) — `tests/test_h5io.py` — verify: `uv run pytest tests/test_h5io.py` fails
- [ ] Task 4: Implement dict_to_h5 to pass the tests — `src/fd5/h5io.py` — verify: `uv run pytest tests/test_h5io.py` passes
- [ ] Task 5: Write failing tests for dict_to_h5 list types (list[int], list[float], list[str], list[bool], empty list) — `tests/test_h5io.py` — verify: `uv run pytest tests/test_h5io.py` has new failures
- [ ] Task 6: Implement list handling in dict_to_h5 to pass — `src/fd5/h5io.py` — verify: `uv run pytest tests/test_h5io.py` passes
- [ ] Task 7: Write failing tests for h5_to_dict (all types, datasets skipped, empty group) — `tests/test_h5io.py` — verify: `uv run pytest tests/test_h5io.py` has new failures
- [ ] Task 8: Implement h5_to_dict to pass — `src/fd5/h5io.py` — verify: `uv run pytest tests/test_h5io.py` passes
- [ ] Task 9: Write failing round-trip test with complex nested dict — `tests/test_h5io.py` — verify: `uv run pytest tests/test_h5io.py` has new failures
- [ ] Task 10: Verify round-trip passes with existing implementation — `src/fd5/h5io.py` — verify: `uv run pytest tests/test_h5io.py` all pass
- [ ] Task 11: Write failing test for TypeError on unsupported type — `tests/test_h5io.py` — verify: `uv run pytest tests/test_h5io.py` has new failure
- [ ] Task 12: Implement TypeError handling — `src/fd5/h5io.py` — verify: `uv run pytest tests/test_h5io.py` all pass
- [ ] Task 13: Verify ≥ 90% coverage — verify: `uv run pytest --cov=fd5.h5io --cov-report=term-missing tests/test_h5io.py`
- [ ] Task 14: Update CHANGELOG.md — `CHANGELOG.md` — verify: entry exists under Unreleased

---

# [Comment #3]() by [gerchowl]()

_Posted on February 25, 2026 at 01:43 AM_

## Push Blocked: SSH Signing Key Not Registered

The implementation is complete (11 commits, 34 tests passing, 98% coverage, all linters green), but push is blocked by the Enterprise-level signed commits rule.

**Root cause:** The SSH key available in this worktree environment (`SHA256:VpDK7fwbjI+QR63qf/vQCc/TcMPx+szvltrh/nyzAa4`) is not registered as a signing key on the GitHub account. The registered signing key (`SHA256:+0tmtrsmsTO60JVBykA1+1C2SKRDd5wjYx58+ZkFDz0`) is from the host machine and its private key isn't forwarded to this environment.

**To resolve**, run one of:

1. **Register the worktree key on GitHub** (preferred):
   ```bash
   gh auth refresh -h github.com -s admin:ssh_signing_key
   gh ssh-key add /root/.ssh/id_ed25519_github.pub --title "worktree-signing" --type signing
   ```
   Then re-run the push.

2. **Forward the host SSH agent** with the correct signing key and re-sign commits.

Once the signing key is registered, push with:
```bash
cd /workspace/fd5-worktrees/10-worktrees/12
git push -u origin HEAD --force
```

---

# [Comment #4]() by [gerchowl]()

_Posted on February 25, 2026 at 02:22 AM_

Completed — merged into dev.

