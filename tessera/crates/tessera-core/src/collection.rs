//! Collections — a content-addressed catalog of member products (ADR-0033, #223).
//!
//! Per the design: physical products stay **flat** (one `.tsra` = one raw OR one derived stage);
//! **logical** collections nest *by reference* — a `Collection` lists its members by their product
//! `id` + `manifest_hash`. The collection itself is content-addressed in the same idiom as a
//! [`crate::manifest::Manifest`]:
//!
//! - [`id`](Collection::id) — `blake3` over canonical-JSON of [`id_inputs`] (default keys
//!   `product="collection"`, `name`, `timestamp`). Identity is logical — independent of the
//!   members or their descriptive metadata.
//! - [`content_hash`](Collection::content_hash) — the **MMR root** over the members'
//!   `manifest_hash`es in declared order, reusing [`crate::hash::merkle_root`]. Same construction
//!   the manifest uses for block digests, so the collection is itself verifiable + has cheap
//!   inclusion/consistency proofs once the streaming-write engine wants them. Member order is
//!   significant.
//! - [`manifest_hash`](Collection::manifest_hash) — `blake3` over canonical-JSON of the whole
//!   collection with `manifest_hash` itself omitted. The seal — transitively commits to every
//!   member's `manifest_hash` (which itself commits to that member's payload), so tampering with
//!   any member or with the catalog changes the collection seal.
//!
//! [`Role`] tags a member as `Raw` (acquisition data, irreplaceable) or `Derived` (regenerable
//! output). Storage layers map this to WORM retention mode — `Role::Raw` → Compliance (immutable),
//! `Role::Derived` → Governance (regenerable). The mapping helper lives next to the WORM module in
//! `tessera-io` so the core stays I/O-free; see `tessera_io::collection::retention_mode`.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::manifest::{SUPPORTED_MAJOR, TESSERA_VERSION};

/// Raw acquisition data vs derived/regenerable product. Drives storage's WORM retention mapping
/// (raw → Compliance, derived → Governance) — see `tessera_io::collection::retention_mode`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    Raw,
    Derived,
}

/// Whether a [`CollectionMember`] resolves to a flat product (`<ref>.tsra`) or a nested
/// sub-collection (`<ref>.collection.json`) — the recursion discriminator (ADR-0049 §1). A member is
/// pinned by `manifest_hash` exactly like a product either way; `kind` only says how to *resolve* and
/// *verify* it. `#[non_exhaustive]` so a future kind (external / virtual reference) stays additive and
/// downstream matchers cannot lock the variant set; an unknown `kind` is *refused* by serde (never
/// swallowed), gated first by [`Collection::check_version`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[non_exhaustive]
pub enum MemberKind {
    /// A flat physical product — one `.tsra` (the default; skipped on serialize so pre-recursion
    /// collections stay byte-identical).
    #[default]
    Product,
    /// A nested sub-collection — a child `collection.json`, verified recursively.
    Collection,
}

impl MemberKind {
    /// The default-kind predicate for `#[serde(skip_serializing_if)]` — keeps existing all-product
    /// collections byte-identical (the `kind` key is omitted entirely). A free-standing associated
    /// fn (not a trait method) so serde's macro is happy. ADR-0049 §1.
    pub fn is_product(&self) -> bool {
        matches!(self, MemberKind::Product)
    }

    /// A fixed **1-byte** content-hash leaf tag — unambiguous for any current *or future* kind (a
    /// byte tag can't collide or prefix-alias the way a string separator could). The exhaustive match
    /// forces a new variant to declare its own tag at compile time. ADR-0049 §2.
    fn leaf_tag(self) -> u8 {
        match self {
            MemberKind::Product => 0x00,
            MemberKind::Collection => 0x01,
        }
    }
}

