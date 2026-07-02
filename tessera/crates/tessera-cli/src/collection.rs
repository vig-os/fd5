//! `tessera collection inspect | ls | verify` — consumer verbs over a `collection.json` descriptor
//! (ADR-0033 / #272). A collection is the content-addressed catalog the declarative ingest engine
//! writes at `<out_dir>/collection.json`, pinning each member `.tsra` by its `manifest_hash`. These
//! verbs let a downstream consumer read + integrity-check the catalog and its members without
//! re-running the ingest — the collection-level analogue of `tessera inspect` / `verify`.
//!
//! Members are referenced by their content-addressed `id`; on disk a **product** member is
//! `<dir>/<reference>.tsra` and a **sub-collection** member is `<dir>/<reference>.collection.json`
//! (resolved by `kind`, ADR-0049 §4). `ls` opens each member to show its human `name` (the child
//! collection's name for a sub-collection); `verify` **recurses** into sub-collection members,
//! checking each descendant's seal + pinned version transitively (ADR-0049 §3).

use std::collections::HashSet;
use std::io::Write;
use std::path::{Path, PathBuf};

use tessera_core::collection::{Collection, MemberKind, Role};
use tessera_core::{Error, Result};
use tessera_io::Reader;

/// The collection seal badge (mirrors `nav::seal_status` for products, #268): `sealed✓` when
/// `manifest_hash` is present AND re-verifies over the canonical bytes, `sealed✗` on a mismatch,
/// `unsealed` when the collection carries no seal.
fn seal_status(c: &Collection) -> &'static str {
    match &c.manifest_hash {
        None => "unsealed",
        Some(mh) => match c.compute_manifest_hash() {
            Ok(got) if &got == mh => "sealed✓",
            _ => "sealed✗",
        },
    }
}

fn role_str(r: &Role) -> &'static str {
    match r {
        Role::Raw => "raw",
        Role::Derived => "derived",
    }
}

/// Load a `collection.json` **without** verifying (so `inspect` can honestly render a tampered one).
fn load(file: &Path) -> Result<Collection> {
    Collection::from_json(&std::fs::read_to_string(file)?)
}

/// The on-disk path of a member next to the `collection.json` — resolved by `kind` (ADR-0049 §4): a
/// product is `<reference>.tsra`, a sub-collection is `<reference>.collection.json`.
fn member_path(collection_file: &Path, reference: &str, kind: MemberKind) -> PathBuf {
    let dir = collection_file.parent().unwrap_or_else(|| Path::new("."));
    if kind == MemberKind::Collection {
        dir.join(format!("{reference}.collection.json"))
    } else {
        dir.join(format!("{reference}.tsra"))
    }
}

fn w(out: &mut dyn Write, args: std::fmt::Arguments<'_>) -> Result<()> {
    out.write_fmt(args).map_err(Error::from)
}

/// `tessera collection inspect FILE` — the catalog header: identity, seal badge, and each member's
/// role + reference + pinned `manifest_hash` (short). Payload-cheap — reads only the descriptor.
pub fn inspect(file: &Path, out: &mut dyn Write) -> Result<()> {
    let c = load(file)?;
    w(out, format_args!("collection {}\n", c.name))?;
    w(out, format_args!("id            {}\n", c.id))?;
    w(out, format_args!("timestamp     {}\n", c.timestamp))?;
    if let Some(s) = &c.study {
        w(out, format_args!("study         {s}\n"))?;
    }
    w(
        out,
        format_args!(
            "content_hash  {}\n",
            c.content_hash.as_deref().unwrap_or("-")
        ),
    )?;
    w(
        out,
        format_args!(
            "manifest_hash {}\n",
            c.manifest_hash.as_deref().unwrap_or("-")
        ),
    )?;
    w(out, format_args!("seal          {}\n", seal_status(&c)))?;
    w(out, format_args!("members       {}\n", c.members.len()))?;
    for m in &c.members {
        let kind = if m.kind == MemberKind::Collection {
            "collection"
        } else {
            "product"
        };
        w(
            out,
            format_args!(
                "  - {:<7} {:<10} {}  [{}]\n",
                role_str(&m.role),
                kind,
                m.reference,
                crate::nav::short_hash(&m.manifest_hash)
            ),
        )?;
    }
    Ok(())
}

