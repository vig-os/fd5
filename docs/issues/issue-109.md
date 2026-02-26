---
type: issue
state: open
created: 2026-02-25T20:24:32Z
updated: 2026-02-25T20:28:02Z
author: gerchowl
author_url: https://github.com/gerchowl
url: https://github.com/vig-os/fd5/issues/109
comments: 0
labels: feature, effort:medium, area:core
assignees: gerchowl
milestone: none
projects: none
relationship: none
synced: 2026-02-26T04:15:51.597Z
---

# [Issue 109]: [[FEATURE] fd5.ingest._base — Loader protocol and shared helpers](https://github.com/vig-os/fd5/issues/109)

## Parent

Epic: #108 (Phase 6: Ingest Layer)

## Summary

Create `src/fd5/ingest/_base.py` with:

1. **`Loader` protocol** — defines the interface all format-specific loaders must implement
2. **Shared helper functions** — provenance recording, source file hashing, common validation

## Proposed API

```python
from typing import Protocol, runtime_checkable
from pathlib import Path
from fd5._types import Fd5Path

@runtime_checkable
class Loader(Protocol):
    """Protocol that all fd5 ingest loaders must satisfy."""

    @property
    def supported_product_types(self) -> list[str]:
        """Product types this loader can produce (e.g. ['recon', 'listmode'])."""
        ...

    def ingest(
        self,
        source: Path | str,
        output_dir: Path,
        *,
        product: str,
        name: str,
        description: str,
        timestamp: str | None = None,
        **kwargs,
    ) -> Fd5Path:
        """Read source data and produce a sealed fd5 file."""
        ...
```

### Shared helpers

```python
def hash_source_files(paths: Iterable[Path]) -> list[dict]:
    """Hash source files for provenance/original_files records."""
    ...

def discover_loaders() -> dict[str, Loader]:
    """Discover available loaders based on installed optional deps."""
    ...
```

## Acceptance criteria

- [ ] `Loader` protocol defined with `runtime_checkable`
- [ ] `hash_source_files()` computes SHA-256 + size for source file provenance
- [ ] `discover_loaders()` returns only loaders whose deps are installed
- [ ] `src/fd5/ingest/__init__.py` re-exports public API
- [ ] Tests in `tests/test_ingest_base.py`
- [ ] ≥ 90% coverage

## Dependencies

None — this is the foundation for all other ingest issues.
