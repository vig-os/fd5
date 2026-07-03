//! Table block — columnar storage. arrow/parquet backend (feature `table-arrow`).
//!
//! Listmode events, spectra, ROIs. Columnar (never row-major compound — see fd5 #193: a
//! single-column projection on compound costs a full-table read). Per-column codecs, and an
//! optional secondary index for fast random per-event `take` (Lance-style).

use serde::{Deserialize, Serialize};

use super::{Block, BlockKind};

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Column {
    pub name: String,
    /// Arrow-ish dtype string, e.g. "i2", "u4", "f4".
    pub dtype: String,
    /// Per-column codec — columnar layout lets each column compress optimally.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub codec: Option<String>,
    /// Human-facing short label (fd5 I1/I2), distinct from `name` (the rename-safe storage id).
    /// e.g. `name = "lt"`, `short_name = "lifetime"`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub short_name: Option<String>,
    /// Human + AI-readable description of the column's meaning — so a reader (or an AI) has the
    /// column's semantics without external context (FAIR I1/I2). The vendor HDF5 carries none.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// UCUM physical unit of the values (after `scale`, if any): "keV", "mm", "ns", "ms", "1".
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub unit: Option<String>,
    /// Fixed-point scale (#310): physical value = `raw × scale`. `None` ⇒ values are already
    /// physical (no quantization). Carried so the read/compute path recovers physical units.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scale: Option<f64>,
    /// Nullability marker (#330): when `true`, the column carries a validity bitmap alongside its
    /// values (Arrow/Vortex native nullness), and `NaN`/`None` values are stored as **NULL** rather
    /// than a float sentinel. Default `false`, skipped on serialize when unset — so a legacy column
    /// (or any non-null column) serializes byte-identical to today, preserving on-disk content
    /// hashes and the conformance corpus.
    #[serde(default, skip_serializing_if = "is_false")]
    pub nullable: bool,
}

/// Serde helper: skip a `bool` field when it's `false` (the null default), so an unannotated
/// column round-trips byte-identical through JSON.
fn is_false(b: &bool) -> bool {
    !*b
}

