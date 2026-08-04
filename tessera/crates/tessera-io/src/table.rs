//! Table block backend — columnar storage as a deterministic **Vortex** file (the settled table
//! backend: smallest + O(1) random-take + filter-pushdown + zero-copy Arrow→DuckDB, spike
//! S0/S4/S7/S10/S11). The real codec behind a [`TableSpec`] block: a set of typed columns ⇄ the
//! exact bytes stored at `blocks/<name>` in a `.tsra`, and back.
//!
//! Like [`crate::array`], the payload is one self-contained, **byte-deterministic** blob (verified:
//! the Vortex 0.75 file writer produces identical bytes for identical input — the writer-determinism
//! release gate), digested over the encoded bytes. Column dtypes use the fd5 numpy-style codes
//! (`i1/i2/i4/i8`, `u1/u2/u4/u8`, `f4/f8`) carried in [`tessera_core::block::table::Column`].
//!
//! # Reading — performance & the intended access pattern
//!
//! **These are Vortex-native reads and they parallelise.** [`decode`] /
//! [`decode_projected`] drive the scan on a per-thread multi-core worker pool
//! (`READ_RT`) so segment I/O + decode fan out across cores — do **not**
//! reach for the bare single-threaded runtime and hand-roll a scan loop; that
//! path is single-core and will read ~4× slower than a mature row store, which is
//! a misuse artefact, not a property of the format.
//!
//! Match the read to the format's shape:
//! - **Project** — ask only for the columns you need ([`decode_projected`] /
//!   [`decode_column`]); Vortex reads just those columns' layout segments.
//! - **Full-materialise-to-`Vec<struct>` is the slow path on purpose.** The
//!   fast, intended consumption is the columnar/zero-copy one (project + filter,
//!   hand the canonical arrays to Arrow/DuckDB) — not decompressing every row into
//!   host structs. A `decode`-everything-then-iterate bench measures the one
//!   access pattern a columnar store is worst at.
//!
//! (Context: this guidance was added after a good-faith integrator copied
//! `runtime_session`'s single-thread runtime into a hand-rolled loop, benched
//! full-materialise, and wrongly concluded "Vortex decode is slow." The runtime
//! choice + intended access pattern were the missing signposts.)

use futures::StreamExt;
use tessera_core::block::table::TableSpec;
use tessera_core::block::{BlockKind, BlockRef};
use tessera_core::chunk_index::{ChunkIndex, ChunkStats};
use tessera_core::hash::digest;
use tessera_core::{Error, Result};
use vortex_array::accessor::ArrayAccessor;
use vortex_array::arrays::struct_::StructArrayExt;
use vortex_array::arrays::{BoolArray, ChunkedArray, PrimitiveArray, StructArray, VarBinViewArray};
use vortex_array::expr::{root, select};
use vortex_array::iter::{ArrayIteratorAdapter, ArrayIteratorExt};
use vortex_array::scalar_fn::session::ScalarFnSession;
use vortex_array::session::ArraySession;
use vortex_array::ExecutionCtx;
use vortex_array::{ArrayRef, IntoArray, VortexSessionExecute};
use vortex_btrblocks::schemes::float::{ALPRDScheme, ALPScheme};
use vortex_btrblocks::{BtrBlocksCompressorBuilder, SchemeExt};
use vortex_buffer::{Buffer, ByteBuffer, ByteBufferMut};
use vortex_file::{
    register_default_encodings, OpenOptionsSessionExt, WriteOptionsSessionExt, WriteStrategyBuilder,
};
use vortex_io::runtime::current::{CurrentThreadRuntime, CurrentThreadWorkerPool};
use vortex_io::runtime::BlockingRuntime;
use vortex_io::session::{RuntimeSession, RuntimeSessionExt};
use vortex_layout::session::LayoutSession;
use vortex_session::VortexSession;

use crate::BlockPayload;

/// One column's typed values (C order). Covers the numeric dtypes Vortex stores natively; the fd5
/// numpy code (`i2`, `u4`, `f4`, …) names the dtype in the [`TableSpec`].
#[derive(Debug, Clone, PartialEq)]
pub enum ColumnData {
    I8(Vec<i8>),
    I16(Vec<i16>),
    I32(Vec<i32>),
    I64(Vec<i64>),
    U8(Vec<u8>),
    U16(Vec<u16>),
    U32(Vec<u32>),
    U64(Vec<u64>),
    F32(Vec<f32>),
    F64(Vec<f64>),
    /// Boolean column (dtype code `b1`). Bit-packed on the wire (Vortex
    /// `BoolArray`); this in-memory form is a plain `Vec<bool>`.
    Bool(Vec<bool>),
    /// UTF-8 string column (dtype code `str`). Genuine variable/high-cardinality
    /// text; Vortex picks FSST/dictionary automatically for low-cardinality
    /// repeats. (For *known* small enums prefer an integer code column + a
    /// categorical descriptor — a schema choice, not a `ColumnData` variant.)
    Utf8(Vec<String>),
}