/// `tessera collection ls FILE` — one line per member with its **human** name + product, resolved by
/// opening each member `.tsra` (falls back to `?` if a member file is absent). `--full` also prints
/// the full pinned `manifest_hash` and any in-collection `derived_from` edges.
pub fn ls(file: &Path, full: bool, out: &mut dyn Write) -> Result<()> {
    let c = load(file)?;
    for m in &c.members {
        let path = member_path(file, &m.reference, m.kind);
        // A product member's name/product comes from its `.tsra`; a sub-collection member's from its
        // child `collection.json` (product shown as `collection`).
        let (product, name) = if m.kind == MemberKind::Collection {
            match std::fs::read_to_string(&path)
                .ok()
                .and_then(|s| Collection::from_json(&s).ok())
            {
                Some(child) => ("collection".to_string(), child.name),
                None => (
                    "collection".to_string(),
                    "<sub-collection not found>".to_string(),
                ),
            }
        } else {
            match Reader::open(&path) {
                Ok(r) => {
                    let mm = r.manifest();
                    (mm.product.clone(), mm.name.clone())
                }
                Err(_) => ("?".to_string(), "<member file not found>".to_string()),
            }
        };
        let hash = if full {
            m.manifest_hash.clone()
        } else {
            crate::nav::short_hash(&m.manifest_hash)
        };
        w(
            out,
            format_args!(
                "{:<7} {:<10} {:<20} {name:<24} [{hash}]\n",
                role_str(&m.role),
                product,
                m.reference,
            ),
        )?;
        if full && !m.derived_from.is_empty() {
            w(
                out,
                format_args!("          derived_from: {}\n", m.derived_from.join(", ")),
            )?;
        }
    }
    Ok(())
}

/// `tessera collection verify FILE` — the catalog's end-to-end integrity check, **recursive**
/// (ADR-0049 §3): verify the collection seal (id / content_hash / manifest_hash), then for every
/// member confirm it is present + intact + exactly the version pinned — opening a **product** member's
/// `.tsra` (its own seal) or descending into a **sub-collection** member's `collection.json` and
/// verifying it transitively. A missing, mismatched, or unreachable member is a typed [`Error`]; a
/// cycle (defense-in-depth — content-addressing is acyclic by construction) is refused. Offline: a
/// child that can't be read fails loudly rather than passing silently.
pub fn verify(file: &Path, out: &mut dyn Write) -> Result<()> {
    let mut seen = HashSet::new();
    let n = verify_collection(file, None, &mut seen)?;
    w(
        out,
        format_args!("OK  {} verified ({n} members, recursive)\n", file.display()),
    )
}