/// One member of a [`Collection`]: a flat physical product referenced by its content-addressed `id`
/// and pinned to its `manifest_hash` (so the collection seal transitively commits to the member).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CollectionMember {
    /// The member product's logical [`crate::manifest::Manifest::id`].
    pub reference: String,
    /// The member product's seal — pinned here so changing the member changes the collection.
    pub manifest_hash: String,
    pub role: Role,
    /// Product or nested sub-collection (ADR-0049 §1). Skipped on serialize when `Product` (the
    /// default) → pre-recursion collections serialize byte-identical.
    #[serde(default, skip_serializing_if = "MemberKind::is_product")]
    pub kind: MemberKind,
    /// Other members in this collection this one is derived from (their `reference`s). Forms an
    /// in-collection DAG that mirrors the manifest's `sources` edges, used by the RO-Crate
    /// projection to render `wasDerivedFrom`. Peers-only — a cross-collection dependency is
    /// materialized as a member of the enclosing collection, never a dangling reference (ADR-0049 §4).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub derived_from: Vec<String>,
}

impl CollectionMember {
    pub fn new(reference: impl Into<String>, manifest_hash: impl Into<String>, role: Role) -> Self {
        CollectionMember {
            reference: reference.into(),
            manifest_hash: manifest_hash.into(),
            role,
            kind: MemberKind::Product,
            derived_from: Vec::new(),
        }
    }

    /// Builder: mark this member as a nested sub-collection (vs the default flat product).
    pub fn with_kind(mut self, kind: MemberKind) -> Self {
        self.kind = kind;
        self
    }

    /// Builder: record the in-collection edges this member is derived from.
    pub fn with_derived_from(mut self, refs: Vec<String>) -> Self {
        self.derived_from = refs;
        self
    }
}

/// A content-addressed catalog over a set of member products (ADR-0033). Mirrors the manifest's
/// identity discipline: `id` (logical) + `content_hash` (MMR root over members in order) +
/// `manifest_hash` (the seal). Three projections of one logical collection live in `tessera-io`:
/// RO-Crate (FAIR discovery), OCI image index (registry-native), and S3-prefix layout.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Collection {
    /// Format/spec version.
    pub tessera_version: String,
    /// Stable, content-derived logical identity.
    pub id: String,
    /// Declared identity inputs (key→value) that `id` is hashed over. Default keys:
    /// `product="collection"`, `name`, `timestamp` — recorded so identity is transparent.
    pub id_inputs: BTreeMap<String, String>,
    pub name: String,
    pub description: String,
    /// RFC 3339 timestamp, normalized to UTC.
    pub timestamp: String,
    /// Optional study/grouping id (fd5 `study`) — ties this collection to other products of the
    /// same exam. Same field as on [`crate::manifest::Manifest`].
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub study: Option<String>,
    /// Optional, **open, domain-supplied** level tag (`_vocabulary`/`_code`). The engine carries it
    /// but never interprets it — level *taxonomies* (exam / cohort / site / …) are domain
    /// profiles/data, NOT an engine enum (ADR-0049 §5, RFC §12). `None` by default; part of the seal
    /// when present. This is what makes a nesting level self-describing without Tessera opining on it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub level: Option<crate::schema::Coded>,
    /// Member products, in declared order — order is significant (folded into `content_hash`).
    #[serde(default)]
    pub members: Vec<CollectionMember>,
    /// MMR root over the members' `manifest_hash`es; `Some` once sealed.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub content_hash: Option<String>,
    /// The seal: blake3 over canonical-JSON of this collection with `manifest_hash` omitted.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub manifest_hash: Option<String>,
}

/// Build the default identity-input map for a collection — mirrors
/// [`crate::identity::default_id_inputs`] but with `product = "collection"`.
pub fn default_collection_id_inputs(name: &str, timestamp: &str) -> BTreeMap<String, String> {
    BTreeMap::from([
        ("product".to_string(), "collection".to_string()),
        ("name".to_string(), name.to_string()),
        ("timestamp".to_string(), timestamp.to_string()),
    ])
}

