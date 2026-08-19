# ADR-0056 — Generic ingest: the normalise-vs-preserve ladder and the Arrow→Tessera type boundary

**Status:** Proposed (2026-08-19, spike #386). Extends **ADR-0025** (ingest model — normalise at the
door, lossless, provenance-rooted) and **ADR-0035** (declarative spec engine / closed-backend
dispatch). Bounded above by **ADR-0038** (blob = the opaque preservation tier) and below by
**ADR-0024** (table payload = flat Vortex columns) / **ADR-0023** (array payload = Zarr v3 + pcodec).
Touches **ADR-0046** (time model — the epoch gap), **ADR-0040** (sensitivity tiers), **ADR-0030**
(spatial referencing), **ADR-0042** (sealed vs `aux/`), **ADR-0020** (identity/determinism).
Follow-ups: [#393](https://github.com/vig-os/tessera/issues/393) (directory-shaped sources),
[#394](https://github.com/vig-os/tessera/issues/394) (TIFF/OME-TIFF).

> Design-only ADR from a five-lens fresh-context spike (Arrow/Parquet internals · scientific
> practitioner · CLI + maintenance burden · reproducibility/archival integrity · FAIR governance).
> No ingest code was written; §10 is the landing plan.

## Context — the gap between the two things we can already do

Tessera has two ways to take in foreign data, and nothing between them:

- **`tessera ingest blob`** (ADR-0038) — the **FAIR zip**. Arbitrary bytes wrapped bit-faithfully in a
  sealed `.tsra`: identity, seal, provenance, versioning, signing, OCI/cloud distribution. The
  payload is a black box — no codec, no projection, no ROI, no field-level integrity, not queryable.
  FAIR **F/A/R**, but not **I**.
- **`tessera ingest <vendor>`** (ADR-0025) — DICOM, GE-HDF5, NIfTI, raw. **Normalises** the source
  into Tessera primitives, so you also get compression, projection/ROI, and cross-arch-deterministic
  content-addressed bytes.

A scientist who is not holding a vendor acquisition file — who has a Parquet table, a `.npy` volume,
a CSV — falls off the second path onto the first and gets a sealed black box. The AX onboarding audit
(#390) scored exactly this: read UX 4.5/5, **write-your-own-data 2/5**. The value of the format is in
the normalising path; today only vendors can reach it.

This ADR extends the normalising path to generic formats. It does **not** replace `blob` — blob stays
the explicit, honest fallback, and this ADR makes falling back to it *louder and better signposted*
rather than rarer.

## The ladder, stated once

| Tier | Verb | What you get | What you give up |
| --- | --- | --- | --- |
| **Preserve** | `ingest blob` | bit-faithful bytes · seal · provenance · signing · distribution | interoperability, query, ROI, per-field integrity |
| **Normalise** | `ingest table` / `ingest array` | all of the above **plus** codecs, projection, ROI, chunk-level integrity, cross-arch determinism | source-format quirks are dropped at the door, by design |

The ladder is a **ratchet, not a fork**: everything the preserve tier gives, the normalise tier also
gives. The only question at the door is whether the source's *logical values* can be carried into a
primitive without lying about them. When they cannot, the answer is blob — and saying so clearly is a
feature.

## §1 — Route by shape; never auto-decide semantics

The premise of the format is that the primitive follows the **shape of the data**, not the container
it arrived in: dense N-D numeric grid → array; record/event table → table. A Parquet file full of
flattened volumes is still volumes; an HDF5 2-D dataset with a header row is still a table.

But **the bytes cannot tell you what the data means.** A 2-D block of numbers is an image or an
N-row × M-column table, and nothing in the file distinguishes them. Therefore:

1. **Default = honour the source's declared structural shape.** A columnar container → table; an N-D
   dense container → array. This is a *structural* reading, not a semantic guess.
2. **`--as table|array` overrides it**, for when the source misrepresents the data.
3. **Advisories may flag a suspected mismatch; they never decide.** No heuristic silently changes the
   primitive. (§9.)

The "previous format is misused" case is a first-class feature. People dump flattened volumes into
Parquet rows and tables into HDF5 2-D datasets. Ingest must not *perpetuate* the misuse silently —
this is where Tessera adds judgment at the door — but it also must not *correct* it unilaterally.

## §2 — The Arrow→Tessera type boundary: three lanes, and there is no lossy lane

Ingest is a **logical re-encode**: `source → Arrow/ndarray → Tessera columns/array → primitive
encode → seal`. There is no byte-level Parquet→Vortex mapping and we do not want one — a byte copy
would import the source writer's non-deterministic encoding and defeat the seal. Re-encoding under
our own deterministic codecs *is* the product.

The boundary is `ColumnData` (`tessera/crates/tessera-io/src/table.rs:66`): flat `I8…I64`, `U8…U64`,
`F32`, `F64`, `Bool`, `Utf8`, plus a non-nestable `Nullable` wrapper. No List, Struct, Map, Decimal,
Date, Timestamp, Dictionary.

**The spike rejected the originally-proposed "lossy-map-with-warning" tier.** ADR-0025 says ingest is
lossless; a warning printed to a terminal that scrolls away does not travel with the artifact, and a
seal over silently-degraded values asserts under a signature that those values are the truth. A
warning is not a record. The three lanes are:

- **Clean** — bit-faithful, no transformation.
- **Lossless-with-recorded-transform** — a reversible transformation whose parameters are written
  **inside the seal** (§6), so the artifact carries its own recovery instructions.
- **Reject** — a hard error naming the column, the reason, and the exact escape hatch.

| Arrow type | Lane | Tessera target | Recorded transform / reason |
| --- | --- | --- | --- |
| `Int8…Int64`, `UInt8…UInt64` | clean | `I8…I64`, `U8…U64` | — |
| `Float32`, `Float64` | clean | `F32`, `F64` | NaN payload canonicalised (§5 H4) |
| `Boolean` | clean | `Bool` | iterate `len` bits, never trailing byte padding |
| `Utf8`, `LargeUtf8`, `Utf8View` | clean | `Utf8` | view is a runtime encoding; materialise owned |
| `Null` | clean | `Nullable{I8, validity=all-false}` | — |
| `RunEndEncoded` | clean | decode through to values | run-encoding is a source detail |
| `Float16` | recorded | `F32` | `f16_widen` — exact for values; NaN payloads canonicalised |
| `Decimal128(p≤18, s)` | recorded | `I64` + `Column.scale = 10⁻ˢ` | `decimal_fixed_point` — exactly what `scale` exists for |
| `Date32` | recorded | `I32` + `unit="d"` + epoch | `epoch_anchor` (§6, needs `Column.referencing`) |
| `Date64` | recorded | `I64` + `unit="ms"` + epoch | `epoch_anchor` |
| `Time32/Time64` | recorded | `I32`/`I64` + `unit="s"` + `scale` | time-of-day; no epoch |
| `Duration` | recorded | `I64` + `unit="s"` + `scale` | elapsed, monotonic (ADR-0046) |
| `Timestamp(unit, None)` | recorded | `I64` ticks + `scale` + `epoch:unix` | `epoch_anchor` — ticks, never floats |
| `Timestamp(unit, Some(tz))` | recorded | `I64` UTC ticks + `epoch:unix` | `tz_to_utc{from}` — **lossless only because the source zone is sealed** |
| `Dictionary` / categorical | recorded | `Utf8` (values, not codes) | `dictionary_materialised` — see below |
| `FixedSizeList<scalar, N≤8>` | recorded | `N` columns `name.0…name.N-1` | `fixed_list_expand{n}` — schema-fixed width |
| `Decimal128(p>18)`, `Decimal256` | reject | — | no lossless integer carrier |
| `Binary`, `LargeBinary`, `FixedSizeBinary` | reject | — | base64-in-Utf8 lies about the type and destroys compression |
| `Interval(*)` | reject | — | encodes calendar arithmetic Tessera does not preserve |
| `List`, `LargeList`, `Map`, `Union` | reject | — | §3 |
| `Struct` | flatten | dotted columns | §3 |
| Extension types | best-effort | underlying storage type | `Column.description = "[arrow-ext:<name>]"` |

Two mappings deserve their reasoning stated, because both look like losses and are not:

- **Dictionary → values, dropping the source codes.** Preserving the writer's integer codes would
  import the writer's *dictionary order* into `content_hash` — and pandas' `Categorical` order is
  insertion-time, so the same logical data from pandas, polars and Spark would seal to three
  different hashes. Vortex re-derives FSST/dictionary encoding for low-cardinality repeats on the far
  side (`table.rs:80-82`), so the compression the source thought it was preserving is reclaimed.
- **Decimal → `I64` + `scale`, never `F64`.** Decimal→float is lossy for exactly the accounting-like
  data that uses decimals, and the cast is FMA-sensitive across architectures (§5 H3).

Rejections are errors with a next command, never bare failures. Literal forms:

```text
error: column 'payload' has type binary; Tessera tables carry no opaque byte columns
       (base64-in-utf8 would lie about the type and defeat the codec).
  drop it:      tessera ingest table data.parquet --exclude payload
  keep bytes:   tessera ingest blob data.parquet   # bit-faithful, opaque payload (ADR-0038)

error: column 'amount' is decimal128(28,6); no lossless integer carrier exists above precision 18.
  declare intent: --column amount:i64@1e-6   # asserts the values fit; recorded in the seal
  or:             tessera ingest blob data.parquet
```

## §3 — Nested sources: flatten structs, reject lists and maps

"Flatten if trivial, else blob" hides the actual rule, so pin it:

- **`struct<a: T, b: U>` → columns `parent.a`, `parent.b`, recursively.** A struct flatten is a
  **renaming**, not a semantic change; pandas, polars and DuckDB already present nested Parquet this
  way. Name collisions with an existing top-level column are an **error**, not a silent suffix.
- **`list<T>` / `map<K,V>` → reject.** `TableSpec.rows` is a scalar; a list column implies a
  per-row variable count. Exploding one row into N destroys the source-row identity a reader uses to
  join sibling columns — that is a semantic transformation, and §1 forbids performing one silently.
  An explicit `--explode <col>` opt-in is the escape hatch, not the default.
- **Never a bare hard error.** Every rejection names the column and offers `--explode` / `--exclude`
  / `ingest blob`.

Rejected alternative — **JSON-encoding a list column into `Utf8`**: defeats every codec, defeats
projection, and misrepresents the type. Rejected alternative — **reject-to-blob for structs**: loses
because the flatten is well-worn ground with no information loss; bailing would be gratuitous.

## §4 — One verb axis: the primitive. Vendor verbs are deprecated into recipes

The CLI currently names verbs on **two** axes: by source (`dicom`, `dicom-series`, `ge-hdf5`,
`nifti`) and by contract/tier (`raw`, `blob`). Adding `table` and `array` — named by *primitive* —
would make three. That guarantees the permanent FAQ "why does `nifti` exist when
`ingest array scan.nii` also works?".

**Decision: the primitive axis is the only axis.** The user-facing surface is exactly three verbs,
matching the three block kinds:

```text
tessera ingest table <FILE>  [--from parquet|arrow|ge-hdf5|csv]  [--as …]
tessera ingest array <FILE>  [--from npy|nifti|dicom|dicom-series|raw|tiff]  [--as …]
tessera ingest blob  <FILE>
```

Vendor decoding does not disappear — it stops being a *verb* and becomes a **`--from` backend** plus
its scoped flags (`--dataset events_2p --quantize`, `--deidentify`, `--rescale-mode global-int16`,
`--shape 256x256x128 --dtype u2`). `--from` is sniffed from magic bytes when unambiguous and required
when not. `raw` disappears entirely: it was always a headerless `array`.

The existing vendor verbs are **deprecated, then removed**: hidden `#[command(hide = true)]` aliases
for one release cycle, with a stderr notice naming the replacement invocation, then deleted. Vendor
*ergonomics* — the muscle memory of `tessera ingest dicom-series …` — is re-delivered as **wrapper
recipes** in the ingest cookbook (#389): thin shell scripts and `--spec` TOML templates that call the
primitive verbs. A recipe is a better home for vendor convenience than a built-in verb, because it is
editable by the user who has the vendor's next quirk, and it does not grow the surface every
maintainer must carry forever.

`FormatOptions` (`tessera/crates/tessera-ingest/src/spec.rs:137`) tracks the same shape, so the CLI
`--from <name>` and the TOML `from = "<name>"` are one string set and one grep locates every backend.

Rejected alternative — **keep vendor verbs as first-class forever**: pre-1.0 is the only moment this
is cheap, and two naming axes is a defect that compounds with every new format.

## §5 — Determinism: the gate is the source decode, not our encode

Tessera's own codecs are already cross-arch byte-deterministic and gated by the conformance corpus.
Generic ingest moves the risk **upstream**: two arrow-rs versions can hand the primitive two
different `ColumnData` for the same Parquet file, and both will then encode deterministically to two
different `content_hash`es. **The ingest determinism gate is the `arrow → primitive` canonicalisation
step.** Naming it is half the fix.

| # | Hazard | Likelihood × radius | Rule |
| --- | --- | --- | --- |
| **H1** | Timezone/timestamp normalisation — **tzdb is a filesystem dependency** (`chrono-tz` compiled-in vs host `/usr/share/zoneinfo`); two hosts, two `i64`s | high × fatal | strip tz, take **raw** ticks, apply our own scale; never trust a decoder-canonicalised value |
| **H2** | Lossy tile codecs — JPEG-in-TIFF, JPEG-2000, WebP differ across libjpeg / libjpeg-turbo / mozjpeg (IDCT rounding, chroma upsampling) | high × fatal | **reject from the normalising path**; route to `blob` (#394) |
| **H3** | Float parsing (`strtod`/`lexical`) and decimal→float casts (FMA-sensitive) | high × fatal | CSV deferred (§8); decimal→float **banned** (§2) |
| **H4** | `NaN` payload bits and `-0.0` — arrow-rs preserves the source bit pattern; producers differ | medium × fatal | canonicalise every NaN to the quiet default at the boundary |
| **H5** | Values **under** a null — arrow hands over whatever the writer left there | medium × fatal | zero at the `arrow → ColumnData` boundary, not only at encode (see below) |
| **H6** | NPY/raw endianness (`>f8` vs `<f8`) — a naive `cast_slice` is silently wrong on one arch | low × fatal | decode and normalise to native LE; test both twins |
| **H7** | SIMD-dispatched decode paths | medium × float-only | covered by H3/H4 canonicalisation |
| **H8** | Locale (`LC_NUMERIC=de_DE` reading `1,5` as 1.5) | low × medium | `LC_ALL=C` for the decode |
| **H9** | arrow-rs / parquet minor bumps changing decoded values | medium × fatal | `=` version pins + §6 sealed decoder id |

**H5 deserves its own paragraph** because it interacts with a documented invariant. `ColumnData::Nullable`
normalises masked slots to the dtype default on **encode** (`table.rs:98-103`) so that `content_hash`
is independent of whatever sat under a null. That is correct and stays. But a foreign source *does*
carry bytes under its nulls, so the normalisation must be pulled forward to the ingest boundary —
otherwise any code inspecting `values` before encode sees producer noise. The consequence must also
be stated plainly in the artifact and the docs: **null semantics after ingest are Tessera's, not the
source's.** A Parquet writer that stored `NaN` under a nullable `f64` slot will read back `0.0` with
`validity=false`. This is not byte-identity with the source's raw values buffer, and §6's transform
record says so.

**The gate.** Extend the conformance corpus with `ingest_*` fixtures whose *source* files are
**generated at build time** by a pinned writer (do not commit binary Parquet/TIFF blobs — they bloat
the repo and force golden churn on unrelated dep bumps); commit only the generator descriptor and the
resulting golden `content_hash`/`manifest_hash`:

- `ingest_parquet_scalars` — every accepted scalar type, including `timestamp(us, UTC)`,
  `timestamp(us, "America/New_York")`, `decimal128(18,4)`, `date32`.
- `ingest_parquet_producers` — the *same logical table* written by pyarrow, polars and DuckDB
  `COPY`; all three must seal to **one** `content_hash`. This is the test that actually catches
  dictionary-order and null-padding leakage.
- `ingest_parquet_nulls` — `[Some(1), None, Some(3)]` with deliberate garbage under the null.
- `ingest_npy_endianness` — a `>f8` file and its `<f8` twin must seal identically.
- `ingest_nifti_scl` — non-unit `scl_slope`.

Tests: `ingest_corpus_hashes_match_goldens` plus the cross-arch run on the existing `ubuntu-24.04-arm`
CI matrix. Compare `content_hash` + `manifest_hash`, not decoded values — the seal is the claim.
Pin `arrow` and `parquet` with `=` (not `^`), and treat a bump as a deliberate corpus-regeneration
commit, the same discipline as the ALP-exclusion pin.

## §6 — What the seal must record (four additive format fields)

All four are `skip_serializing_if`-guarded, so existing manifests serialise byte-identically and the
committed corpus needs no regeneration — the same trick `Column.nullable` already uses
(`tessera/crates/tessera-core/src/block/table.rs:41-44`).

1. **`Column.referencing: Option<Referenced>`** — the epoch slot. `Column` today carries `unit` and
   `scale` but nothing that anchors an epoch, so an ingested Arrow timestamp would land as
   `i64 + unit="s" + scale=1e-6` **with the epoch dropped** — indistinguishable from a duration, and
   a live violation of ADR-0046 §2's ticks-plus-epoch model. This is the smallest change that keeps
   the time model truthful, and it also closes the pre-existing listmode `t_ms` semantics gap.
2. **`ingest_decoder` inside the seal** — decoder name + version + relevant features (e.g.
   `"arrow-rs 58.3.0"`). Without it, re-ingesting an unchanged file after `cargo update` produces a
   different `content_hash` and no one can distinguish decoder drift from changed data. Recording it
   makes two seals from two decoder versions *honestly different products* rather than a silent
   contradiction. The cost is stated openly: `content_hash` becomes a function of the decoder
   version, which is the truth it was always implicitly a function of.
3. **`ingest_transform: [{name, params}]`** — the §2 recorded-transform list (`tz_to_utc{from}`,
   `decimal_fixed_point{scale}`, `f16_widen`, `dictionary_materialised`, `fixed_list_expand{n}`,
   `null_slot_normalisation`, `struct_flatten`). This is what makes the middle lane honest: the
   artifact carries its own recovery instructions instead of relying on a warning that scrolled away.
4. **`Column.sensitivity: Sensitivity` + a fifth variant `Sensitivity::Unknown`** — §7.

**Why inside the seal and not `aux/provenance.json`.** ADR-0042 puts wall-clock and host facts
outside the seal precisely so re-ingest is byte-identical; that is right for `ingested_at`. It is
wrong for these four, because each of them **changes what the values mean**. A reader who cannot see
the epoch, the decoder, or the transform list cannot reconstruct the source's semantics, and
FAIR-Reusable collapses. Transitive dependency versions, decode-time diagnostics and per-column
inference statistics stay in `aux/` — audit-useful, not meaning-bearing.

## §7 — Schema, sensitivity, and the laundering rule

**Two new permissive builtin schemas, `table` and `array`**, mirroring how `blob` is a builtin
permissive schema. Every field is `recommended`, never `required` — the blob lesson applies: the door
stays frictionless (preserve now, label later) and the warn tier does the FAIR nudging.

```rust
ProductSchema {
    fields: vec![
        FieldSpec::recommended("study",
            "Study / cohort / experiment this table belongs to (FAIR grouping)", "string"),
        FieldSpec::recommended("source_format",
            "Source format normalised at ingest (\"parquet\" | \"arrow\" | \"csv\" | …)", "string"),
        FieldSpec::recommended("ingest_decoder",
            "Decoder that produced this block (name + version)", "string"),
    ],
    blocks: vec![one("data", Some(Table),
        "Normalised flat columnar table (Vortex-encoded at seal)")],
    ..schema("table", "1.0",
        "A generically-ingested flat table — structural preservation, semantics still to be attached.")
},
```

`array` is the same shape with `Some(Array)` and `"npy" | "nifti" | "tiff" | …`.

**The semantic-nakedness problem, and why it is already solvable.** A Parquet file has column names
and dtypes but no descriptions, units or vocabularies — while `FieldSpec` demands exactly those, and
that is the FAIR-Reusable pitch. A generically-ingested table that leaves them empty is a Parquet
file with a seal on it. But the mechanism already exists: `Column` carries `short_name`,
`description`, `unit` and `scale`, and the GE-HDF5 path already populates them from an embedded TOML
dictionary. Generalise that, and ship **both** doors in P1:

- **at ingest** — `--column-meta cols.toml` (`[<col>] short_name= description= unit= scale=
  sensitivity=`), landing **inside the seal**;
- **after the fact** — the existing content-addressed metadata-edit path (`tessera commit --set …`),
  one new object, lineage preserved.

Deferring column annotation to "operator homework later" is the failure mode that turns generic
ingest into a wrapper. It ships with the door.

**Sensitivity: `Public` is the wrong default here.** Vendor paths either never see PHI (GE listmode =
scan events) or classify at the door (DICOM → PS3.15 tiers). Generic ingest has neither defence, and
`Sensitivity::Public` — "safe in clear" — would be a false assertion sealed permanently into a CSV of
patient records. Add **`Sensitivity::Unknown`** (serde default stays `Public`, so every existing
schema is unchanged) and **`Column.sensitivity`**; generic ingest stamps `Unknown` on every column no
`--column-meta` classified. A future `verify --require-classified` then gives operators a one-line
gate before share/push.

On a suspect column name, ingest prints once, to stderr, with the fix:

```text
warn: column 'patient_id' matches an identifying-name pattern (MRN / patient id / name / DOB /
      accession / UID) and no --column-meta gave it a tier; stamped: unknown
      classify before sharing:
        tessera ingest analyze data.parquet          # full per-column tier report
        tessera commit --set data.spec.columns.3.sensitivity=identifying
```

**The laundering rule.** The seal binds a schema's *promises*, not the pipeline's fulfilment of them.
`tessera ingest table events.csv --from csv --schema listmode` would otherwise produce a `.tsra`
byte-indistinguishable from a real vendor listmode ingest, carrying PS3.15 `Identifying` tiers that
**no classification pass ever validated** — and every downstream consumer of
`manifest.schema.fields[].sensitivity` would trust them. That is the self-describing-artifact thesis
turned into a weapon. So: **a manifest whose `ingest_decoder` is a generic backend must declare a
product in `{table, array, blob}`**, unless the operator supplies an explicit
`--classification-ack` (an ADR-0037 signature over the schema + column-tier tuple). No ack, no vendor
schema. Retrofitting this after the first such artifact ships would leave those seals permanently
ambiguous, which is why it belongs in this ADR rather than a later one.

## §8 — CSV is deferred, and that is a determinism decision

CSV needs delimiter, header, per-column dtype and null-token inference. Sample-based inference is
**anti-deterministic by construction**: the inferred schema depends on which rows landed in the
sample, so the same file can seal to two different products. That is the one property Tessera cannot
trade. P1 refuses `.csv` with a conversion path rather than guessing:

```text
error: CSV carries no schema and Tessera does not infer one (an inferred schema is not
       reproducible, and the seal must be). Convert first:
         duckdb -c "COPY (SELECT * FROM 'input.csv') TO 'input.parquet' (FORMAT parquet)"
         tessera ingest table input.parquet
       Native CSV with an explicit schema is tracked in #386 phase 2.
```

When CSV does land (P2) it is **inference-free by default**: a single pass, `--schema schema.toml` or
repeatable `--column name:dtype` required, and if any `--column` is given, no other column is
inferred either — no mixed mode. Optional inference stays opt-in behind an explicit flag and records
`ingest_transform: [{name: "csv_inferred_schema"}]` in the seal.

## §9 — `analyze` suggests, and only when there is a judgment to make

`tessera ingest analyze <FILE>` is a **separate verb**, read-only. Its contract: print the recommended
primitive, the reason, and **the exact command to run**. If a code path ever emits a warning without a
runnable next command, that path is a bug.

```text
$ tessera ingest analyze study.parquet
shape: 4096 rows × 12 cols; column `voxels` = fixed_size_list<float32>[262144]
recommendation: array (the row-set looks like flattened volumes)
run:  tessera ingest array study.parquet --column voxels --shape 64x64x64
also: tessera ingest table study.parquet   # if the row semantics are real
```

Heuristics worth having (each has a real hit-rate in practice): an HDF5 2-D dataset or compound whose
column dtypes vary; a Parquet whose columns are uniformly one dtype and index like a grid; a NumPy
**structured/record dtype** (which is a table, not an array — §1 in its purest form); an `.npz` whose
members are the auto-generated `arr_0`/`arr_1` names; a lone monotonically-increasing `i64` column;
column names containing `.`, spaces or unicode confusables. Deliberately **not** flagged: dtype-width
choices, the presence of nulls, file size.

**Loudness.** `ingest` itself does not run the heuristics. It prints only for routing decisions that
*drop or transform* data (§2 recorded transforms, §3 flattening, §7 suspect column names), once, to
stderr, and stays silent when stdout is not a TTY — someone running `find … -exec tessera ingest …`
across 5000 files must not scroll 30k lines of advice. An advisory **never** gates an ingest.

Rejected alternative — **`tessera ingest <FILE>` with auto-detected format and primitive** (the
originally-proposed phase 3). Extension sniffing trains users into a habit that breaks the moment the
extension lies (`.dat`, `.bin`, a `.parquet` that is really Feather), and every file-type
misdetection becomes a Tessera bug. `analyze` already prints the exact command — same ergonomics,
none of the magic. Dropped from the plan.

## §10 — Directory sources: the same shape rule, one level up

Every source→primitive row above assumes a **single file**. Real datasets are directory-shaped: BIDS
trees, DICOM study folders, `run.ap.bin` + `run.ap.meta` (where the `.meta` *is* the header the
`.bin` lacks), `experiment/ch0/z0000.tif …`, `arr_000.npy … arr_999.npy`. The `--spec` engine can
already build collections; the user-facing routing cannot, so today the first real ingest is "write
me a TOML spec".

The §1 rule generalises without modification — apply it to the **layout's** shape:

- Directory members that together form **one dense N-D grid** (a single DICOM series, a z-stack, a
  numbered `.npy` sequence) → **one array product**, stacked into a single Zarr block. This is what
  `dicom-series` already does; the rule simply names it.
- Directory members that are **independent acquisitions** (several scans, several subjects) → a
  **collection** of `.tsra`, one product per acquisition (ADR-0033 / ADR-0049).

The *semantics* are decided here; the **detection heuristics** (BIDS recognition, sidecar pairing,
series grouping, numbered-sequence ordering) are a large design surface of their own and are scoped
out to **#393**. Detection must *emit* a `--spec` TOML rather than bypass it, so the declarative path
stays the single source of truth (ADR-0035).

## §11 — Format coverage in the first landing

| Source | Primitive | Verdict |
| --- | --- | --- |
| Parquet / Arrow / Feather | table | **P1** — self-describing dtypes, no guessing |
| NumPy `.npy` | array | **P1** — shape + dtype explicit. Fortran-order transposed to C at the door (recorded); **structured/record dtype routes to `table`**; object/pickled dtype rejects to blob (never unpickle at ingest); big-endian normalised to native |
| NumPy `.npz` | collection | **P1** — one array product per member; warn on auto-generated `arr_N` names |
| NIfTI `.nii[.gz]` | array | **already built** — see the gaps below |
| CSV / TSV | table | **P2**, inference-free (§8) |
| TIFF / OME-TIFF | array | **cut from P1** → #394 |
| anything else | blob | the honest fallback, signposted by `analyze` |

**NIfTI is largely already answered** — `tessera/crates/tessera-ingest/src/nifti.rs` reads the sform,
reorders it to `[z,y,x]`, converts RAS+→LPS and carries `scl_slope`/`scl_inter`, which is ADR-0030
§1/§6 compliant. Four real gaps remain, and they are correctness bugs rather than design questions:

1. **`.nii.gz` is unsupported** — and it is the majority of NIfTI on disk. Currently fails with a
   confusing `sizeof_hdr != 348`.
2. **qform is ignored.** Files with `sform_code == 0` and `qform_code > 0` (older SPM/FSL outputs)
   carry geometry in the quaternion; ignoring it silently drops the frame from an array that *has*
   one. Precedence must be sform, else qform, else no `world_frame`.
3. **`world_frame.space` is hard-coded `"scanner"`** — the `sform_code`/`qform_code` value
   (scanner=1, aligned=2, talairach=3, mni=4) must map onto it, and which code was used recorded.
4. **4-D/5-D volumes are silently truncated to 3-D**, dropping fMRI time and DWI directions — the
   second-most-common neuroimaging shape. Either declare `[t,z,y,x]` with the time axis carried via
   ADR-0032 `axis_referencing`, or hard-error. Silently losing volumes is not an option.

## §12 — Dependency and feature layout: gate the readers, but not because of bloat

Measured against the workspace as it stands (729 packages in `Cargo.lock`):

- **`arrow` is already in the tree** — 14 `arrow*` crates arrive via Vortex/DataFusion, so the Arrow
  half of Parquet ingest costs **zero new dependencies**. `parquet` itself is absent and brings
  `thrift`, `snap` and `brotli` (`lz4_flex`, `flate2` and `twox-hash` are already present).
- **wasm is safe by construction** — `tessera-wasm` depends only on `tessera-core`, and only
  `tessera-cli` depends on `tessera-ingest`. No decoder can reach the wasm graph or the pure-abi3
  Python wheel. A `cargo tree` assertion in the `wasm-core` check keeps that true rather than
  assumed.
- **The existing importers are not gated at all** — `dicom` and `hdf5-metno` are unconditional
  dependencies of `tessera-ingest`; the `static-hdf5` feature only switches how libhdf5 *links*, not
  whether it compiles. They are also, by a wide margin, the expensive ones.

So the new readers do not meaningfully bloat anything, and "bloat" is the wrong reason to gate them.
They are gated anyway, for three reasons that do hold:

1. **CI cost** — `--all-features` clippy is a gate, and the x86_64 flake check already runs ~90 min
   with the static-HDF5 build in it. Every ungated reader is unconditionally in that build.
2. **Supply-chain surface** — an embedder who never ingests Parquet should not have to audit
   `thrift`/`snap`/`brotli` under `cargo deny`.
3. **The determinism story (the load-bearing one)** — §6 seals `ingest_decoder`. A feature-gated
   decoder makes *which decoders could have produced this artifact* a **build-time fact** rather than
   a runtime accident, which is exactly the property the sealed decoder id is trying to buy.

```toml
[features]
default        = ["ingest-parquet", "ingest-npy"]   # everything P1 ships, on
ingest-parquet = ["dep:parquet", "dep:arrow"]       # arrow already in-tree via Vortex
ingest-npy     = []                                 # in-tree header parser; no ndarray dep
ingest-csv     = ["dep:arrow", "dep:csv"]           # P2 (§8)
ingest-tiff    = ["dep:tiff"]                       # #394
```

Two constraints on the layout:

- **A feature may decide whether a format is *readable*; it may never change how one *encodes*.**
  Building without `ingest-parquet` must produce a clean "unsupported source format" error — never
  different bytes for the same input. Feature selection is outside the sealed byte-path, the same way
  `static-hdf5` is (HDF5 is read-only input and cannot move a `content_hash`).
- **Defaults on for everything P1 ships.** A downloaded `tessera` that cannot read Parquet is a bad
  binary; the gates exist for embedders and CI, not for end users. Release channels enable the full
  set.

`ndarray-npy` is deliberately **not** taken: NPY is a header parse plus a memcpy, and the crate would
drag `ndarray` into the tree for one format. Retro-gating the existing `dicom` / `hdf5-metno`
dependencies is out of scope here but is the larger prize, and is named for a future pass.

## Alternatives considered and rejected

- **A byte-level Parquet→Vortex mapping.** Would import the source writer's non-deterministic
  encoding into `content_hash` and defeat the seal. There is no such mapping and we do not want one.
- **A "lossy-map-with-warning" tier** (the issue's original framing). A warning does not travel with
  the artifact; a seal over degraded values asserts they are the truth. Replaced by the
  recorded-transform lane (§2/§6) plus honest rejections.
- **Preserving source dictionary codes + a vocabulary sidecar.** Imports producer-specific dictionary
  ordering into the hash; the same table from three writers would seal three ways.
- **Auto-exploding list columns.** Changes row cardinality and destroys source-row identity — a
  semantic transformation, which §1 forbids doing silently.
- **`tessera ingest <FILE>` full auto-detect.** Magic that breaks when extensions lie; `analyze`
  delivers the same ergonomics with none of the failure modes.
- **Keeping vendor verbs as first-class CLI citizens.** Locks in a second naming axis forever;
  pre-1.0 is the only cheap moment to collapse it.
- **Recording the decoder version outside the seal** (in `aux/provenance.json`). Leaves
  `content_hash` silently dependent on an unrecorded input.
- **Defaulting generic-ingest columns to `Sensitivity::Public`.** Seals a false safety claim, and
  seals are forever.
- **TIFF in P1.** Two independent reviewers flagged it; the pyramid is the point for whole-slide
  imaging, and JPEG-in-TIFF decode is not bit-reproducible across libjpeg variants (§5 H2).

## Consequences

- The normalising path opens to non-vendor data; the AX write-your-own-data gap (#390) gets a real
  answer rather than "wrap it in a blob".
- Four additive, corpus-neutral format fields land in `tessera-core` (§6). They are additive by
  construction, but they are still format surface — the reason each earns its place is stated inline.
- `content_hash` becomes explicitly a function of the decoder version. This is a clarification of
  reality, not a new dependency, but it means dependency bumps become deliberate corpus events.
- The CLI shrinks to three ingest verbs and grows a `--from` dimension; vendor verbs go through a
  deprecation cycle and vendor ergonomics move to cookbook recipes (#389).
- `blob` gets *more* traffic, not less, and that is intended: every rejection routes there with a
  clear reason, which is a better outcome than a quiet lossy import.
- Cross-arch CI gains ingest fixtures; the generated-not-committed approach keeps repo weight flat.

## Landing plan

- **P1 — self-describing formats, primitive verbs.** `ingest table --from parquet|arrow`;
  `ingest array --from npy|npz|nifti|dicom|dicom-series|raw`; the §2 type map with recorded
  transforms; §3 struct-flatten; `--as`, `--exclude`, `--column name:dtype`, `--schema`,
  `--column-meta`; the four §6 format fields; the §5 canonicalisation rules and corpus fixtures;
  vendor verbs hidden-aliased. Tests: value round-trip, three-producer hash equality, nested→reject,
  null-slot normalisation, cross-arch determinism.
- **P2 — judgment and CSV.** `ingest analyze`; inference-free CSV with `--schema`/`--column`;
  `verify --require-classified`; the §7 laundering rule enforced in `schema.validate()`.
- **P3 — the NIfTI correctness gaps** (§11): `.nii.gz`, qform precedence, `space` from the sform/qform
  code, 4-D/5-D.
- **Out of scope, tracked separately:** directory-shaped sources (#393), TIFF/OME-TIFF with pyramid
  carry-through (#394), vendor-verb removal after the deprecation cycle, ingest cookbook recipes
  (#389).

## Open gaps this ADR does not close

- Whether `--classification-ack` (§7) should be a signature or a simpler attestation — the mechanism
  is pinned to ADR-0037 keys, the ergonomics are not designed.
- Cross-*version* determinism (as opposed to cross-arch) remains unproven for ingest, as it does for
  the format generally.
- Extension-type handling is best-effort; named handling for `arrow.uuid` / `arrow.json` is unspecified.
