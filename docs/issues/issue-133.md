---
type: issue
state: open
created: 2026-02-25T21:40:12Z
updated: 2026-02-25T21:41:03Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/133
comments: 0
labels: feature
assignees: gerchowl
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:48.018Z
---

# [Issue 133]: [[FEATURE] Add fd5 ingest parquet CLI subcommand](https://github.com/vig-os/fd5/issues/133)

## Parent

Epic: #108 (Phase 6: Ingest Layer)
Depends on: #117 (Parquet loader), #113 (CLI commands)

## Summary

The `fd5 ingest` CLI group (#113) exposes `raw`, `csv`, `nifti`, and `dicom` subcommands but is missing `parquet`. The `ParquetLoader` (#117) is already merged — this issue wires it into the CLI.

## Proposed CLI

```bash
fd5 ingest parquet /path/to/data.parquet --output ./output/ \
    --product spectrum --name "Gamma spectrum" \
    --description "HPGe detector measurement"
```

## Scope

1. Add `@ingest.command("parquet")` to `src/fd5/cli.py`
   - Options: `--output`, `--name`, `--description`, `--product`, `--timestamp`, `--column-map` (optional JSON string)
   - Lazy import `ParquetLoader` with clear `ImportError` message if `pyarrow` is missing
2. Add `"parquet"` to `_ALL_LOADER_NAMES` tuple
3. Add `_get_parquet_loader()` helper (same pattern as `_get_nifti_loader`)
4. Add tests in `tests/test_ingest_cli.py`:
   - `TestIngestParquet` class with happy path, missing dep, missing file tests

## Acceptance criteria

- [ ] `fd5 ingest parquet --help` works
- [ ] `fd5 ingest list` shows `parquet` with correct status
- [ ] Happy path test with real `ParquetLoader` or mock
- [ ] Missing `pyarrow` shows clear install instruction
- [ ] All tests pass (`pytest tests/`)

## Size

Small
