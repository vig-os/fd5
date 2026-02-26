---
type: issue
state: open
created: 2026-02-25T21:39:58Z
updated: 2026-02-25T21:40:51Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/132
comments: 0
labels: none
assignees: gerchowl
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:48.314Z
---

# [Issue 132]: [[TEST] Add fd5.schema.validate() smoke tests for all ingest loaders](https://github.com/vig-os/fd5/issues/132)

## Parent

Epic: #108 (Phase 6: Ingest Layer)

## Summary

Add smoke tests that run `fd5.schema.validate()` on the output of every ingest loader. Currently only `test_ingest_dicom.py` validates the sealed output. All other loaders (raw, CSV, NIfTI, Parquet) produce sealed fd5 files but never verify schema compliance.

## Scope

Add a `TestFd5Validate` class to each test file:

- `tests/test_ingest_raw.py` — validate `ingest_array()` and `ingest_binary()` output
- `tests/test_ingest_csv.py` — validate `CsvLoader.ingest()` output (spectrum product)
- `tests/test_ingest_nifti.py` — validate `ingest_nifti()` output
- `tests/test_ingest_parquet.py` — validate `ParquetLoader.ingest()` output (spectrum product)

Each test should:
1. Ingest a synthetic input file
2. Call `fd5.schema.validate(result_path)`
3. Assert errors list is empty

## Acceptance criteria

- [ ] Each loader has at least one `fd5.schema.validate()` smoke test
- [ ] All tests pass (`pytest tests/`)
- [ ] No regressions in existing tests

## Size

Small — test-only, no implementation changes.
