# Installing Tessera

Tessera has exactly one native dependency: **libhdf5**, and it is used only to *read* vendor
acquisitions (GE listmode, DICOM-adjacent HDF5) at ingest time. Everything Tessera *writes* is
re-encoded to Zarr + [`pcodec`](https://github.com/mwlon/pcodec) (arrays) or
[Vortex](https://github.com/spiraldb/vortex) (tables). That single fact drives both the install choices
below and why the bundled-HDF5 options are safe.

## Which path?

| Path | Needs on the box | Best for |
| --- | --- | --- |
| Prebuilt binary | nothing | end users |
| `cargo install --features static-hdf5` | CMake + C compiler | source installs, any distro |
| `cargo build` (default) | system libhdf5 + pkg-config | day-to-day development |
| Nix dev shell | nix | contributors |

### 1. Prebuilt binary (recommended)

Self-contained `tessera` for Linux and macOS (x86-64 + arm64), with libhdf5 statically linked in — no
system libraries required. These are produced by [cargo-dist](https://opensource.axo.dev/cargo-dist/)
and attached to each [GitHub Release](https://github.com/vig-os/tessera/releases):

```bash
curl --proto '=https' --tlsv1.2 -LsSf \
  https://github.com/vig-os/tessera/releases/latest/download/tessera-cli-installer.sh | sh
```

Or `cargo binstall tessera-cli` (reads the same release artifacts), or download a `.tar.xz` directly.

> The first release (`0.1.0-alpha.1`) is staged but deliberately **held** while the format settles;
> see `release-plz.toml`. Until it is cut, build from source with one of the paths below.

### 2. From source, self-contained (`static-hdf5`)

Builds a private libhdf5 from vendored source ([`hdf5-metno-src`](https://crates.io/crates/hdf5-metno-src),
HDF5 2.2.0) and links it statically — so the resulting binary needs **no** system HDF5. The build host
needs **CMake, a C compiler, and `make`** (and a few extra minutes to compile HDF5 once):

```bash
cargo install --git https://github.com/vig-os/tessera --features static-hdf5 tessera-cli
```

This path works on every distribution, including `lib64`-layout ones (Fedora / RHEL / SUSE / nix) where
CMake installs the archive to `lib64` rather than `lib`. (Tessera's `tessera-ingest` build script adds
the `lib64` search path explicitly, working around an upstream `hdf5-metno-sys` assumption that the
archive is always under `lib`.)

### 3. From source, system HDF5 (default, fastest dev build)

The default build (no `static-hdf5` feature) links a libhdf5 that is already installed, discovered via
`pkg-config`. This is what you want while developing — it skips the multi-minute HDF5 compile:

```bash
# Debian/Ubuntu: apt-get install libhdf5-dev pkg-config
# Fedora:        dnf install hdf5-devel pkgconf-pkg-config
# macOS:         brew install hdf5 pkg-config
cd tessera && cargo build --release -p tessera-cli
```

### 4. Nix dev shell (contributors)

The repository is Nix-managed; the dev shell pins the exact toolchain and every native dependency
(hdf5, zstd, …):

```bash
direnv allow          # or: nix develop
cd tessera && cargo test
```

## Why bundling HDF5 can't affect your data

HDF5 is a read-only *input* format for Tessera. On write, every array and table is re-encoded into the
sealed `.tsra` container (Zarr+pcodec / Vortex), and the block digests + `manifest_hash` seal are
computed over *those* bytes. The libhdf5 you happened to link — system, or the vendored 2.2.0, of any
version — is never in a sealed product's byte-path, so it can never change a `content_hash`. Two
machines with different libhdf5 builds ingest the same acquisition to the same bytes.