impl Collection {
    pub fn new(
        name: impl Into<String>,
        description: impl Into<String>,
        timestamp: impl Into<String>,
    ) -> Self {
        let name = name.into();
        let description = description.into();
        // Normalise to UTC so equivalent instants in different offsets share one id (mirrors
        // [`crate::manifest::Manifest::new`]).
        let timestamp = crate::identity::normalize_timestamp(&timestamp.into());
        let id_inputs = default_collection_id_inputs(&name, &timestamp);
        // Infallible: string id_inputs always canonicalize.
        let id =
            crate::identity::compute_id(&id_inputs).expect("string id_inputs always canonicalize");
        Collection {
            tessera_version: TESSERA_VERSION.to_string(),
            id,
            id_inputs,
            name,
            description,
            timestamp,
            study: None,
            level: None,
            members: Vec::new(),
            content_hash: None,
            manifest_hash: None,
        }
    }

    /// True once the collection has been sealed (carries a manifest hash).
    pub fn is_sealed(&self) -> bool {
        self.manifest_hash.is_some()
    }

    /// Pretty JSON, for humans / display. NOT the hashed form — see [`canonical_bytes`].
    pub fn to_json(&self) -> crate::Result<String> {
        Ok(serde_json::to_string_pretty(self)?)
    }

    /// Canonical (RFC 8785 JCS) bytes of this collection with `manifest_hash` excluded — the
    /// exact bytes [`manifest_hash`](Self::manifest_hash) is computed over.
    pub fn canonical_bytes(&self) -> crate::Result<Vec<u8>> {
        let mut bare = self.clone();
        bare.manifest_hash = None;
        crate::canonical::to_bytes(&bare)
    }

    /// Recompute the logical `id` from `id_inputs`.
    pub fn recompute_id(&self) -> crate::Result<String> {
        crate::identity::compute_id(&self.id_inputs)
    }

    /// Recompute the MMR root over the members' `manifest_hash`es in declared order. Reuses the
    /// same [`crate::hash::merkle_root`] the manifest uses for block digests, so a collection is
    /// content-addressed in the exact same idiom as a product (and gets the same inclusion +
    /// consistency proofs as a free corollary).
    pub fn recompute_content_hash(&self) -> String {
        // Domain-separate the leaf by `kind` (ADR-0049 §2): each leaf is `BLAKE3(leaf-domain ‖
        // kind_byte ‖ manifest_hash)`, so an MMR inclusion proof is **kind-bound** (product-`H` and
        // collection-`H` fold to different leaves) and `kind` cannot be flipped in the JSON without
        // moving `content_hash`. A fixed 1-byte `kind_byte` is unambiguous for any future kind — no
        // string-separator prefix-collision. `merkle_root`'s own leaf/node domains (ADR-0028) are
        // unchanged. Pre-1.0 with no pinned collection goldens, adopted outright (no compat shim).
        let leaves: Vec<String> = self
            .members
            .iter()
            .map(|m| {
                let mut pre = Vec::with_capacity(m.manifest_hash.len() + 32);
                pre.extend_from_slice(b"tessera-collection-member-v1");
                pre.push(m.kind.leaf_tag());
                pre.extend_from_slice(m.manifest_hash.as_bytes());
                crate::hash::digest(&pre)
            })
            .collect();
        crate::hash::merkle_root(&leaves)
    }

    /// Recompute the seal (`manifest_hash`) over the canonical bytes.
    pub fn compute_manifest_hash(&self) -> crate::Result<String> {
        Ok(crate::hash::digest(&self.canonical_bytes()?))
    }

    /// Parse a collection JSON, refusing one whose major spec version this reader can't handle.
    /// Does not verify hashes — use [`from_json_verified`](Self::from_json_verified) for that.
    pub fn from_json(s: &str) -> crate::Result<Self> {
        let c: Collection = serde_json::from_str(s)?;
        c.check_version()?;
        Ok(c)
    }

    /// Parse + version-check + full integrity [`verify`](Self::verify).
    pub fn from_json_verified(s: &str) -> crate::Result<Self> {
        let c = Self::from_json(s)?;
        c.verify()?;
        Ok(c)
    }