impl Column {
    /// A bare column: storage `name` + `dtype`, no codec/annotation. Chain the `with_*` builders
    /// to attach the fd5 annotation triad (`short_name`/`description`/`unit`) and a `scale`.
    pub fn new(name: impl Into<String>, dtype: impl Into<String>) -> Self {
        Column {
            name: name.into(),
            dtype: dtype.into(),
            ..Default::default()
        }
    }
    /// Builder: per-column codec.
    pub fn with_codec(mut self, codec: impl Into<String>) -> Self {
        self.codec = Some(codec.into());
        self
    }
    /// Builder: human short label.
    pub fn with_short_name(mut self, short_name: impl Into<String>) -> Self {
        self.short_name = Some(short_name.into());
        self
    }
    /// Builder: description.
    pub fn with_description(mut self, description: impl Into<String>) -> Self {
        self.description = Some(description.into());
        self
    }
    /// Builder: UCUM unit.
    pub fn with_unit(mut self, unit: impl Into<String>) -> Self {
        self.unit = Some(unit.into());
        self
    }
    /// Builder: fixed-point scale (physical = raw × scale).
    pub fn with_scale(mut self, scale: f64) -> Self {
        self.scale = Some(scale);
        self
    }
    /// Builder: mark the column nullable (#330 — values carry a validity bitmap; missing rows
    /// serialize as NULL rather than a float sentinel). Idempotent.
    pub fn with_nullable(mut self) -> Self {
        self.nullable = true;
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TableSpec {
    pub columns: Vec<Column>,
    pub rows: u64,
    /// Optional secondary index column enabling O(1)-ish random row `take`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub row_index: Option<String>,
}

pub struct TableBlock {
    pub name: String,
    pub spec: TableSpec,
}

impl TableBlock {
    pub fn new(name: impl Into<String>, spec: TableSpec) -> Self {
        TableBlock {
            name: name.into(),
            spec,
        }
    }
}

impl Block for TableBlock {
    fn name(&self) -> &str {
        &self.name
    }
    fn kind(&self) -> BlockKind {
        BlockKind::Table
    }
    fn spec_json(&self) -> crate::Result<serde_json::Value> {
        Ok(serde_json::to_value(&self.spec)?)
    }
    fn digest(&self) -> crate::Result<String> {
        // Spike: digest the spec. Real impl digests the encoded column chunks.
        Ok(crate::hash::digest(&serde_json::to_vec(&self.spec)?))
    }
}

#[cfg(feature = "table-arrow")]
impl TableBlock {
    /// Write the columnar payload via arrow/parquet. Not yet implemented.
    pub fn write_parquet(&self, _path: &std::path::Path) -> crate::Result<()> {
        Err(crate::Error::Unimplemented(
            "TableBlock::write_parquet (arrow backend)",
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::Column;

    #[test]
    fn builders_attach_annotation_triad_and_scale() {
        let c = Column::new("en", "i2")
            .with_short_name("energy")
            .with_description("Calibrated per-photon energy")
            .with_unit("keV")
            .with_scale(0.1);
        assert_eq!(c.name, "en");
        assert_eq!(c.dtype, "i2");
        assert_eq!(c.short_name.as_deref(), Some("energy"));
        assert_eq!(c.unit.as_deref(), Some("keV"));
        assert_eq!(c.scale, Some(0.1));
        assert_eq!(c.codec, None);
    }

    #[test]
    fn bare_column_skips_annotation_fields_on_serialize() {
        // Back-compat: an unannotated column serializes to exactly the legacy shape (name+dtype
        // only), so existing on-disk `.tsra` specs and content hashes are unaffected. Order-
        // agnostic: `serde_json`'s Map iterates alphabetically without the `preserve_order`
        // feature — the invariant is the KEY SET, not its iteration order.
        let bare = Column::new("ms", "u4");
        let v = serde_json::to_value(&bare).unwrap();
        let obj = v.as_object().unwrap();
        let mut keys: Vec<&str> = obj.keys().map(String::as_str).collect();
        keys.sort();
        assert_eq!(keys, vec!["dtype", "name"]);
    }

    #[test]
    fn annotation_round_trips_through_json() {
        let c = Column::new("lt", "i2").with_unit("ns").with_scale(0.001);
        let back: Column = serde_json::from_str(&serde_json::to_string(&c).unwrap()).unwrap();
        assert_eq!(back, c);
    }

    #[test]
    fn legacy_spec_without_annotation_deserializes() {
        // A pre-#307 column (no annotation keys) must still parse (fields default to None).
        let c: Column = serde_json::from_str(r#"{"name":"t","dtype":"u8"}"#).unwrap();
        assert_eq!(c.name, "t");
        assert!(c.unit.is_none() && c.scale.is_none() && c.description.is_none());
        assert!(!c.nullable, "legacy column defaults to non-nullable");
    }

    #[test]
    fn nullable_flag_round_trips_and_skips_when_false() {
        // #330 back-compat: `nullable: false` is the default, MUST NOT appear on serialize (so a
        // non-null column is byte-identical to today's on-disk shape and content hashes are
        // preserved). A nullable column round-trips through JSON with the flag set.
        let bare = Column::new("t", "u8");
        let v = serde_json::to_value(&bare).unwrap();
        let obj = v.as_object().unwrap();
        assert!(
            !obj.contains_key("nullable"),
            "unset `nullable` MUST be skipped — content-hash stability"
        );

        let n = Column::new("lt_corr", "i2")
            .with_unit("ns")
            .with_scale(0.001)
            .with_nullable();
        assert!(n.nullable);
        let v2 = serde_json::to_value(&n).unwrap();
        assert_eq!(v2["nullable"], true);
        let back: Column = serde_json::from_value(v2).unwrap();
        assert_eq!(back, n);
    }
}