/// Recursively verify the collection at `file`. `expected_mh` (when descending from a parent) pins the
/// exact version the parent recorded. Returns the count of members verified in this subtree.
fn verify_collection(
    file: &Path,
    expected_mh: Option<&str>,
    seen: &mut HashSet<String>,
) -> Result<usize> {
    let bytes = std::fs::read_to_string(file).map_err(|e| {
        Error::Invalid(format!(
            "sub-collection unreachable at {} — cannot fully verify offline: {e}",
            file.display()
        ))
    })?;
    // Seal check (id + content_hash over pinned member hashes + manifest_hash).
    let c = Collection::from_json_verified(&bytes)?;
    // Confirm this collection is the exact version its parent pinned (swapped-but-valid = failure).
    if let Some(exp) = expected_mh {
        let got = c.manifest_hash.as_deref().unwrap_or_default();
        if got != exp {
            return Err(Error::Integrity {
                what: "collection_member",
                expected: exp.to_string(),
                actual: got.to_string(),
            });
        }
    }
    // Cycle guard (defense-in-depth; a member can't pin an ancestor hash that doesn't exist yet).
    if let Some(mh) = &c.manifest_hash {
        if !seen.insert(mh.clone()) {
            return Err(Error::Invalid(format!(
                "collection cycle detected at {} (manifest_hash already visited)",
                file.display()
            )));
        }
    }

    let mut count = 0usize;
    for m in &c.members {
        let path = member_path(file, &m.reference, m.kind);
        match m.kind {
            MemberKind::Collection => {
                // Descend: the child's own seal + pinned version + its whole subtree.
                count += verify_collection(&path, Some(&m.manifest_hash), seen)?;
            }
            _ => {
                // Product member: `Reader::open` verifies its seal; confirm the pinned version.
                let r = Reader::open(&path).map_err(|e| {
                    Error::Invalid(format!(
                        "collection member '{}' missing or unreadable at {}: {e}",
                        m.reference,
                        path.display()
                    ))
                })?;
                let got = r.manifest().manifest_hash.as_deref().unwrap_or_default();
                if got != m.manifest_hash {
                    return Err(Error::Integrity {
                        what: "collection_member",
                        expected: m.manifest_hash.clone(),
                        actual: got.to_string(),
                    });
                }
            }
        }
        count += 1;
    }
    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tessera_core::block::array::ArraySpec;
    use tessera_core::collection::CollectionBuilder;
    use tessera_core::ProductBuilder;
    use tessera_io::{array::ArrayData, pack};

    /// Build a 2-member collection on disk (`collection.json` + two `<id>.tsra`) and return its dir.
    fn build_collection(dir: &Path) -> (Collection, Vec<String>) {
        let mut ids = Vec::new();
        let mut cb = CollectionBuilder::new("study", "a CT+PET study", "2024-01-01T00:00:00Z");
        for name in ["ct", "pt"] {
            let spec = ArraySpec::new(vec![2, 2], "int16");
            let (bref, payload) =
                tessera_io::array::array_block("volume", &spec, &ArrayData::I16(vec![0, 1, 2, 3]))
                    .unwrap();
            let mut b = ProductBuilder::new("recon", name, "d", "2024-01-01T00:00:00Z");
            b.add_block_ref(bref);
            let sealed = b.seal().unwrap();
            pack(
                &sealed,
                &[payload],
                &dir.join(format!("{}.tsra", sealed.id)),
            )
            .unwrap();
            cb.add_member(
                &sealed.id,
                sealed.manifest_hash.clone().unwrap(),
                Role::Raw,
                Vec::new(),
            );
            ids.push(sealed.id.clone());
        }
        let c = cb.seal().unwrap();
        std::fs::write(dir.join("collection.json"), c.to_json().unwrap()).unwrap();
        (c, ids)
    }

    #[test]
    fn inspect_ls_verify_a_collection_on_disk() {
        let dir = tempfile::tempdir().unwrap();
        let (c, _ids) = build_collection(dir.path());
        let cf = dir.path().join("collection.json");

        let mut buf = Vec::new();
        inspect(&cf, &mut buf).unwrap();
        let s = String::from_utf8(buf).unwrap();
        assert!(s.contains("collection study"));
        assert!(s.contains("seal          sealed✓"), "{s}");
        assert!(s.contains("members       2"));

        let mut buf = Vec::new();
        ls(&cf, false, &mut buf).unwrap();
        let s = String::from_utf8(buf).unwrap();
        // The human name + product of each member (resolved by opening the .tsra) show up.
        assert!(
            s.contains("recon") && s.contains("ct") && s.contains("pt"),
            "{s}"
        );

        // Full verify: collection seal + every member present, intact, and the pinned version.
        let mut buf = Vec::new();
        verify(&cf, &mut buf).unwrap();
        assert!(String::from_utf8(buf)
            .unwrap()
            .contains("verified (2 members, recursive)"));

        // Remove a member file → verify fails loudly (missing member).
        std::fs::remove_file(dir.path().join(format!("{}.tsra", c.members[0].reference))).unwrap();
        assert!(verify(&cf, &mut Vec::new()).is_err());
    }

    /// Build a child collection on disk written as `<id>.collection.json` (+ its member `.tsra`s).
    fn build_child_collection(dir: &Path, name: &str) -> Collection {
        let mut cb = CollectionBuilder::new(name, "a child dataset", "2024-01-01T00:00:00Z");
        for pname in ["ct", "pt"] {
            let spec = ArraySpec::new(vec![2, 2], "int16");
            let (bref, payload) =
                tessera_io::array::array_block("volume", &spec, &ArrayData::I16(vec![0, 1, 2, 3]))
                    .unwrap();
            let mut b = ProductBuilder::new("recon", pname, "d", "2024-01-01T00:00:00Z");
            b.add_block_ref(bref);
            let sealed = b.seal().unwrap();
            pack(
                &sealed,
                &[payload],
                &dir.join(format!("{}.tsra", sealed.id)),
            )
            .unwrap();
            cb.add_member(
                &sealed.id,
                sealed.manifest_hash.clone().unwrap(),
                Role::Raw,
                Vec::new(),
            );
        }
        let c = cb.seal().unwrap();
        std::fs::write(
            dir.join(format!("{}.collection.json", c.id)),
            c.to_json().unwrap(),
        )
        .unwrap();
        c
    }

    /// Part 2 (ADR-0049 §3): `verify` recurses into a sub-collection member (a `project` over a
    /// `dataset`), `inspect` shows its kind, `ls` resolves its name, and a tampered *grand*child is
    /// caught transitively.
    #[test]
    fn verify_recurses_into_a_sub_collection() {
        use tessera_core::collection::CollectionHandle;
        let dir = tempfile::tempdir().unwrap();
        let child = build_child_collection(dir.path(), "dataset-A");

        // Parent "project" with the child dataset as a sub-collection member.
        let mut cb = CollectionBuilder::new("project-X", "a project", "2024-01-01T00:00:00Z");
        cb.add_subcollection(
            &CollectionHandle::of(&child).unwrap(),
            Role::Derived,
            Vec::new(),
        );
        let parent = cb.seal().unwrap();
        let pf = dir.path().join("collection.json");
        std::fs::write(&pf, parent.to_json().unwrap()).unwrap();

        // inspect: the member line shows `collection` kind for the sub-collection.
        let mut buf = Vec::new();
        inspect(&pf, &mut buf).unwrap();
        let s = String::from_utf8(buf).unwrap();
        assert!(
            s.lines()
                .any(|l| l.contains(&child.id) && l.contains("collection")),
            "{s}"
        );

        // ls: the sub-collection member resolves to the child's human name.
        let mut buf = Vec::new();
        ls(&pf, false, &mut buf).unwrap();
        assert!(String::from_utf8(buf).unwrap().contains("dataset-A"));

        // verify: recurses → the sub-collection (1) + its two products = 3 members.
        let mut buf = Vec::new();
        verify(&pf, &mut buf).unwrap();
        let s = String::from_utf8(buf).unwrap();
        assert!(s.contains("recursive") && s.contains("3 members"), "{s}");

        // Tamper a grandchild product `.tsra` → the recursive verify catches it transitively.
        std::fs::remove_file(
            dir.path()
                .join(format!("{}.tsra", child.members[0].reference)),
        )
        .unwrap();
        assert!(verify(&pf, &mut Vec::new()).is_err());
    }
}