    /// Verify the three hashes against their recomputed values (and the spec version). Any
    /// mismatch is a typed [`crate::Error::Integrity`] naming the field. An unsealed collection
    /// verifies its `id` only; a sealed one verifies all three. Mirrors
    /// [`crate::manifest::Manifest::verify`].
    pub fn verify(&self) -> crate::Result<()> {
        self.check_version()?;
        check("id", &self.id, &self.recompute_id()?)?;
        if let Some(ch) = &self.content_hash {
            check("content_hash", ch, &self.recompute_content_hash())?;
        }
        if let Some(mh) = &self.manifest_hash {
            check("manifest_hash", mh, &self.compute_manifest_hash()?)?;
        }
        Ok(())
    }

    /// Error if `tessera_version`'s major exceeds [`SUPPORTED_MAJOR`] (forward-incompat), or if it
    /// is unparseable. Never panics. Same policy as the manifest's version check.
    pub fn check_version(&self) -> crate::Result<()> {
        let major = self
            .tessera_version
            .split('.')
            .next()
            .and_then(|x| x.parse::<u64>().ok())
            .ok_or_else(|| {
                crate::Error::UnsupportedVersion(format!(
                    "unparseable tessera_version: {}",
                    self.tessera_version
                ))
            })?;
        if major > SUPPORTED_MAJOR {
            return Err(crate::Error::UnsupportedVersion(format!(
                "{} (reader supports major <= {SUPPORTED_MAJOR})",
                self.tessera_version
            )));
        }
        Ok(())
    }
}

/// Compare an expected vs recomputed hash, raising a typed integrity error on mismatch. Same shape
/// as the manifest's check.
fn check(what: &'static str, expected: &str, actual: &str) -> crate::Result<()> {
    if expected != actual {
        return Err(crate::Error::Integrity {
            what,
            expected: expected.to_string(),
            actual: actual.to_string(),
        });
    }
    Ok(())
}

/// A resolved reference to a sealed **product** — its logical `id` + `manifest_hash` carried as one
/// unit, so a caller can't pair the wrong reference with the wrong hash (ADR-0049 §4).
#[derive(Debug, Clone)]
pub struct ProductHandle {
    // Private so `of()` is the ONLY construction path — a caller cannot pair a wrong reference with
    // a wrong hash (ADR-0049 §4). Read via `reference()` / `manifest_hash()`.
    pub(crate) reference: String,
    pub(crate) manifest_hash: String,
}

impl ProductHandle {
    /// The pinned product reference (its logical `id`).
    pub fn reference(&self) -> &str {
        &self.reference
    }
    /// The pinned product `manifest_hash`.
    pub fn manifest_hash(&self) -> &str {
        &self.manifest_hash
    }

    /// Build from a sealed product manifest (errors if it isn't sealed yet).
    pub fn of(m: &crate::manifest::Manifest) -> crate::Result<Self> {
        Ok(ProductHandle {
            reference: m.id.clone(),
            manifest_hash: m
                .manifest_hash
                .clone()
                .ok_or_else(|| crate::Error::Invalid("product is not sealed".into()))?,
        })
    }
}

/// A resolved reference to a sealed **sub-collection** — the recursion analogue of [`ProductHandle`].
#[derive(Debug, Clone)]
pub struct CollectionHandle {
    pub(crate) reference: String,
    pub(crate) manifest_hash: String,
}

impl CollectionHandle {
    /// The pinned child-collection reference (its logical `id`).
    pub fn reference(&self) -> &str {
        &self.reference
    }
    /// The pinned child-collection `manifest_hash`.
    pub fn manifest_hash(&self) -> &str {
        &self.manifest_hash
    }

    /// Build from a sealed child collection (errors if it isn't sealed yet).
    pub fn of(c: &Collection) -> crate::Result<Self> {
        Ok(CollectionHandle {
            reference: c.id.clone(),
            manifest_hash: c
                .manifest_hash
                .clone()
                .ok_or_else(|| crate::Error::Invalid("sub-collection is not sealed".into()))?,
        })
    }
}