impl ColumnData {
    /// The fd5 numpy-style dtype code (matches [`tessera_core::block::table::Column::dtype`]).
    pub fn numpy_code(&self) -> &'static str {
        match self {
            ColumnData::I8(_) => "i1",
            ColumnData::I16(_) => "i2",
            ColumnData::I32(_) => "i4",
            ColumnData::I64(_) => "i8",
            ColumnData::U8(_) => "u1",
            ColumnData::U16(_) => "u2",
            ColumnData::U32(_) => "u4",
            ColumnData::U64(_) => "u8",
            ColumnData::F32(_) => "f4",
            ColumnData::F64(_) => "f8",
            ColumnData::Bool(_) => "b1",
            ColumnData::Utf8(_) => "str",
        }
    }

    pub fn len(&self) -> usize {
        match self {
            ColumnData::I8(v) => v.len(),
            ColumnData::I16(v) => v.len(),
            ColumnData::I32(v) => v.len(),
            ColumnData::I64(v) => v.len(),
            ColumnData::U8(v) => v.len(),
            ColumnData::U16(v) => v.len(),
            ColumnData::U32(v) => v.len(),
            ColumnData::U64(v) => v.len(),
            ColumnData::F32(v) => v.len(),
            ColumnData::F64(v) => v.len(),
            ColumnData::Bool(v) => v.len(),
            ColumnData::Utf8(v) => v.len(),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Reserve capacity for exactly `additional` more rows in the backing `Vec` — the
    /// accumulator pre-size used by the slab decoders. Lives here (rather than as a
    /// per-variant `match` at each call site) so adding a variant can't leave a downstream
    /// pre-size loop silently unhandled.
    pub fn reserve_exact(&mut self, additional: usize) {
        match self {
            ColumnData::I8(v) => v.reserve_exact(additional),
            ColumnData::I16(v) => v.reserve_exact(additional),
            ColumnData::I32(v) => v.reserve_exact(additional),
            ColumnData::I64(v) => v.reserve_exact(additional),
            ColumnData::U8(v) => v.reserve_exact(additional),
            ColumnData::U16(v) => v.reserve_exact(additional),
            ColumnData::U32(v) => v.reserve_exact(additional),
            ColumnData::U64(v) => v.reserve_exact(additional),
            ColumnData::F32(v) => v.reserve_exact(additional),
            ColumnData::F64(v) => v.reserve_exact(additional),
            ColumnData::Bool(v) => v.reserve_exact(additional),
            ColumnData::Utf8(v) => v.reserve_exact(additional),
        }
    }

    /// The column's values as `i64` for chunk-statistics (ADR-0028 §3), if it is an integer column that
    /// fits losslessly: `i1/i2/i4/i8`, `u1/u2/u4` always, and `u8` (u64) only when every value ≤
    /// `i64::MAX` (a monotonic cast → `min`/`max` stay exact). Float columns return `None` (they need
    /// canonical reduction before stats — ADR-0024).
    pub fn as_i64(&self) -> Option<Vec<i64>> {
        match self {
            ColumnData::I8(v) => Some(v.iter().map(|&x| x as i64).collect()),
            ColumnData::I16(v) => Some(v.iter().map(|&x| x as i64).collect()),
            ColumnData::I32(v) => Some(v.iter().map(|&x| x as i64).collect()),
            ColumnData::I64(v) => Some(v.clone()),
            ColumnData::U8(v) => Some(v.iter().map(|&x| x as i64).collect()),
            ColumnData::U16(v) => Some(v.iter().map(|&x| x as i64).collect()),
            ColumnData::U32(v) => Some(v.iter().map(|&x| x as i64).collect()),
            ColumnData::U64(v) => v
                .iter()
                .all(|&x| x <= i64::MAX as u64)
                .then(|| v.iter().map(|&x| x as i64).collect()),
            ColumnData::F32(_) | ColumnData::F64(_) | ColumnData::Bool(_) | ColumnData::Utf8(_) => {
                None
            }
        }
    }

    /// Flatten the column to little-endian bytes for zero-copy reconstruction in another runtime —
    /// e.g. `numpy.frombuffer(buf, "<" + numpy_code)`.
    pub fn to_le_bytes(&self) -> Vec<u8> {
        use crate::array::le_bytes;
        match self {
            ColumnData::I8(v) => v.iter().map(|x| *x as u8).collect(),
            ColumnData::I16(v) => le_bytes(v, i16::to_le_bytes),
            ColumnData::I32(v) => le_bytes(v, i32::to_le_bytes),
            ColumnData::I64(v) => le_bytes(v, i64::to_le_bytes),
            ColumnData::U8(v) => v.clone(),
            ColumnData::U16(v) => le_bytes(v, u16::to_le_bytes),
            ColumnData::U32(v) => le_bytes(v, u32::to_le_bytes),
            ColumnData::U64(v) => le_bytes(v, u64::to_le_bytes),
            ColumnData::F32(v) => le_bytes(v, f32::to_le_bytes),
            ColumnData::F64(v) => le_bytes(v, f64::to_le_bytes),
            ColumnData::Bool(v) => v.iter().map(|&b| b as u8).collect(),
            // length-prefixed: [u32 LE len | utf8 bytes] per string.
            ColumnData::Utf8(v) => {
                let mut out = Vec::new();
                for s in v {
                    out.extend_from_slice(&(s.len() as u32).to_le_bytes());
                    out.extend_from_slice(s.as_bytes());
                }
                out
            }
        }
    }

    /// Build a [`ColumnData`] from a little-endian buffer + numpy code (`i1/i2/i4/i8`, `u1/u2/u4/u8`,
    /// `f4/f8`) — the inverse of [`Self::to_le_bytes`] + [`Self::numpy_code`].
    pub fn from_le_bytes(numpy_code: &str, bytes: &[u8]) -> Result<ColumnData> {
        use crate::array::from_le;
        Ok(match numpy_code {
            "i1" => ColumnData::I8(bytes.iter().map(|&b| b as i8).collect()),
            "i2" => ColumnData::I16(from_le(bytes, i16::from_le_bytes)?),
            "i4" => ColumnData::I32(from_le(bytes, i32::from_le_bytes)?),
            "i8" => ColumnData::I64(from_le(bytes, i64::from_le_bytes)?),
            "u1" => ColumnData::U8(bytes.to_vec()),
            "u2" => ColumnData::U16(from_le(bytes, u16::from_le_bytes)?),
            "u4" => ColumnData::U32(from_le(bytes, u32::from_le_bytes)?),
            "u8" => ColumnData::U64(from_le(bytes, u64::from_le_bytes)?),
            "f4" => ColumnData::F32(from_le(bytes, f32::from_le_bytes)?),
            "f8" => ColumnData::F64(from_le(bytes, f64::from_le_bytes)?),
            "b1" => ColumnData::Bool(bytes.iter().map(|&b| b != 0).collect()),
            // inverse of the Utf8 length-prefixed encoding: [u32 LE len | bytes]*.
            "str" => {
                let mut v = Vec::new();
                let mut i = 0usize;
                while i + 4 <= bytes.len() {
                    let len =
                        u32::from_le_bytes([bytes[i], bytes[i + 1], bytes[i + 2], bytes[i + 3]])
                            as usize;
                    i += 4;
                    let end = i
                        .checked_add(len)
                        .filter(|&e| e <= bytes.len())
                        .ok_or_else(|| {
                            Error::Codec("truncated utf8 length-prefixed column".to_string())
                        })?;
                    v.push(String::from_utf8_lossy(&bytes[i..end]).into_owned());
                    i = end;
                }
                ColumnData::Utf8(v)
            }
            other => {
                return Err(Error::Codec(format!(
                    "unsupported column dtype code '{other}'"
                )))
            }
        })
    }

    /// The `[start, end)` row sub-range of this column — used to slice a table into row-groups.
    pub fn slice(&self, start: usize, end: usize) -> ColumnData {
        macro_rules! sl {
            ($v:expr, $variant:ident) => {
                ColumnData::$variant($v[start..end].to_vec())
            };
        }
        match self {
            ColumnData::I8(v) => sl!(v, I8),
            ColumnData::I16(v) => sl!(v, I16),
            ColumnData::I32(v) => sl!(v, I32),
            ColumnData::I64(v) => sl!(v, I64),
            ColumnData::U8(v) => sl!(v, U8),
            ColumnData::U16(v) => sl!(v, U16),
            ColumnData::U32(v) => sl!(v, U32),
            ColumnData::U64(v) => sl!(v, U64),
            ColumnData::F32(v) => sl!(v, F32),
            ColumnData::F64(v) => sl!(v, F64),
            ColumnData::Bool(v) => sl!(v, Bool),
            ColumnData::Utf8(v) => sl!(v, Utf8),
        }
    }

    /// Append another column's values onto this one (dtypes must match).
    pub fn extend(&mut self, other: &ColumnData) -> Result<()> {
        macro_rules! ext {
            ($v:expr, $variant:ident) => {
                match other {
                    ColumnData::$variant(o) => $v.extend_from_slice(o),
                    _ => {
                        return Err(Error::Codec(format!(
                            "extend: dtype {} != {}",
                            other.numpy_code(),
                            self.numpy_code()
                        )))
                    }
                }
            };
        }
        match self {
            ColumnData::I8(v) => ext!(v, I8),
            ColumnData::I16(v) => ext!(v, I16),
            ColumnData::I32(v) => ext!(v, I32),
            ColumnData::I64(v) => ext!(v, I64),
            ColumnData::U8(v) => ext!(v, U8),
            ColumnData::U16(v) => ext!(v, U16),
            ColumnData::U32(v) => ext!(v, U32),
            ColumnData::U64(v) => ext!(v, U64),
            ColumnData::F32(v) => ext!(v, F32),
            ColumnData::F64(v) => ext!(v, F64),
            ColumnData::Bool(v) => ext!(v, Bool),
            ColumnData::Utf8(v) => ext!(v, Utf8),
        }
        Ok(())
    }

    /// Bytes per element of a **fixed-width** numpy dtype code (`i1`=1 … `f8`=8, `b1`=1).
    ///
    /// `b1` is 1 byte per value in this LE form (see [`Self::to_le_bytes`] — the *wire* form is
    /// bit-packed by Vortex, but the flat byte form is one byte per bool), so it is fixed-width
    /// like the numerics.
    ///
    /// `str` has **no** element size — it is length-prefixed and varies per value — so it is an
    /// error here by design. Callers that only need "is this a dtype we support?" must use
    /// [`Self::validate_dtype`]; using this function for that question silently excludes every
    /// variable-width column.
    pub fn dtype_size(code: &str) -> Result<usize> {
        Ok(match code {
            "i1" | "u1" | "b1" => 1,
            "i2" | "u2" => 2,
            "i4" | "u4" | "f4" => 4,
            "i8" | "u8" | "f8" => 8,
            "str" => {
                return Err(Error::Codec(
                    "dtype 'str' is variable-width and has no element size".to_string(),
                ))
            }
            other => return Err(Error::Codec(format!("unknown dtype code '{other}'"))),
        })
    }

    /// Whether `code` names a dtype [`ColumnData`] can represent — including the variable-width
    /// `str`. This is the correct front-door check for "can this column be written?"; it exists
    /// because [`Self::dtype_size`] was being used for that question, which rejected `b1`/`str`
    /// and so locked the boolean and string column types out of every streaming write path.
    pub fn validate_dtype(code: &str) -> Result<()> {
        match code {
            "i1" | "i2" | "i4" | "i8" | "u1" | "u2" | "u4" | "u8" | "f4" | "f8" | "b1" | "str" => {
                Ok(())
            }
            other => Err(Error::Codec(format!("unknown dtype code '{other}'"))),
        }
    }

    /// Whether `code` is fixed-width (every value occupies [`Self::dtype_size`] bytes).
    pub fn dtype_is_fixed_width(code: &str) -> bool {
        Self::dtype_size(code).is_ok()
    }

    fn to_vortex(&self) -> ArrayRef {
        match self {
            ColumnData::I8(v) => Buffer::copy_from(v.as_slice()).into_array(),
            ColumnData::I16(v) => Buffer::copy_from(v.as_slice()).into_array(),
            ColumnData::I32(v) => Buffer::copy_from(v.as_slice()).into_array(),
            ColumnData::I64(v) => Buffer::copy_from(v.as_slice()).into_array(),
            ColumnData::U8(v) => Buffer::copy_from(v.as_slice()).into_array(),
            ColumnData::U16(v) => Buffer::copy_from(v.as_slice()).into_array(),
            ColumnData::U32(v) => Buffer::copy_from(v.as_slice()).into_array(),
            ColumnData::U64(v) => Buffer::copy_from(v.as_slice()).into_array(),
            ColumnData::F32(v) => Buffer::copy_from(v.as_slice()).into_array(),
            ColumnData::F64(v) => Buffer::copy_from(v.as_slice()).into_array(),
            ColumnData::Bool(v) => v.iter().copied().collect::<BoolArray>().into_array(),
            ColumnData::Utf8(v) => {
                VarBinViewArray::from_iter_str(v.iter().map(|s| s.as_str())).into_array()
            }
        }
    }
}

/// An ordered set of named columns — the decoded form of a table block (column order matches the
/// [`TableSpec`]). All columns have the same length (`rows`).
pub type TableData = Vec<(String, ColumnData)>;

/// An empty column of the dtype named by a numpy code (the decode accumulator).
fn empty_column(code: &str) -> Result<ColumnData> {
    empty_column_with_capacity(code, 0)
}

/// An empty accumulator column, pre-sized for `cap` rows.
///
/// **This is the dominant cost of a full-materialise read.** Profiling (`examples/read_profile`)
/// attributes a 2 M-row × 21-column [`decode`] as ~2 % layout/scan, ~17 % genuine Vortex
/// decompress, and **~81 % this host copy** — so the accumulators' growth policy, not the codec,
/// sets the read's speed. Growing from empty re-allocates + re-copies each column O(log n) times
/// (~2–3× the traffic of one pass); reserving the declared row count up front leaves exactly one
/// copy per row-group.
///
/// `cap` comes from the spec's *declared* `rows`, which is attacker-controlled for an untrusted
/// blob, so it is clamped to [`BLOCK_ROWS`] — the partitioning law's maximum rows in one table
/// block. A larger table still decodes correctly; it just resumes amortised growth past the clamp.
fn empty_column_with_capacity(code: &str, cap: usize) -> Result<ColumnData> {
    let cap = cap.min(BLOCK_ROWS);
    Ok(match code {
        "i1" => ColumnData::I8(Vec::with_capacity(cap)),
        "i2" => ColumnData::I16(Vec::with_capacity(cap)),
        "i4" => ColumnData::I32(Vec::with_capacity(cap)),
        "i8" => ColumnData::I64(Vec::with_capacity(cap)),
        "u1" => ColumnData::U8(Vec::with_capacity(cap)),
        "u2" => ColumnData::U16(Vec::with_capacity(cap)),
        "u4" => ColumnData::U32(Vec::with_capacity(cap)),
        "u8" => ColumnData::U64(Vec::with_capacity(cap)),
        "f4" => ColumnData::F32(Vec::with_capacity(cap)),
        "f8" => ColumnData::F64(Vec::with_capacity(cap)),
        "b1" => ColumnData::Bool(Vec::with_capacity(cap)),
        "str" => ColumnData::Utf8(Vec::with_capacity(cap)),
        other => {
            return Err(Error::Codec(format!(
            "table column dtype '{other}' unsupported (numpy codes i1/i2/i4/i8 u1/u2/u4/u8 f4/f8)"
        )))
        }
    })
}

fn ze(e: impl std::fmt::Display) -> Error {
    Error::Codec(e.to_string())
}

// The per-thread Vortex runtimes + sessions the read paths use. A session needs a runtime handle
// (`CurrentThreadRuntime`, no tokio) or async IO panics, so each entry pairs the two.
// (Plain comment, not a doc comment: rustdoc does not document macro invocations, and a `///` here
// is an `unused_doc_comments` error under `-D warnings`.)
/// A fresh, **independent** encoding-registered session bound to `rt`'s handle.
///
/// Sessions must never be shared across runtimes. `VortexSession` is `Arc`-backed,
/// so `clone().with_handle(..)` rebinds the *shared* state instead of producing an
/// independent session: caching one template and re-binding a handle per call lets a
/// short-lived runtime (`encode`/`decode_column`) leave every other holder — notably
/// the long-lived pooled [`READ_RT`] session — pointing at a dropped runtime. The next
/// pooled read then panics `Attempted to use a Handle after its runtime was dropped`.
/// Regression-tested by `short_lived_runtime_does_not_poison_pooled_session`.
///
/// Building per runtime instead of cloning a template costs nothing measurable: the
/// read win is the worker pool, not session reuse (`examples/read_profile` attributes
/// ~93 % of a read to the host copy; template caching moved nothing).
fn new_session(rt: &CurrentThreadRuntime) -> VortexSession {
    let s = VortexSession::empty()
        .with::<ArraySession>()
        .with::<LayoutSession>()
        .with::<ScalarFnSession>()
        .with::<RuntimeSession>();
    register_default_encodings(&s);
    s.with_handle(rt.handle())
}

thread_local! {
    /// Per-thread **pooled** read runtime: a `CurrentThreadWorkerPool` sized to
    /// available parallelism drives the scan's segment I/O + decode across all
    /// cores in the background while `block_on` awaits results. The bare
    /// `CurrentThreadRuntime` [`runtime_session`] uses is single-threaded — which
    /// is the actual read-throughput bottleneck, NOT the columnar decode. The
    /// pool + workers are spawned once per thread and kept alive here.
    static READ_RT: (CurrentThreadRuntime, CurrentThreadWorkerPool, VortexSession) = {
        let rt = CurrentThreadRuntime::new();
        let pool = rt.new_pool();
        pool.set_workers_to_available_parallelism();
        let s = new_session(&rt);
        (rt, pool, s)
    };
}

/// A fresh Vortex runtime + session with the default encodings registered. The session needs a
/// runtime handle (`CurrentThreadRuntime`, no tokio) or async IO panics.
///
/// This is the *single-threaded* runtime. Read paths should prefer [`with_read_session`], which
/// hands out the pooled one ([`READ_RT`]).
fn runtime_session() -> (CurrentThreadRuntime, VortexSession) {
    let rt = CurrentThreadRuntime::new();
    let s = new_session(&rt);
    (rt, s)
}

/// Run `f` with the per-thread pooled read runtime+session (see [`READ_RT`]).
fn with_read_session<R>(f: impl FnOnce(&CurrentThreadRuntime, &VortexSession) -> R) -> R {
    READ_RT.with(|(rt, _pool, s)| f(rt, s))
}

/// Validate that `data` is encodable under `spec`: same column count, names, dtypes, and every
/// column the same length == `rows`.
fn validate(spec: &TableSpec, data: &TableData) -> Result<()> {
    if data.len() != spec.columns.len() {
        return Err(Error::Codec(format!(
            "table has {} columns, spec declares {}",
            data.len(),
            spec.columns.len()
        )));
    }
    for (i, (col, (name, cd))) in spec.columns.iter().zip(data).enumerate() {
        if &col.name != name {
            return Err(Error::Codec(format!(
                "column {i}: name '{name}' != spec '{}'",
                col.name
            )));
        }
        if col.dtype != cd.numpy_code() {
            return Err(Error::Codec(format!(
                "column '{name}': dtype '{}' != spec '{}'",
                cd.numpy_code(),
                col.dtype
            )));
        }
        if cd.len() as u64 != spec.rows {
            return Err(Error::Codec(format!(
                "column '{name}': {} rows != spec rows {}",
                cd.len(),
                spec.rows
            )));
        }
    }
    Ok(())
}

/// The fixed table row-group size: a table block is **always** written as a chunked Vortex file with
/// this many rows per group (the last group is the remainder). A power-of-two constant so it's part
/// of the format contract, never a writer knob — one encoder serves batch *and* streaming, and a
/// >RAM producer can flush one row-group at a time (ADR-0026).
pub const ROWS_PER_GROUP: usize = 1 << 16; // 65_536

/// **Format-invariant** maximum rows per table block — partitions a >`BLOCK_ROWS` listmode product
/// across multiple `events_NNNN` blocks (ADR-0026). Picked at 64 × [`ROWS_PER_GROUP`] = `2^22`
/// (≈ 4.19 M rows ≈ a few hundred MiB encoded for typical PET schemas), big enough that the per-block
/// Vortex footer overhead stays trivial and small enough that one block fits comfortably in a worker's
/// RAM. Changing this is a **format-breaking** change (it shifts the per-block partition, which shifts
/// the per-block bytes, which shifts every `content_hash`). The compile-time assertion below makes
/// the SSoT explicit: every block is *exactly* 64 row-groups (or fewer for the trailing partial).
pub const BLOCK_ROWS: usize = 1 << 22; // 4_194_304 = 64 × ROWS_PER_GROUP

// `is_multiple_of` is not yet const-stable on `usize` (1.87 stabilised the method, not the const
// form), so the const assertion uses the integer `%` operator directly.
#[allow(clippy::manual_is_multiple_of)]
const _: () = assert!(
    BLOCK_ROWS % ROWS_PER_GROUP == 0,
    "BLOCK_ROWS must be a whole multiple of ROWS_PER_GROUP — one block = N full row-groups"
);

/// Row-groups per full table block ([`BLOCK_ROWS`] / [`ROWS_PER_GROUP`]) — the canonical fragment
/// count at which the multi-block sink closes a block. Derived from the format invariants so a
/// future tuner can never let them drift apart.
pub const ROW_GROUPS_PER_BLOCK: usize = BLOCK_ROWS / ROWS_PER_GROUP;

/// How many [`BLOCK_ROWS`]-sized blocks `rows` partitions into. A product with `rows == 0` still
/// yields ONE block (the metadata-bearing single `events` block — an empty table is one empty
/// row-group, see [`encode`]). For `rows > 0` it's `ceil(rows / BLOCK_ROWS)` — the trailing block
/// may be partial. **Format invariant**: shared by every ingest path so whole-file and streamed
/// agree on the partition (and therefore on the `content_hash`).
pub fn block_count(rows: u64) -> u64 {
    partition_blocks(rows, BLOCK_ROWS as u64)
}

/// Partition `rows` into ceil(rows / block_rows) blocks (`max(1)` so an empty table still has one
/// block). Pure helper extracted from [`block_count`] so the partition logic can be unit-tested at a
/// **small** `block_rows` (cheap CI) while production stays pinned at the [`BLOCK_ROWS`] format
/// invariant.
pub fn partition_blocks(rows: u64, block_rows: u64) -> u64 {
    let br = block_rows.max(1);
    rows.div_ceil(br).max(1)
}

/// Canonical name for the `idx`-th of `total` blocks under `prefix`. `total <= 1` → `prefix` (the
/// **small-stays-single** invariant — a ≤ [`BLOCK_ROWS`] product writes exactly one `events` block,
/// byte-identical to today's pre-partition layout). Otherwise `prefix_NNNN` (zero-padded to 4
/// digits, plenty of headroom for the realistic block-count range — up to 9999 blocks ≈ 41 G rows).
/// Shared by writer and reader so the manifest order is unambiguous.
pub fn block_name(prefix: &str, idx: u64, total: u64) -> String {
    if total <= 1 {
        prefix.to_string()
    } else {
        format!("{prefix}_{idx:04}")
    }
}

/// Encode columns into the deterministic table-block payload bytes for `spec`.
///
/// The table is written as a **chunked** Vortex file: the columns are sliced into fixed
/// [`ROWS_PER_GROUP`] row-groups and streamed as chunks. The grid is fixed, so the bytes are a pure
/// function of the data (batch and streaming produce the *same* bytes — there is one encoder).
///
/// **ALP float-encoding is excluded** from the write strategy: Vortex's ALP codec searches for a
/// float exponent via float arithmetic, whose result varies with the *build profile's* float codegen
/// (opt-level / FMA contraction), so the same float columns would encode to different bytes under
/// different compilers — fatal for a content-addressed format. With ALP excluded, floats fall back to
/// flat `Primitive` (raw little-endian, codegen-independent) while integer encodings (Sequence/FoR/…,
/// chosen by exact integer math) remain. The payload is then a pure function of the logical data
/// (cross-environment deterministic).
pub fn encode(spec: &TableSpec, data: &TableData) -> Result<Vec<u8>> {
    validate(spec, data)?;
    let (rt, s) = runtime_session();
    let fields: Vec<(&str, ArrayRef)> = data
        .iter()
        .map(|(name, cd)| (name.as_str(), cd.to_vortex()))
        .collect();
    let full = StructArray::from_fields(&fields).map_err(ze)?.into_array();
    // Slice into fixed row-groups (≥ 1 chunk even when empty) → a chunked Vortex layout.
    let rows = spec.rows as usize;
    let n_groups = rows.div_ceil(ROWS_PER_GROUP).max(1);
    let chunks: Vec<ArrayRef> = (0..n_groups)
        .map(|g| {
            let start = g * ROWS_PER_GROUP;
            let end = ((g + 1) * ROWS_PER_GROUP).min(rows);
            full.slice(start..end).map_err(ze)
        })
        .collect::<Result<_>>()?;
    let chunked = ChunkedArray::from_iter(chunks).into_array();
    // Exclude the ALP float schemes from the compressor so it never *chooses* them; floats then use
    // the deterministic Pco/flat schemes. Integer schemes (chosen by exact integer math) are kept.
    let compressor =
        BtrBlocksCompressorBuilder::default().exclude_schemes([ALPScheme.id(), ALPRDScheme.id()]);
    let strategy = WriteStrategyBuilder::default()
        .with_btrblocks_builder(compressor)
        .build();
    let mut buf = ByteBufferMut::empty();
    rt.block_on(
        s.write_options()
            .with_strategy(strategy)
            .write(&mut buf, chunked.to_array_stream()),
    )
    .map_err(ze)?;
    let payload = buf.freeze().to_vec();
    // Encode-path observability (SSoT for table bytes): raw→encoded size + ratio, so devs see the
    // achieved columnar compression on write. raw = Σ column widths × rows. Zero-cost when no subscriber.
    let raw: usize = data
        .iter()
        .map(|(_, c)| c.len() * ColumnData::dtype_size(c.numpy_code()).unwrap_or(0))
        .sum();
    let ratio = (raw as f64) / (payload.len().max(1) as f64);
    tracing::debug!(
        target: "tessera::encode",
        kind = "table",
        rows = spec.rows,
        columns = spec.columns.len(),
        raw_bytes = raw,
        encoded_bytes = payload.len(),
        ratio = ratio,
        "encoded table block"
    );
    Ok(payload)
}

/// **Bounded-memory / >RAM variant of [`encode`]**: consume row-group [`TableData`] chunks from a
/// *lazy* iterator (each ≤ [`ROWS_PER_GROUP`] rows) and write the chunked Vortex bytes **without ever
/// holding the whole table** — the DAQ / streaming-compaction path. The iterator is pulled one chunk
/// at a time as the writer consumes it (`ArrayIteratorAdapter` → `into_array_stream`), so a producer
/// that reads one row-group fragment at a time stays at ~one-group RAM.
///
/// Feeding the row-groups in fixed-grid order yields bytes **byte-identical to [`encode`]** of the
/// concatenation — there is one logical encoder, so streaming-then-compact == batch (tested by
/// `encode_streaming_matches_batch_encode`).
pub fn encode_streaming<I>(spec: &TableSpec, groups: I) -> Result<Vec<u8>>
where
    I: IntoIterator<Item = TableData>,
    I::IntoIter: Send + 'static,
{
    let (rt, s) = runtime_session();
    // The struct dtype, taken from an empty struct of the declared columns.
    let mut empty: TableData = Vec::with_capacity(spec.columns.len());
    for c in &spec.columns {
        empty.push((c.name.clone(), empty_column(&c.dtype)?));
    }
    let efields: Vec<(&str, ArrayRef)> = empty
        .iter()
        .map(|(n, c)| (n.as_str(), c.to_vortex()))
        .collect();
    let dtype = StructArray::from_fields(&efields)
        .map_err(ze)?
        .into_array()
        .dtype()
        .clone();

    // Lazily turn each row-group into a Vortex StructArray chunk (one in flight at a time).
    let chunk_iter = groups.into_iter().map(|td| {
        let fields: Vec<(&str, ArrayRef)> = td
            .iter()
            .map(|(n, c)| (n.as_str(), c.to_vortex()))
            .collect();
        StructArray::from_fields(&fields).map(|s| s.into_array())
    });
    let array_iter = ArrayIteratorAdapter::new(dtype, chunk_iter);

    let compressor =
        BtrBlocksCompressorBuilder::default().exclude_schemes([ALPScheme.id(), ALPRDScheme.id()]);
    let strategy = WriteStrategyBuilder::default()
        .with_btrblocks_builder(compressor)
        .build();
    let mut buf = ByteBufferMut::empty();
    rt.block_on(
        s.write_options()
            .with_strategy(strategy)
            .write(&mut buf, array_iter.into_array_stream()),
    )
    .map_err(ze)?;
    Ok(buf.freeze().to_vec())
}

/// Append a decoded (canonicalized) Vortex column's values onto the matching output (bit-exact).
/// Execute one struct field into its declared `ColumnData` type and append it.
/// Numeric columns canonicalize to `PrimitiveArray`; `Bool` → `BoolArray`,
/// `Utf8` → `VarBinViewArray` (the compressor's chosen scheme is transparent
/// here — canonicalization undoes FSST/dict/bit-packing).
fn extend_field(col: &mut ColumnData, field: ArrayRef, ctx: &mut ExecutionCtx) -> Result<()> {
    match col {
        ColumnData::Bool(v) => {
            let b: BoolArray = field.execute(ctx).map_err(ze)?;
            v.extend(b.into_bit_buffer().iter());
        }
        ColumnData::Utf8(v) => {
            let s: VarBinViewArray = field.execute(ctx).map_err(ze)?;
            s.with_iterator(|it| {
                for opt in it {
                    v.push(
                        opt.map(|b| String::from_utf8_lossy(b).into_owned())
                            .unwrap_or_default(),
                    );
                }
            });
        }
        _ => {
            let prim: PrimitiveArray = field.execute(ctx).map_err(ze)?;
            extend_column(col, &prim);
        }
    }
    Ok(())
}

fn extend_column(col: &mut ColumnData, prim: &PrimitiveArray) {
    match col {
        ColumnData::I8(v) => v.extend_from_slice(prim.as_slice::<i8>()),
        ColumnData::I16(v) => v.extend_from_slice(prim.as_slice::<i16>()),
        ColumnData::I32(v) => v.extend_from_slice(prim.as_slice::<i32>()),
        ColumnData::I64(v) => v.extend_from_slice(prim.as_slice::<i64>()),
        ColumnData::U8(v) => v.extend_from_slice(prim.as_slice::<u8>()),
        ColumnData::U16(v) => v.extend_from_slice(prim.as_slice::<u16>()),
        ColumnData::U32(v) => v.extend_from_slice(prim.as_slice::<u32>()),
        ColumnData::U64(v) => v.extend_from_slice(prim.as_slice::<u64>()),
        ColumnData::F32(v) => v.extend_from_slice(prim.as_slice::<f32>()),
        ColumnData::F64(v) => v.extend_from_slice(prim.as_slice::<f64>()),
        ColumnData::Bool(_) | ColumnData::Utf8(_) => {
            unreachable!("bool/utf8 columns are handled in extend_field, not as primitives")
        }
    }
}

/// Below this many values (rows × columns) the fan-out in [`materialise`] costs more in thread
/// spawns than it saves. Small tables stay exactly as serial as they were.
const PARALLEL_MATERIALISE_MIN_VALUES: usize = 1 << 20;

/// Decompress every column out of the already-scanned row-groups and copy it into the host
/// accumulators — **column-parallel**.
///
/// This is where a full-materialise read spends its time (`examples/read_profile`: ~20 % Vortex
/// decompress + ~78 % host copy, against ~2 % for the scan itself), and it parallelises perfectly:
/// each column is touched by exactly one worker, and that worker walks the row-groups in order, so
/// the output is **bit-identical** to a serial decode (asserted by
/// `decode_is_bit_identical_across_thread_counts`). Measured 2.1× on a 10-core box for a
/// 2 M-row × 21-column listmode table; the ceiling is memory bandwidth, not core count.
///
/// The driver hands over already-scanned `chunks`, whose fields are still *encoded* views into the
/// blob the caller already holds in memory — so this buys its parallelism without inflating the
/// resident set.
fn materialise(s: &VortexSession, chunks: &[StructArray], cols: &mut [ColumnData]) -> Result<()> {
    let ncols = cols.len();
    if ncols == 0 {
        return Ok(());
    }
    let values = chunks.iter().map(|c| c.len()).sum::<usize>() * ncols;
    let threads = if values < PARALLEL_MATERIALISE_MIN_VALUES {
        1
    } else {
        // NB: sized against the whole machine. A caller that already decodes many blocks in
        // parallel should decode each block on one thread rather than nest the fan-outs.
        std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(1)
            .min(ncols)
    };
    materialise_with(s, chunks, cols, threads)
}

/// [`materialise`] with the worker count pinned — the seam the equivalence test drives to prove
/// serial and parallel produce the same bytes.
fn materialise_with(
    s: &VortexSession,
    chunks: &[StructArray],
    cols: &mut [ColumnData],
    threads: usize,
) -> Result<()> {
    let ncols = cols.len();
    if ncols == 0 {
        return Ok(());
    }
    if threads <= 1 {
        let mut ctx = s.create_execution_ctx();
        for (i, col) in cols.iter_mut().enumerate() {
            for st in chunks {
                extend_field(col, st.unmasked_field(i).clone(), &mut ctx)?;
            }
        }
        return Ok(());
    }

    let per = ncols.div_ceil(threads);
    std::thread::scope(|sc| -> Result<()> {
        let handles: Vec<_> = cols
            .chunks_mut(per)
            .enumerate()
            .map(|(t, group)| {
                let s = s.clone(); // Arc-backed — the clone is the cheap part
                sc.spawn(move || -> Result<()> {
                    let mut ctx = s.create_execution_ctx();
                    for (j, col) in group.iter_mut().enumerate() {
                        let i = t * per + j;
                        for st in chunks {
                            extend_field(col, st.unmasked_field(i).clone(), &mut ctx)?;
                        }
                    }
                    Ok(())
                })
            })
            .collect();
        for h in handles {
            h.join()
                .map_err(|_| Error::Codec("table decode worker panicked".into()))??;
        }
        Ok(())
    })
}

/// Drive the scan to completion, returning one canonical [`StructArray`] per row-group. The
/// struct is canonical but its *fields* are still encoded, so this is cheap (~2 % of a read) and
/// holds no more memory than the blob already resident in the caller's hands.
async fn scan_chunks(
    s: &VortexSession,
    blob: &[u8],
    projection: Option<&[&str]>,
) -> Result<Vec<StructArray>> {
    let mut ctx = s.create_execution_ctx();
    let scan = s
        .open_options()
        .open_buffer(ByteBuffer::copy_from(blob))
        .map_err(ze)?
        .scan()
        .map_err(ze)?;
    let scan = match projection {
        Some(names) => scan.with_projection(select(names.to_vec(), root())),
        None => scan,
    };
    let stream = scan.into_array_stream().map_err(ze)?;
    futures::pin_mut!(stream);
    let mut chunks = Vec::new();
    while let Some(chunk) = stream.next().await {
        chunks.push(chunk.map_err(ze)?.execute(&mut ctx).map_err(ze)?);
    }
    Ok(chunks)
}

/// Decode the whole table from a block payload (inverse of [`encode`]).
///
/// Sizes its own fan-out against the whole machine. A caller that is *already* decoding many
/// blocks in parallel should use [`decode_with_workers`] to pin each block to one worker instead
/// of nesting two fan-outs.
pub fn decode(spec: &TableSpec, blob: &[u8]) -> Result<TableData> {
    decode_inner(spec, blob, None)
}

/// [`decode`] with the materialise fan-out pinned to `workers` threads (`1` = fully serial).
///
/// The point is composition. `decode` sizes itself to `available_parallelism()`, which is right
/// for one decode on an idle machine and wrong inside a caller's own parallel loop — N concurrent
/// `decode`s would each spawn N workers. Decoding a cohort of blocks across a thread pool should
/// therefore pass `1` here and keep the parallelism at the outer level, where it already has
/// better work granularity.
pub fn decode_with_workers(spec: &TableSpec, blob: &[u8], workers: usize) -> Result<TableData> {
    decode_inner(spec, blob, Some(workers))
}

fn decode_inner(spec: &TableSpec, blob: &[u8], workers: Option<usize>) -> Result<TableData> {
    // Accumulators, one per declared column (column order == struct field order on write),
    // pre-sized to the declared row count — see [`empty_column_with_capacity`], this is the
    // read's dominant cost.
    let rows = spec.rows as usize;
    let mut cols: Vec<ColumnData> = spec
        .columns
        .iter()
        .map(|c| empty_column_with_capacity(&c.dtype, rows))
        .collect::<Result<_>>()?;

    with_read_session(|rt, s| {
        let chunks = rt.block_on(scan_chunks(s, blob, None))?;
        match workers {
            Some(n) => materialise_with(s, &chunks, &mut cols, n),
            None => materialise(s, &chunks, &mut cols),
        }
    })?;

    Ok(spec
        .columns
        .iter()
        .map(|c| c.name.clone())
        .zip(cols)
        .collect())
}

/// Decode a SINGLE column from a table block via Vortex **projection** — the scan reads only that
/// column's layout segments, so it doesn't materialise the whole table (the columnar-take win;
/// cf. Parquet/ROOT column projection in the #143 ecosystem bench). Bit-exact with [`decode`]'s
/// matching column.
pub fn decode_column(spec: &TableSpec, blob: &[u8], name: &str) -> Result<ColumnData> {
    let col = spec
        .columns
        .iter()
        .find(|c| c.name == name)
        .ok_or_else(|| Error::Codec(format!("table has no column '{name}'")))?;
    let (rt, s) = runtime_session();
    let mut out = empty_column_with_capacity(&col.dtype, spec.rows as usize)?;
    let mut ctx = s.create_execution_ctx();
    rt.block_on(async {
        let stream = s
            .open_options()
            .open_buffer(ByteBuffer::copy_from(blob))
            .map_err(ze)?
            .scan()
            .map_err(ze)?
            .with_projection(select([name], root())) // only this field is scanned
            .into_array_stream()
            .map_err(ze)?;
        futures::pin_mut!(stream);
        while let Some(chunk) = stream.next().await {
            let st: StructArray = chunk.map_err(ze)?.execute(&mut ctx).map_err(ze)?;
            extend_field(&mut out, st.unmasked_field(0).clone(), &mut ctx)?;
        }
        Ok::<(), Error>(())
    })?;
    Ok(out)
}

/// Decode a **projected subset** of columns in a **single session** — Vortex
/// scans only the named columns' layout segments (projection pushdown) and pays
/// the session/encoding setup **once**, unlike N separate [`decode_column`]
/// calls. The result columns are in `names` order.
///
/// This is the read shape the replay pipeline wants (a few columns of a wide
/// listmode), and where Vortex's columnar layout beats a full [`decode`].
pub fn decode_projected(spec: &TableSpec, blob: &[u8], names: &[&str]) -> Result<TableData> {
    let dtypes: Vec<String> = names
        .iter()
        .map(|&n| {
            spec.columns
                .iter()
                .find(|c| c.name == n)
                .map(|c| c.dtype.clone())
                .ok_or_else(|| Error::Codec(format!("table has no column '{n}'")))
        })
        .collect::<Result<_>>()?;
    let mut cols: Vec<ColumnData> = dtypes
        .iter()
        .map(|d| empty_column_with_capacity(d, spec.rows as usize))
        .collect::<Result<_>>()?;
    with_read_session(|rt, s| {
        let chunks = rt.block_on(scan_chunks(s, blob, Some(names)))?;
        materialise(s, &chunks, &mut cols)
    })?;
    Ok(names.iter().map(|n| n.to_string()).zip(cols).collect())
}

/// Build the `{hash, stats}` chunk-index (ADR-0028 §3) for a table block, splitting on the **same**
/// fixed [`ROWS_PER_GROUP`] row-groups [`encode`] uses. Each entry carries the row-group's content digest
/// (BLAKE3 over the group's little-endian column bytes — recomputable from the decoded group, independent
/// of the Vortex byte layout) and the chunk statistics of `stat_column` (which must be an integer column,
/// see [`ColumnData::as_i64`]). Other columns still feed each group's digest; only the stats come from
/// `stat_column`. `index.root()` is the block's sub-block Merkle root (ADR-0028 §1), and `index.prune()`
/// skips row-groups a ranged read can't hit. Per #221-B, the *index* leaf may later be finer than
/// `ROWS_PER_GROUP`; this first wiring uses the encoder's row-groups 1:1.
///
/// ```
/// use tessera_core::block::table::{Column, TableSpec};
/// use tessera_io::table::{table_chunk_index, ColumnData, TableData};
///
/// let spec = TableSpec {
///     columns: vec![Column { name: "t".into(), dtype: "u8".into(), codec: None, ..Default::default() }],
///     rows: 3,
///     row_index: None,
/// };
/// let data: TableData = vec![("t".into(), ColumnData::U64(vec![10, 20, 30]))];
/// let idx = table_chunk_index(&spec, &data, "t").unwrap();
///
/// assert_eq!(idx.len(), 1); // 3 rows <= ROWS_PER_GROUP -> a single row-group
/// assert_eq!(idx.aggregate().max, Some(30)); // stats over the column
/// assert_eq!(idx.prune(0, 15), vec![0]); // the group spans [10, 30] -> overlaps [0, 15]
/// assert!(idx.root().starts_with("blake3:")); // sub-block MMR root
/// ```
pub fn table_chunk_index(
    spec: &TableSpec,
    data: &TableData,
    stat_column: &str,
) -> Result<ChunkIndex> {
    validate(spec, data)?;
    let stat_vals = data
        .iter()
        .find(|(name, _)| name == stat_column)
        .ok_or_else(|| Error::Codec(format!("table has no column '{stat_column}'")))?
        .1
        .as_i64()
        .ok_or_else(|| {
            Error::Codec(format!(
                "column '{stat_column}' is not an integer column for stats"
            ))
        })?;
    let rows = data.first().map(|(_, c)| c.len()).unwrap_or(0);
    let n_groups = rows.div_ceil(ROWS_PER_GROUP).max(1);
    let mut idx = ChunkIndex::new();
    for g in 0..n_groups {
        let start = g * ROWS_PER_GROUP;
        let end = ((g + 1) * ROWS_PER_GROUP).min(rows);
        // group content digest = every column's LE bytes for [start, end), in column order.
        let mut bytes = Vec::new();
        for (_, col) in data.iter() {
            bytes.extend_from_slice(&col.slice(start, end).to_le_bytes());
        }
        idx.push_entry(
            digest(&bytes),
            ChunkStats::from_values(&stat_vals[start..end]),
        );
    }
    Ok(idx)
}

/// Encode a table block and produce both the digested [`BlockRef`] (digest over the real Vortex
/// payload bytes) and the [`BlockPayload`] to pack.
pub fn table_block(
    name: &str,
    spec: &TableSpec,
    data: &TableData,
) -> Result<(BlockRef, BlockPayload)> {
    let payload = encode(spec, data)?;
    let digest = tessera_core::hash::digest(&payload);
    let block_ref = BlockRef {
        name: name.to_string(),
        kind: BlockKind::Table,
        digest: Some(digest),
        spec: serde_json::to_value(spec)?,
    };
    Ok((block_ref, BlockPayload::new(name, payload)))
}

/// A committed block: its manifest reference paired with its payload bytes.
type EncodedBlock = (BlockRef, BlockPayload);

/// Fused table block emit (ADR-0028 §5): encode the table block **and** build its `{hash, stats}`
/// chunk-index sidecar over `stat_column` in one call — the table counterpart to
/// [`crate::array::array_block_with_index`]. The sidecar is built only when `stat_column` names an
/// **integer** column present in the data (else `None`: the row-group digests still roll up through the
/// data block, but there are no prunable stats). Real encode/index errors propagate.
pub fn table_block_with_index(
    name: &str,
    spec: &TableSpec,
    data: &TableData,
    stat_column: Option<&str>,
) -> Result<(EncodedBlock, Option<EncodedBlock>)> {
    let block = table_block(name, spec, data)?;
    let sidecar = match stat_column {
        Some(col) if data.iter().any(|(n, c)| n == col && c.as_i64().is_some()) => {
            let index = table_chunk_index(spec, data, col)?;
            Some(crate::chunk_index::chunk_index_block(name, &index)?)
        }
        _ => None, // no integer stat column → no prunable-stats sidecar (ADR-0028 §3 integer core)
    };
    Ok((block, sidecar))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tessera_core::block::table::Column;

    fn col(name: &str, dtype: &str) -> Column {
        Column {
            name: name.into(),
            dtype: dtype.into(),
            codec: None,
            ..Default::default()
        }
    }

    /// A table spec + data with every supported dtype as a column.
    fn all_dtype_table(rows: usize) -> (TableSpec, TableData) {
        let data: TableData = vec![
            (
                "i1".into(),
                ColumnData::I8((0..rows).map(|k| (k % 128) as i8 - 64).collect()),
            ),
            (
                "i2".into(),
                ColumnData::I16((0..rows).map(|k| (k % 4096) as i16 - 1024).collect()),
            ),
            (
                "i4".into(),
                ColumnData::I32((0..rows).map(|k| k as i32 * 7 - 100).collect()),
            ),
            (
                "i8".into(),
                ColumnData::I64((0..rows).map(|k| k as i64 * 1_000_003).collect()),
            ),
            (
                "u1".into(),
                ColumnData::U8((0..rows).map(|k| k as u8).collect()),
            ),
            (
                "u2".into(),
                ColumnData::U16((0..rows).map(|k| (k * 7) as u16).collect()),
            ),
            (
                "u4".into(),
                ColumnData::U32((0..rows).map(|k| (k * 999) as u32).collect()),
            ),
            (
                "u8".into(),
                ColumnData::U64((0..rows).map(|k| (k as u64) << 33).collect()),
            ),
            (
                "f4".into(),
                ColumnData::F32((0..rows).map(|k| k as f32 * 0.25 - 8.0).collect()),
            ),
            (
                "f8".into(),
                ColumnData::F64((0..rows).map(|k| k as f64 * 1.5).collect()),
            ),
        ];
        let columns = data.iter().map(|(n, c)| col(n, c.numpy_code())).collect();
        let spec = TableSpec {
            columns,
            rows: rows as u64,
            row_index: None,
        };
        (spec, data)
    }

    /// The column-parallel materialise must be **bit-identical** to the serial one, for every
    /// dtype (including the `Bool`/`Utf8` columns that take their own decode path) and across
    /// several row-groups — worker `t` owns columns `[t*per, (t+1)*per)` and walks the row-groups
    /// in order, so any ordering or off-by-one in the split shows up here.
    #[test]
    fn materialise_is_bit_identical_across_thread_counts() {
        let rows = ROWS_PER_GROUP + 4242; // 2 row-groups + remainder
        let (mut spec, mut data) = all_dtype_table(rows);
        data.push((
            "b1".into(),
            ColumnData::Bool((0..rows).map(|k| k % 3 == 0).collect()),
        ));
        data.push((
            "str".into(),
            ColumnData::Utf8((0..rows).map(|k| format!("crystal-{}", k % 97)).collect()),
        ));
        spec.columns = data.iter().map(|(n, c)| col(n, c.numpy_code())).collect();
        let blob = encode(&spec, &data).unwrap();

        // `repeat` duplicates the scanned chunks, exercising the multi-chunk append loop
        // regardless of how the reader chooses to batch this particular file.
        let decoded = |threads: usize, repeat: usize| -> TableData {
            let mut cols: Vec<ColumnData> = spec
                .columns
                .iter()
                .map(|c| empty_column_with_capacity(&c.dtype, rows * repeat))
                .collect::<Result<_>>()
                .unwrap();
            with_read_session(|rt, s| {
                let scanned = rt.block_on(scan_chunks(s, &blob, None)).unwrap();
                let chunks: Vec<StructArray> =
                    std::iter::repeat_n(scanned, repeat).flatten().collect();
                materialise_with(s, &chunks, &mut cols, threads).unwrap();
            });
            spec.columns
                .iter()
                .map(|c| c.name.clone())
                .zip(cols)
                .collect()
        };

        let serial = decoded(1, 1);
        assert_eq!(serial, data, "serial materialise must round-trip");
        // Every column must land in the same worker split regardless of worker count — including
        // more workers than columns (the empty-group edge).
        for threads in [2, 3, 4, 8, 64] {
            assert_eq!(
                decoded(threads, 1),
                serial,
                "materialise with {threads} workers diverged from serial"
            );
            assert_eq!(
                decoded(threads, 3),
                decoded(1, 3),
                "multi-chunk append order diverged at {threads} workers"
            );
        }
        // And both public entry points agree — the self-sizing one and the pinned one.
        assert_eq!(decode(&spec, &blob).unwrap(), data);
        for workers in [1, 2, 7] {
            assert_eq!(
                decode_with_workers(&spec, &blob, workers).unwrap(),
                data,
                "decode_with_workers({workers}) diverged"
            );
        }
    }

    #[test]
    fn table_block_with_index_emits_block_plus_optional_sidecar() {
        // ADR-0028 §5 fused emit (table counterpart): data block + optional chunk-index sidecar.
        let (spec, data) = all_dtype_table(10);
        // an integer stat column → block + sidecar; the sidecar == the separate composition.
        let ((blk, _), sidecar) = table_block_with_index("t", &spec, &data, Some("i8")).unwrap();
        let (blk_ref, _) = table_block("t", &spec, &data).unwrap();
        assert_eq!(blk.digest, blk_ref.digest);
        let (scar, _) = sidecar.expect("integer stat column yields a sidecar");
        let idx = table_chunk_index(&spec, &data, "i8").unwrap();
        let (expect, _) = crate::chunk_index::chunk_index_block("t", &idx).unwrap();
        assert_eq!(scar.digest, expect.digest);
        assert_eq!(scar.name, expect.name);
        // None, a float column, or an absent column → no prunable-stats sidecar.
        assert!(table_block_with_index("t", &spec, &data, None)
            .unwrap()
            .1
            .is_none());
        assert!(table_block_with_index("t", &spec, &data, Some("f8"))
            .unwrap()
            .1
            .is_none());
        assert!(table_block_with_index("t", &spec, &data, Some("nope"))
            .unwrap()
            .1
            .is_none());
    }

    #[test]
    fn column_from_le_bytes_inverts_to_le_bytes() {
        let cases = [
            ColumnData::I8(vec![-1, 0, 127]),
            ColumnData::U8(vec![1, 2, 255]),
            ColumnData::U16(vec![0, 513, 65535]),
            ColumnData::F32(vec![0.5, -0.0, f32::INFINITY]),
            ColumnData::I64(vec![-1, 1_000_003, i64::MIN]),
        ];
        for c in cases {
            let back = ColumnData::from_le_bytes(c.numpy_code(), &c.to_le_bytes()).unwrap();
            assert_eq!(back, c);
        }
        assert!(ColumnData::from_le_bytes("f4", &[0u8; 3]).is_err()); // not a multiple of width
    }

    #[test]
    fn encode_streaming_matches_batch_encode() {
        // The SSoT proof: feeding row-groups through the lazy streaming encoder produces bytes
        // byte-identical to a batch encode of the whole table → one encoder, streaming == batch.
        let rows = ROWS_PER_GROUP + 9000; // 2 groups + remainder
        let spec = TableSpec {
            columns: vec![col("t", "u8"), col("e", "f4")],
            rows: rows as u64,
            row_index: Some("t".into()),
        };
        let full: TableData = vec![
            ("t".into(), ColumnData::U64((0..rows as u64).collect())),
            (
                "e".into(),
                ColumnData::F32((0..rows).map(|k| 511.0 + (k % 13) as f32).collect()),
            ),
        ];
        let n = rows.div_ceil(ROWS_PER_GROUP);
        let groups: Vec<TableData> = (0..n)
            .map(|g| {
                let (st, en) = (g * ROWS_PER_GROUP, ((g + 1) * ROWS_PER_GROUP).min(rows));
                full.iter()
                    .map(|(name, c)| (name.clone(), c.slice(st, en)))
                    .collect()
            })
            .collect();
        let streamed = encode_streaming(&spec, groups).unwrap();
        let batch = encode(&spec, &full).unwrap();
        assert_eq!(
            streamed, batch,
            "streaming-then-compact != batch — SSoT broken"
        );
        assert_eq!(
            decode(&spec, &streamed).unwrap(),
            full,
            "streamed bytes must decode"
        );
    }

    #[test]
    fn multi_rowgroup_roundtrips_and_is_deterministic() {
        // > ROWS_PER_GROUP forces several chunks (here 2 groups + remainder).
        let rows = ROWS_PER_GROUP + 4242;
        let spec = TableSpec {
            columns: vec![col("t", "u8"), col("e", "f4")],
            rows: rows as u64,
            row_index: Some("t".into()),
        };
        let data: TableData = vec![
            ("t".into(), ColumnData::U64((0..rows as u64).collect())),
            (
                "e".into(),
                ColumnData::F32((0..rows).map(|k| 511.0 + (k % 13) as f32).collect()),
            ),
        ];
        let blob = encode(&spec, &data).unwrap();
        assert_eq!(decode(&spec, &blob).unwrap(), data, "multi-chunk roundtrip");
        assert_eq!(
            encode(&spec, &data).unwrap(),
            blob,
            "multi-chunk non-deterministic"
        );
        // projection still works across chunks
        let ColumnData::F32(e) = &decode_column(&spec, &blob, "e").unwrap() else {
            panic!()
        };
        assert_eq!(e.len(), rows);
    }

    #[test]
    fn table_chunk_index_groups_stats_and_prunes() {
        let rows = ROWS_PER_GROUP + 4242; // 2 row-groups (one full + a remainder)
        let spec = TableSpec {
            columns: vec![col("t", "u8"), col("e", "f4")],
            rows: rows as u64,
            row_index: Some("t".into()),
        };
        let data: TableData = vec![
            ("t".into(), ColumnData::U64((0..rows as u64).collect())), // monotonic → prunable
            (
                "e".into(),
                ColumnData::F32((0..rows).map(|k| (k % 7) as f32).collect()),
            ),
        ];
        let idx = table_chunk_index(&spec, &data, "t").unwrap();
        // one entry per encoder row-group
        assert_eq!(idx.len(), rows.div_ceil(ROWS_PER_GROUP));
        // stats roll up to the whole monotonic column [0, rows)
        let agg = idx.aggregate();
        assert_eq!(agg.count, rows as u64);
        assert_eq!(agg.min, Some(0));
        assert_eq!(agg.max, Some(rows as i64 - 1));
        // 't' is sorted, so a low/high value range keeps only the first/last group
        assert_eq!(idx.prune(0, 10), vec![0]);
        let last = idx.len() - 1;
        assert_eq!(idx.prune(rows as i64 - 1, rows as i64 - 1), vec![last]);
        // root = the sub-block MMR over the per-group digests; deterministic
        assert!(idx.root().starts_with("blake3:"));
        assert_eq!(
            table_chunk_index(&spec, &data, "t").unwrap().root(),
            idx.root()
        );
        // a float column can't supply integer stats
        assert!(table_chunk_index(&spec, &data, "e").is_err());
    }

    #[test]
    fn decode_column_projection_matches_full_decode() {
        let (spec, data) = all_dtype_table(257);
        let blob = encode(&spec, &data).unwrap();
        let full = decode(&spec, &blob).unwrap();
        // every column read via projection equals the same column from the full decode
        for (name, col) in &full {
            assert_eq!(
                &decode_column(&spec, &blob, name).unwrap(),
                col,
                "projection mismatch for column {name}"
            );
        }
        assert!(decode_column(&spec, &blob, "nope").is_err());
    }

    #[test]
    fn roundtrip_every_dtype_and_deterministic() {
        let (spec, data) = all_dtype_table(257); // odd, multi-of-nothing
        let blob = encode(&spec, &data).unwrap();
        let back = decode(&spec, &blob).unwrap();
        assert_eq!(back, data, "table roundtrip mismatch");
        assert_eq!(
            encode(&spec, &data).unwrap(),
            blob,
            "table non-deterministic"
        );
    }

    /// A short-lived runtime must not poison the long-lived pooled read session.
    ///
    /// `encode`/`encode_streaming`/`decode_column` each build their own
    /// `CurrentThreadRuntime` and drop it on return, while `decode`/`decode_projected`
    /// use the per-thread pooled [`READ_RT`]. When every session was cloned from one
    /// cached template, `clone().with_handle(..)` rebound `Arc`-shared state, so the
    /// short-lived runtime's death left the pooled session dangling and this third
    /// call panicked with `Attempted to use a Handle after its runtime was dropped`.
    ///
    /// The ordering is the whole test: it only reproduces when a pooled read, a
    /// short-lived-runtime read, and another pooled read share **one process** — which
    /// is why nextest (a process per test) could never surface it, and only the
    /// `tessera-py-import` check did.
    #[test]
    fn short_lived_runtime_does_not_poison_pooled_session() {
        use tessera_core::block::table::{Column, TableSpec};
        let spec = TableSpec {
            columns: vec![Column::new("idx", "u4"), Column::new("en", "f4")],
            rows: 5,
            row_index: None,
        };
        let data: TableData = vec![
            ("idx".into(), ColumnData::U32((0..5u32).collect())),
            ("en".into(), ColumnData::F32(vec![0.5, 1.5, 2.5, 3.5, 4.5])),
        ];
        let blob = encode(&spec, &data).unwrap();

        assert_eq!(decode(&spec, &blob).unwrap(), data, "pooled decode");
        // Builds and drops its own runtime — the poisoning step.
        decode_column(&spec, &blob, "idx").unwrap();
        assert_eq!(
            decode(&spec, &blob).unwrap(),
            data,
            "pooled session poisoned by a dropped short-lived runtime"
        );
    }

    #[test]
    fn bool_and_utf8_columns_roundtrip() {
        use tessera_core::block::table::{Column, TableSpec};
        let n = 300usize;
        let flags: Vec<bool> = (0..n).map(|k| k % 3 == 0).collect();
        let origins: Vec<String> = (0..n)
            .map(|k| ["annih511", "prompt_nuclear", "other"][k % 3].to_string())
            .collect();
        let data: TableData = vec![
            ("flag".into(), ColumnData::Bool(flags.clone())),
            ("origin".into(), ColumnData::Utf8(origins.clone())),
        ];
        let spec = TableSpec {
            columns: vec![Column::new("flag", "b1"), Column::new("origin", "str")],
            rows: n as u64,
            row_index: None,
        };
        // Vortex round-trip (bit-packed bool + FSST/dict-chosen strings).
        let blob = encode(&spec, &data).unwrap();
        assert_eq!(
            decode(&spec, &blob).unwrap(),
            data,
            "bool/utf8 vortex roundtrip"
        );
        assert_eq!(
            encode(&spec, &data).unwrap(),
            blob,
            "bool/utf8 non-deterministic"
        );
        // The low-cardinality origin column compresses: encoding the *same shape* with unique
        // strings instead is materially bigger, i.e. the compressor exploited the repeats
        // (dict/FSST). Comparing against the raw string bytes would be unfair — a Vortex file
        // carries a fixed footer/metadata cost that dwarfs 300 short strings.
        let unique: Vec<String> = (0..n).map(|k| format!("origin-{k:07}")).collect();
        let hi_card: TableData = vec![
            ("flag".into(), ColumnData::Bool(flags.clone())),
            ("origin".into(), ColumnData::Utf8(unique)),
        ];
        let hi_blob = encode(&spec, &hi_card).unwrap();
        assert!(
            blob.len() < hi_blob.len(),
            "expected the repeated-string column to compress below the unique-string one: \
             {} vs {}",
            blob.len(),
            hi_blob.len()
        );
        // LE-bytes round-trip (cross-runtime path).
        let b = ColumnData::Bool(flags.clone());
        assert_eq!(
            ColumnData::from_le_bytes("b1", &b.to_le_bytes()).unwrap(),
            b
        );
        let u = ColumnData::Utf8(origins);
        assert_eq!(
            ColumnData::from_le_bytes("str", &u.to_le_bytes()).unwrap(),
            u
        );
    }

    #[test]
    fn float_bit_patterns_survive_exactly() {
        let mut f4: Vec<f32> = (0..32).map(|k| k as f32).collect();
        for (j, v) in [
            f32::NAN,
            f32::INFINITY,
            f32::NEG_INFINITY,
            -0.0,
            0.0,
            f32::MIN_POSITIVE,
            f32::MIN_POSITIVE / 2.0,
            f32::MIN,
        ]
        .into_iter()
        .enumerate()
        {
            f4[j] = v;
        }
        let mut f8: Vec<f64> = (0..32).map(|k| k as f64).collect();
        for (j, v) in [f64::NAN, f64::NEG_INFINITY, -0.0, f64::MIN_POSITIVE / 2.0]
            .into_iter()
            .enumerate()
        {
            f8[j] = v;
        }
        let data: TableData = vec![
            ("a".into(), ColumnData::F32(f4.clone())),
            ("b".into(), ColumnData::F64(f8.clone())),
        ];
        let spec = TableSpec {
            columns: vec![col("a", "f4"), col("b", "f8")],
            rows: 32,
            row_index: None,
        };
        let back = decode(&spec, &encode(&spec, &data).unwrap()).unwrap();
        let ColumnData::F32(ga) = &back[0].1 else {
            panic!()
        };
        let ColumnData::F64(gb) = &back[1].1 else {
            panic!()
        };
        for (a, b) in ga.iter().zip(&f4) {
            assert_eq!(a.to_bits(), b.to_bits(), "f32 bit pattern diverged");
        }
        for (a, b) in gb.iter().zip(&f8) {
            assert_eq!(a.to_bits(), b.to_bits(), "f64 bit pattern diverged");
        }
    }

    #[test]
    fn table_block_digest_is_over_real_payload() {
        let (spec, data) = all_dtype_table(16);
        let (block_ref, payload) = table_block("events", &spec, &data).unwrap();
        assert_eq!(
            block_ref.digest.unwrap(),
            tessera_core::hash::digest(&payload.bytes)
        );
        assert_eq!(decode(&spec, &payload.bytes).unwrap(), data);
    }

    #[test]
    fn partition_blocks_and_block_name_are_the_format_partition_ssot() {
        // The partition + naming logic is the SSoT both whole-file and streamed ingest call into
        // (so they cannot disagree on the per-block split / content_hash). Test the partition logic
        // at a small block size — independent of the production BLOCK_ROWS constant — and check the
        // small-stays-single naming invariant + the multi-block naming.

        // ── partition logic (worker/RAM-independent: depends ONLY on rows + block size)
        assert_eq!(partition_blocks(0, 4), 1, "empty → one (empty) block");
        assert_eq!(partition_blocks(1, 4), 1, "below the ceiling → one block");
        assert_eq!(partition_blocks(4, 4), 1, "exact == one block, no extra");
        assert_eq!(partition_blocks(5, 4), 2, "just-over → 2 blocks");
        assert_eq!(partition_blocks(8, 4), 2, "exact 2x → 2 blocks");
        assert_eq!(partition_blocks(9, 4), 3, "rolls over by one → 3 blocks");
        // production helper agrees with the explicit form at the real BLOCK_ROWS.
        assert_eq!(block_count(BLOCK_ROWS as u64), 1);
        assert_eq!(block_count((BLOCK_ROWS as u64) + 1), 2);

        // ── naming: small-stays-single (no NNNN suffix), multi-block uses zero-padded 4-digit suffix
        assert_eq!(
            block_name("events", 0, 0),
            "events",
            "empty product → bare name"
        );
        assert_eq!(
            block_name("events", 0, 1),
            "events",
            "single block → bare name"
        );
        assert_eq!(block_name("events", 0, 2), "events_0000");
        assert_eq!(block_name("events", 7, 8), "events_0007");
        assert_eq!(block_name("events", 1234, 9999), "events_1234");
    }

    #[test]
    fn rejects_dtype_name_and_len_mismatches() {
        let spec = TableSpec {
            columns: vec![col("t", "u8"), col("e", "f4")],
            rows: 4,
            row_index: None,
        };
        // wrong dtype for column 'e'
        let bad_dtype: TableData = vec![
            ("t".into(), ColumnData::U64(vec![0; 4])),
            ("e".into(), ColumnData::I32(vec![0; 4])),
        ];
        assert!(matches!(encode(&spec, &bad_dtype), Err(Error::Codec(_))));
        // wrong length
        let bad_len: TableData = vec![
            ("t".into(), ColumnData::U64(vec![0; 4])),
            ("e".into(), ColumnData::F32(vec![0.0; 3])),
        ];
        assert!(matches!(encode(&spec, &bad_len), Err(Error::Codec(_))));
        // wrong name
        let bad_name: TableData = vec![
            ("x".into(), ColumnData::U64(vec![0; 4])),
            ("e".into(), ColumnData::F32(vec![0.0; 4])),
        ];
        assert!(matches!(encode(&spec, &bad_name), Err(Error::Codec(_))));
    }
}
