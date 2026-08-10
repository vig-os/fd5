//! Build script — only does one thing, and only under the `static-hdf5` feature.
//!
//! When we link a *vendored* libhdf5 (feature `static-hdf5` → `hdf5-metno-sys/static`, which builds
//! HDF5 from source via `hdf5-metno-src`), `hdf5-metno-sys`'s build script emits its link-search path
//! as a hard-coded `{install_prefix}/lib`. But CMake's `GNUInstallDirs` installs the static archive
//! into `lib64` instead of `lib` on "lib64" distros (Fedora / RHEL / SUSE / nix, anything where
//! `CMAKE_INSTALL_LIBDIR` resolves to `lib64`), so the archive is at `{prefix}/lib64/libhdf5.a` and
//! the linker — told to search only `{prefix}/lib` — fails with
//! `could not find native static library 'hdf5'`. Debian / Ubuntu / macOS use `lib`, so the prebuilt
//! release binaries (built on those runners) are unaffected; this only bites a source
//! `cargo install --features static-hdf5` on a lib64 platform.
//!
//! `hdf5-metno-sys` declares `links = "hdf5"` and re-emits the install prefix as `metadata=root`, so we
//! (a direct dependent) receive it as `DEP_HDF5_ROOT`. We add `{root}/lib64` as an *extra* link-search
//! path. It is purely additive — the linker searches every `-L` path, so adding the lib64 sibling next
//! to hdf5-metno-sys's `lib` makes the archive findable under either layout, on every platform.
//!
//! Determinism note: this touches only where the *input* libhdf5 is found at link time — HDF5 is
//! read-only input (Tessera encodes to Vortex/pcodec), never in the sealed byte-path, so nothing here
//! can move a content_hash.

fn main() {
    println!("cargo::rerun-if-changed=build.rs");
    println!("cargo::rerun-if-env-changed=DEP_HDF5_ROOT");

    // Only relevant for the vendored-static build; a no-op for the default pkg-config path (where
    // hdf5-metno-sys does not emit `root`, so DEP_HDF5_ROOT is unset).
    if std::env::var_os("CARGO_FEATURE_STATIC_HDF5").is_none() {
        return;
    }
    if let Ok(root) = std::env::var("DEP_HDF5_ROOT") {
        // Additive fallback next to hdf5-metno-sys's own `{root}/lib`; covers the lib64 install layout.
        println!("cargo::rustc-link-search=native={root}/lib64");
    }
}
