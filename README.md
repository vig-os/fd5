# Tessera

A substrate-agnostic, Rust-native **FAIR data-product format** (`fd5` v2) — one immutable,
content-addressed, self-describing product with a single identity / provenance / integrity /
versioning spine.

> ⚠️ **Active development is on the [`dev`](https://github.com/vig-os/tessera/tree/dev) branch.**
> This `main` branch is **release-only** and has not yet received a release: the first alpha
> (`0.1.0-alpha.1`) is staged but **deliberately held** while the on-disk format settles. Until it is
> cut, the code, docs, CLI, and Nix flake all live on `dev` — `main` intentionally stays behind.
>
> To use or read Tessera today, see the **[`dev` README](https://github.com/vig-os/tessera/blob/dev/README.md)**
> and, to consume it from another repo (git / Nix flake refs),
> **[`dev` docs/CONSUMING.md](https://github.com/vig-os/tessera/blob/dev/docs/CONSUMING.md)**.