/// Build a [`Collection`] by adding members in order then sealing — mirrors
/// [`crate::ProductBuilder`]. Member order is preserved and is significant for `content_hash`, so
/// the same members in the same order seal to byte-identical bytes (writer-determinism).
pub struct CollectionBuilder {
    collection: Collection,
}

impl CollectionBuilder {
    pub fn new(
        name: impl Into<String>,
        description: impl Into<String>,
        timestamp: impl Into<String>,
    ) -> Self {
        CollectionBuilder {
            collection: Collection::new(name, description, timestamp),
        }
    }

    /// Set the study/grouping id (ties this collection to the products of the same exam).
    pub fn with_study(&mut self, study: impl Into<String>) -> &mut Self {
        self.collection.study = Some(study.into());
        self
    }

    /// Set the open, domain-supplied `level` tag (the engine carries it, never interprets it —
    /// ADR-0049 §5). Level taxonomies are domain data, not an engine enum.
    pub fn with_level(&mut self, level: crate::schema::Coded) -> &mut Self {
        self.collection.level = Some(level);
        self
    }

    /// Append a **product** member from its resolved handle (ADR-0049 §4) — the type-safe front for
    /// [`add_member`](Self::add_member) that can't mismatch reference/hash.
    pub fn add_product(
        &mut self,
        product: &ProductHandle,
        role: Role,
        derived_from: Vec<String>,
    ) -> &mut Self {
        self.collection.members.push(
            CollectionMember::new(&product.reference, &product.manifest_hash, role)
                .with_derived_from(derived_from),
        );
        self
    }

    /// Append a **sub-collection** member — the recursion entry point (ADR-0049 §1). Pinned by the
    /// child's `manifest_hash`; `verify` resolves it as `<ref>.collection.json` and recurses.
    pub fn add_subcollection(
        &mut self,
        sub: &CollectionHandle,
        role: Role,
        derived_from: Vec<String>,
    ) -> &mut Self {
        self.collection.members.push(
            CollectionMember::new(&sub.reference, &sub.manifest_hash, role)
                .with_kind(MemberKind::Collection)
                .with_derived_from(derived_from),
        );
        self
    }

    /// Low-level append (pins `kind = Product`). Order is preserved — the seal folds members'
    /// `manifest_hash`es in this exact order, so two builders that add the same members in different
    /// orders seal to different `content_hash`es (order is part of the catalog's identity).
    ///
    /// **Prefer the typed [`add_product`](Self::add_product) / [`add_subcollection`](Self::add_subcollection)** —
    /// this raw form cannot express a sub-collection (using it to add a nested collection would silently
    /// seal a *product*-kind leaf and the wrong `content_hash`).
    pub fn add_member(
        &mut self,
        reference: impl Into<String>,
        manifest_hash: impl Into<String>,
        role: Role,
        derived_from: Vec<String>,
    ) -> &mut Self {
        self.collection.members.push(
            CollectionMember::new(reference, manifest_hash, role).with_derived_from(derived_from),
        );
        self
    }

