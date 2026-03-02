---
type: issue
state: closed
created: 2026-02-25T01:08:51Z
updated: 2026-02-25T02:35:54Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/20
comments: 4
labels: feature, effort:medium, area:core
assignees: gerchowl
milestone: Phase 1: Core SDK
projects: none
relationship: none
synced: 2026-02-25T04:19:54.030Z
---

# [Issue 20]: [[FEATURE] Implement TOML manifest generation and parsing](https://github.com/vig-os/fd5/issues/20)

### Description

Implement the `fd5.manifest` module: scan a directory of fd5 files, extract root attrs, and write/read `manifest.toml`.

### Acceptance Criteria

- [ ] `build_manifest(directory) -> dict` scans `.h5` files, reads root attrs, returns manifest dict
- [ ] `write_manifest(directory, output_path)` writes `manifest.toml` with `_schema_version`, `dataset_name`, `study`, `subject` (if present), and `[[data]]` entries
- [ ] `read_manifest(path) -> dict` parses an existing `manifest.toml`
- [ ] Each `[[data]]` entry includes: `product`, `id`, `file`, `timestamp`, and product-specific summary fields
- [ ] Files are iterated lazily (no full in-memory collection for large directories)
- [ ] ≥ 90% test coverage

### Dependencies

- Depends on #12 (`h5io`) for reading root attrs from HDF5 files

### References

- Epic: #11
- Design: [DES-001 § fd5.manifest](docs/designs/DES-001-2026-02-25-fd5-sdk-architecture.md#fd5manifest--toml-manifest)
- Whitepaper: [§ manifest.toml](white-paper.md#manifesttoml)
---

# [Comment #1]() by [gerchowl]()

_Posted on February 25, 2026 at 02:25 AM_

## Design

Issue: #20
Branch: `feature/20-toml-manifest`

### Architecture

Add `src/fd5/manifest.py` with three public functions:

1. **`build_manifest(directory: Path) -> dict`** — Scans `*.h5` files in `directory` using `Path.glob` (lazy iterator). For each file, opens it with `h5py.File` in read mode, calls `h5io.h5_to_dict(root)` to extract root attrs, and builds a `[[data]]` entry dict. Collects dataset-level keys (`_schema_version`, `dataset_name`, `study`, `subject`) from the first file that has them. Returns a manifest dict.

2. **`write_manifest(directory: Path, output_path: Path) -> None`** — Calls `build_manifest(directory)`, then serializes with `tomli_w.dumps()` and writes to `output_path`.

3. **`read_manifest(path: Path) -> dict`** — Reads the file, parses with `tomllib.loads()`, returns the dict.

### Data Entry Mapping

Each `[[data]]` entry includes:
- `product` — from root attr `product`
- `id` — from root attr `id`
- `file` — relative path (filename) of the `.h5` file
- `timestamp` — from root attr `timestamp` (if present)
- All other root attrs are included as product-specific summary fields (excluding internal attrs like `_schema`, `content_hash`, `id_inputs`)

### Design Decisions

1. **Lazy iteration**: `Path.glob("*.h5")` returns a generator — satisfies the lazy requirement without holding all paths in memory.
2. **Use `h5io.h5_to_dict`**: Reuse existing infrastructure instead of raw `h5py` attr reading.
3. **TOML libraries**: `tomli_w` for writing (already in deps), `tomllib` (stdlib 3.11+) for reading.
4. **Dataset-level metadata**: Extract `study` and `subject` from root groups if present in HDF5 files. `_schema_version` defaults to `1` and `dataset_name` is derived from the directory name.
5. **Filtered attrs for data entries**: Exclude internal/large attrs (`_schema`, `_schema_version`, `content_hash`, `id_inputs`, `name`, `description`) from data entries to keep the manifest lightweight. Keep `product`, `id`, `timestamp`, and product-specific summary fields.

### Testing Strategy

- Unit tests with `tmp_path` + `h5py` to create minimal `.h5` files with known attrs
- Test `build_manifest` happy path, empty directory, multiple files
- Test `write_manifest` produces valid TOML, round-trips through `read_manifest`
- Test `read_manifest` with a hand-crafted TOML string
- Test lazy iteration (no full in-memory list)
- Target ≥ 90% coverage

---

# [Comment #2]() by [gerchowl]()

_Posted on February 25, 2026 at 02:25 AM_

## Implementation Plan

Issue: #20
Branch: `feature/20-toml-manifest`

### Tasks

- [ ] Task 1: Write failing tests for `build_manifest`, `write_manifest`, `read_manifest` — `tests/test_manifest.py` — verify: `uv run pytest tests/test_manifest.py` (all fail)
- [ ] Task 2: Implement `fd5.manifest` module with `build_manifest`, `write_manifest`, `read_manifest` — `src/fd5/manifest.py` — verify: `uv run pytest tests/test_manifest.py` (all pass)
- [ ] Task 3: Verify full test suite passes and coverage ≥ 90% — verify: `uv run pytest --cov=fd5.manifest --cov-report=term-missing`
- [ ] Task 4: Update CHANGELOG.md with manifest entry under Unreleased — `CHANGELOG.md` — verify: visual check

---

# [Comment #3]() by [gerchowl]()

_Posted on February 25, 2026 at 02:30 AM_

## Autonomous Run Complete

- Design: posted
- Plan: posted (4 tasks)
- Execute: all tasks done
- Verify: all checks pass (95 tests, 100% coverage on fd5.manifest)
- PR: https://github.com/vig-os/fd5/pull/39
- CI: lint failure about pre-commit not found is a pre-existing CI infrastructure issue (ignored per instructions)

---

# [Comment #4]() by [gerchowl]()

_Posted on February 25, 2026 at 02:35 AM_

Completed — merged into dev.

