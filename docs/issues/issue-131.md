---
type: issue
state: open
created: 2026-02-25T21:39:49Z
updated: 2026-02-25T21:40:39Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/131
comments: 0
labels: none
assignees: gerchowl
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:48.564Z
---

# [Issue 131]: [[TEST] Add idempotency tests for all ingest loaders](https://github.com/vig-os/fd5/issues/131)

## Parent

Epic: #108 (Phase 6: Ingest Layer)

## Summary

Add idempotency tests to every ingest loader. Calling the same ingest function twice with the same input should produce two valid, independently sealed fd5 files with unique IDs and content hashes.

## Scope

Add a `TestIdempotency` class to each test file:

- `tests/test_ingest_raw.py` — `ingest_array()` and `ingest_binary()`
- `tests/test_ingest_csv.py` — `CsvLoader.ingest()`
- `tests/test_ingest_nifti.py` — `ingest_nifti()`
- `tests/test_ingest_dicom.py` — `ingest_dicom()`
- `tests/test_ingest_parquet.py` — `ParquetLoader.ingest()`

Each test should:
1. Call the ingest function twice with identical inputs
2. Assert both outputs exist and are valid `.h5` files
3. Assert the two files have **different** `id` attrs (UUID uniqueness)
4. Assert the two files have **identical** `content_hash` attrs (deterministic sealing)

## Acceptance criteria

- [ ] Each loader has at least one idempotency test
- [ ] All tests pass (`pytest tests/`)
- [ ] No regressions in existing tests

## Size

Small — test-only, no implementation changes.