    /// Seal: compute the MMR root over the members, then the canonical-JSON seal. Mirrors
    /// [`crate::ProductBuilder::seal`] — the same input always yields byte-identical bytes.
    pub fn seal(mut self) -> crate::Result<Collection> {
        // Structural well-formedness of the open `level` tag (the engine still never *interprets* it,
        // ADR-0049 §5): an empty vocabulary or code is malformed, same class as an empty `name`.
        if let Some(level) = &self.collection.level {
            if level.vocabulary.is_empty() || level.code.is_empty() {
                return Err(crate::Error::Invalid(
                    "collection level tag must have a non-empty _vocabulary and _code".into(),
                ));
            }
        }
        self.collection.content_hash = Some(self.collection.recompute_content_hash());
        // Computed last, over the canonical bytes with `manifest_hash` excluded, so the seal
        // transitively commits to id_inputs, study, members + their pinned manifest_hashes, and
        // the content_hash itself.
        self.collection.manifest_hash = None;
        self.collection.manifest_hash = Some(self.collection.compute_manifest_hash()?);
        Ok(self.collection)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::manifest::Manifest;
    use crate::provenance::Source;
    use crate::ProductBuilder;

    const TS: &str = "2024-01-01T00:00:00Z";

    fn raw_listmode() -> Manifest {
        ProductBuilder::new("listmode", "DP06-raw", "raw events", TS)
            .seal()
            .unwrap()
    }

    fn derived_recon(from: &Manifest) -> Manifest {
        let mut b = ProductBuilder::new("recon", "DP06-recon", "reconstructed", TS);
        b.add_source(
            Source::new("derived_from", &from.id)
                .with_content_hash(from.manifest_hash.clone().unwrap()),
        );
        b.seal().unwrap()
    }

    fn build_collection(raw: &Manifest, recon: &Manifest) -> Collection {
        let mut cb = CollectionBuilder::new("DP06-study", "DUPLET DP06 study", TS);
        cb.with_study("DP06-2024-01");
        cb.add_member(
            &raw.id,
            raw.manifest_hash.clone().unwrap(),
            Role::Raw,
            Vec::new(),
        );
        cb.add_member(
            &recon.id,
            recon.manifest_hash.clone().unwrap(),
            Role::Derived,
            vec![raw.id.clone()],
        );
        cb.seal().unwrap()
    }

    #[test]
    fn collection_is_deterministic_and_content_addressed() {
        let raw = raw_listmode();
        let recon = derived_recon(&raw);
        let a = build_collection(&raw, &recon);
        let b = build_collection(&raw, &recon);
        // identical inputs (same members, same order) → byte-identical sealed bytes.
        assert!(a.is_sealed());
        assert_eq!(a.id, b.id);
        assert_eq!(a.content_hash, b.content_hash);
        assert_eq!(a.manifest_hash, b.manifest_hash);
        assert_eq!(a.canonical_bytes().unwrap(), b.canonical_bytes().unwrap());
        a.verify().unwrap();

        // a different member order changes content_hash + manifest_hash (id stays — it's logical).
        let mut cb = CollectionBuilder::new("DP06-study", "DUPLET DP06 study", TS);
        cb.with_study("DP06-2024-01");
        cb.add_member(
            &recon.id,
            recon.manifest_hash.clone().unwrap(),
            Role::Derived,
            vec![raw.id.clone()],
        );
        cb.add_member(
            &raw.id,
            raw.manifest_hash.clone().unwrap(),
            Role::Raw,
            Vec::new(),
        );
        let reordered = cb.seal().unwrap();
        assert_eq!(
            reordered.id, a.id,
            "id is logical — order doesn't change it"
        );
        assert_ne!(reordered.content_hash, a.content_hash);
        assert_ne!(reordered.manifest_hash, a.manifest_hash);

        // tampering with a member's pinned manifest_hash changes content_hash + manifest_hash.
        let mut tampered = a.clone();
        tampered.members[0].manifest_hash = "blake3:deadbeef".into();
        assert_ne!(
            tampered.recompute_content_hash(),
            a.recompute_content_hash()
        );
        match tampered.verify() {
            Err(crate::Error::Integrity { what, .. }) => assert_eq!(what, "content_hash"),
            other => panic!("expected content_hash integrity error, got {other:?}"),
        }
    }

    #[test]
    fn collection_id_independent_of_descriptive_metadata() {
        // Mirrors the manifest's identity discipline: changing description (non-identity-bearing)
        // does NOT change id; changing name (identity-bearing) does.
        let a = CollectionBuilder::new("DP06", "first description", TS)
            .seal()
            .unwrap();
        let b = CollectionBuilder::new("DP06", "different description", TS)
            .seal()
            .unwrap();
        let c = CollectionBuilder::new("DP07", "first description", TS)
            .seal()
            .unwrap();
        assert_eq!(a.id, b.id, "description is not identity-bearing");
        assert_ne!(a.id, c.id, "name IS identity-bearing");
        // a sealed empty collection still verifies (empty MMR root is well-defined).
        a.verify().unwrap();
    }

    #[test]
    fn collection_round_trips_through_canonical_json() {
        let raw = raw_listmode();
        let recon = derived_recon(&raw);
        let c = build_collection(&raw, &recon);
        let parsed = Collection::from_json_verified(&c.to_json().unwrap()).unwrap();
        assert_eq!(parsed.manifest_hash, c.manifest_hash);
        assert_eq!(parsed.content_hash, c.content_hash);
        assert_eq!(parsed.members.len(), 2);
        assert_eq!(parsed.members[1].derived_from, vec![raw.id]);
    }

    // ---- ADR-0049 recursion mechanism (Part 1) ----

    /// Corpus-neutrality: a product-only collection serializes with NO `kind` key (default skipped),
    /// so pre-recursion collections are byte-identical. ADR-0049 §1.
    #[test]
    fn product_only_collection_omits_the_kind_key() {
        let raw = raw_listmode();
        let recon = derived_recon(&raw);
        let json = build_collection(&raw, &recon).to_json().unwrap();
        assert!(
            !json.contains("\"kind\""),
            "default Product kind must be skipped on serialize:\n{json}"
        );
    }

    /// `content_hash` is **kind-bound**: the same `reference`+`manifest_hash` folded as a product vs.
    /// a sub-collection yields DIFFERENT roots, and the sub-collection member emits `"kind"`. ADR-0049 §2.
    #[test]
    fn content_hash_is_domain_separated_by_kind() {
        let raw = raw_listmode();
        let handle_ref = &raw.id;
        let handle_mh = raw.manifest_hash.clone().unwrap();

        let mut as_product = CollectionBuilder::new("c", "d", TS);
        as_product.add_member(handle_ref, &handle_mh, Role::Raw, Vec::new());
        let p = as_product.seal().unwrap();

        let child = CollectionHandle {
            reference: handle_ref.clone(),
            manifest_hash: handle_mh.clone(),
        };
        let mut as_collection = CollectionBuilder::new("c", "d", TS);
        as_collection.add_subcollection(&child, Role::Derived, Vec::new());
        let c = as_collection.seal().unwrap();

        assert_ne!(
            p.content_hash, c.content_hash,
            "flipping a member's kind must move content_hash (leaf domain separation)"
        );
        c.verify().unwrap();
        assert!(c.to_json().unwrap().contains("\"kind\": \"collection\""));
    }

    /// The open `level` tag is optional (omitted when None) and **bound in the seal** when present —
    /// but the engine never interprets it. ADR-0049 §5.
    #[test]
    fn level_tag_is_optional_and_sealed_but_uninterpreted() {
        let plain = CollectionBuilder::new("cohort-A", "a cohort", TS)
            .seal()
            .unwrap();
        assert!(!plain.to_json().unwrap().contains("\"level\""));

        let mut b = CollectionBuilder::new("cohort-A", "a cohort", TS);
        b.with_level(crate::schema::Coded::new(
            "tessera-imaging-levels",
            "cohort",
        ));
        let leveled = b.seal().unwrap();
        let json = leveled.to_json().unwrap();
        assert!(json.contains("tessera-imaging-levels") && json.contains("\"cohort\""));
        // The level is part of the manifest_hash seal (same name/timestamp, only level differs).
        assert_ne!(
            leveled.manifest_hash, plain.manifest_hash,
            "level must be committed by the seal"
        );
        leveled.verify().unwrap();
    }

    /// An unknown `kind` is REFUSED by the parser (serde rejects the variant; never swallowed). ADR-0049 §1.
    #[test]
    fn unknown_member_kind_is_refused() {
        let child = CollectionHandle {
            reference: "recon-x".into(),
            manifest_hash: "blake3:abc".into(),
        };
        let mut b = CollectionBuilder::new("c", "d", TS);
        b.add_subcollection(&child, Role::Derived, Vec::new());
        let json = b
            .seal()
            .unwrap()
            .to_json()
            .unwrap()
            .replace("\"kind\": \"collection\"", "\"kind\": \"teleport\"");
        assert!(
            Collection::from_json(&json).is_err(),
            "an unknown member kind must be refused, not silently accepted"
        );
    }

    /// End-to-end: a two-level nest (a cohort with a product + a sub-collection member) built through
    /// the typed handles, sealed, round-tripped, and verified. ADR-0049 §1/§4.
    #[test]
    fn nested_collection_via_typed_handles_round_trips() {
        let raw = raw_listmode();
        let recon = derived_recon(&raw);
        let exam = build_collection(&raw, &recon); // an L1 "exam" sub-collection (sealed)

        let mut cohort = CollectionBuilder::new("cohort-2024", "a cohort", TS);
        cohort.add_product(
            &ProductHandle::of(&recon).unwrap(),
            Role::Derived,
            Vec::new(),
        );
        cohort.add_subcollection(
            &CollectionHandle::of(&exam).unwrap(),
            Role::Derived,
            Vec::new(),
        );
        let sealed = cohort.seal().unwrap();

        assert_eq!(sealed.members[0].kind, MemberKind::Product);
        assert_eq!(sealed.members[1].kind, MemberKind::Collection);
        assert_eq!(sealed.members[1].reference, exam.id);

        let parsed = Collection::from_json_verified(&sealed.to_json().unwrap()).unwrap();
        assert_eq!(parsed.members[1].kind, MemberKind::Collection);
        assert_eq!(parsed.content_hash, sealed.content_hash);
    }

    /// The property leaf domain-separation exists for: a **kind-flip on a *sealed document***
    /// (collection→product) is caught by `verify` as a `content_hash` mismatch — not merely builder
    /// divergence (round-2 review). ADR-0049 §2.
    #[test]
    fn kind_flip_on_a_sealed_doc_is_caught_by_verify() {
        let child = CollectionHandle {
            reference: "exam-1".into(),
            manifest_hash: "blake3:abc".into(),
        };
        let mut b = CollectionBuilder::new("cohort", "d", TS);
        b.add_subcollection(&child, Role::Derived, Vec::new());
        let sealed = b.seal().unwrap();
        let tampered = sealed
            .to_json()
            .unwrap()
            .replace("\"kind\": \"collection\"", "\"kind\": \"product\"");
        let parsed = Collection::from_json(&tampered).unwrap(); // product is a valid kind → parses
        match parsed.verify() {
            Err(crate::Error::Integrity { what, .. }) => assert_eq!(what, "content_hash"),
            other => panic!("expected content_hash integrity error on kind-flip, got {other:?}"),
        }
    }

    /// The `add_member` footgun is detectable: adding a sub-collection via the raw `add_member`
    /// (product-kind) seals a DIFFERENT `content_hash` than `add_subcollection`. ADR-0049 §4.
    #[test]
    fn add_member_and_add_subcollection_seal_different_content_hash() {
        let child = CollectionHandle {
            reference: "x".into(),
            manifest_hash: "blake3:z".into(),
        };
        let mut raw = CollectionBuilder::new("c", "d", TS);
        raw.add_member(
            child.reference(),
            child.manifest_hash(),
            Role::Derived,
            Vec::new(),
        );
        let mut typed = CollectionBuilder::new("c", "d", TS);
        typed.add_subcollection(&child, Role::Derived, Vec::new());
        assert_ne!(
            raw.seal().unwrap().content_hash,
            typed.seal().unwrap().content_hash
        );
    }

    /// An explicit `"kind": "product"` from another writer parses to the default (serde compat).
    #[test]
    fn explicit_product_kind_parses_to_default() {
        let m: CollectionMember = serde_json::from_str(
            r#"{"reference":"r","manifest_hash":"blake3:h","role":"raw","kind":"product"}"#,
        )
        .unwrap();
        assert_eq!(m.kind, MemberKind::Product);
    }

    /// A malformed (empty) level tag is refused at seal — structural well-formedness (round-2 review).
    #[test]
    fn empty_level_tag_is_refused_at_seal() {
        let mut b = CollectionBuilder::new("c", "d", TS);
        b.with_level(crate::schema::Coded::new("", ""));
        assert!(b.seal().is_err());
    }
}
