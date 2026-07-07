# ADR-0052 — Generation provenance (generic bag) + seal-time identity inheritance

Status: **Proposed** · Relates: ADR-0025 (ingest, provenance-rooted) · ADR-0033 (raw→derived) ·
ADR-0042 (aux sidecars, the seal/wall-clock line) · ADR-0045 (units/quantities as derived products) ·
ADR-0046 (time model) · ADR-0049/0050 (collections, schema-enforced rules) · #324 · #342 · #305 ·
#310 · #331. Found during the DUPLET first-user run (two independent fresh-context FAIR reviews).

## Context — a single derived `.tsra` cannot answer "what is this?" or "how was it made?"

The DUPLET conversion produced correct, integrity-sound products, but a scientist handed **one**
derived `.tsra` in isolation could recover neither its identity nor its recipe:

1. **Identity is stranded on the parent.** The raw `.dat` blob carries 16 acquisition fields
   (`patient_id=ANON9297`, `exam=9297`, `start_time`, `acq_mode_config`, the cal-file names, …); the
   DICOM recon carries full `study_instance_uid`/`modality`/`manufacturer`/`model_name`/`study_date`.
   But the *derived* listmode tables inherit only `study` + `coincidence_mode`, and the *parent* DICOM
   blob-series manifest is anemic (`series`, `study`). `tessera inspect events-3p` tells you almost
   nothing about the patient, scanner, or acquisition. (#342)

2. **The recipe is not recorded.** `Manifest.producer` is the bare string `"tessera/0.0.0"` — the
   *packager*, not the DAQ decoder / coincidence-sorter / reconstruction software that produced the
   semantic content, and with a placeholder version + no git commit. The *settings* that produced the
   data (energy window, coincidence timing window, TOF calibration, the int16 quantization scales, a
   sim seed) live ad-hoc in `metadata` or nowhere. Nothing forces an external producer (a DAQ or a SIM
   authoring a Vortex block through the library) to record its build + config. This fails FAIR R1.2
   (reproducibility). (#324)

The `derived_from` edge (ADR-0033) answers *which parent / which version*; it does **not** answer
*what identity this product carries* or *how this product was made*. Those are the two gaps here.

### The load-bearing tension with ADR-0042

ADR-0042 drew a sharp line: the **wall-clock** `ingested_at` + host ride in **unsealed `aux/`** so
re-ingest stays byte-identical (writer-determinism is a release gate). One might therefore put *all*
provenance in `aux/`. That is wrong for this decision: provenance that is **strippable and forgeable**
(outside the seal, not in `manifest_hash`) is worthless as a reproducibility or attribution claim — a
`signer`/`config` that anyone can rewrite without changing the product id proves nothing (the same
class of bug ADR-0037 fixed for signatures). The resolution is the ADR-0042 *principle*, applied
correctly:

> **Non-deterministic bytes ride outside the seal; deterministic, identity-bearing bytes are sealed.**

`ingested_at` (wall-clock) is non-deterministic → unsealed. A product's **producer identity** and the
**config that generated it** are *deterministic given the run* (same input + same config → same bytes)
and are *part of what the product is* → **sealed**. Sealing them does **not** break writer-determinism
(no wall-clock enters), and it makes them tamper-evident and identity-bearing — which is the whole
point.

## Decision

Three sealed additions to `Manifest`, one enforcement rule, and a seal-time inheritance pass. All are
deterministic; the only cost is a **one-time conformance-corpus regeneration** (precedent: ADR-0049
accepted the same for the domain-separated MMR leaf).

### 1. Structured `producer` (sealed) — *who/what built this*

`Manifest.producer: Option<String>` → `Option<Producer>`:

```jsonc
"producer": {
  "tool":       "tessera",          // or "ge-listmode-daq", "recon-toolkit", a sim name — the generator
  "version":    "0.1.0",
  "git_commit": "0855f5f",           // optional; tessera stamps its own at build (build.rs + vergen)
  "git_repo":   "vig-os/tessera",    // optional
  "dirty":      false                 // optional; working tree state at build
}
```

`#[serde(default)]` + an untagged `String | Producer` deserializer keeps older manifests readable
(a bare string parses into `Producer{ tool: <string>, .. }`). Tessera stamps its **own** commit into
every `.tsra` it packages; an external producer fills its own identity through the write API (see §4).

### 2. Generation record (sealed) — *how it was made*, a **generic bag** (#324 owner directive)

A new sealed `Manifest.generation: Option<Generation>`:

```jsonc
"generation": {
  "config":     { /* free-form JSON: energy_window_keV, coincidence_window_ns, tof_cal_ref,
                     quant_scales, seed, cmd, … — whatever the generator used */ },
  "config_ref": "blake3:…"           // XOR alternative: point at a config/.ini/.cfg BLOCK carried
                                     //   in this .tsra (ADR-0038 Blob), bit-faithful + dedup'd
}
```

**Non-opinionated by construction.** Tessera does **not** enumerate or validate the `config` keys —
the shape of the bag is the *generator's* business, not the format's. The format enforces only that,
for a product that must be reproducible (§3), the bag is **present and non-empty** — inline `config`
(default; JSON I/O is cheap for small configs) **or** `config_ref` pointing at a carried Blob block
(for large or bit-faithful vendor config, e.g. the DUPLET DAQ `acq.cfg.LYSO4x9_6_SIPMGEN1_230223` —
it rides verbatim as a block and `config_ref` = its digest, avoiding re-serialization and preserving
the exact bytes). This keeps enforcement (R1.2) without Tessera becoming an ontology of every
instrument's config.

### 3. Enforcement (schema-driven, ADR-0040/0050 pattern)

**Whether a product must carry generation provenance is a schema property, not an engine hardcode.**
The core ships the sensible default: a product with `role = derived` (ADR-0033), or one authored by an
external DAQ/SIM through the library, requires a structured `producer` with a real `tool`+`version`
**and** a non-empty `generation` (inline `config` or a resolvable `config_ref`); absence is a **block**
(`Error::Invalid`), not a warning. A `raw` acquisition records instrument/serial identity instead (§5)
and is exempt — it was measured, not computed. A **domain schema is authoritative** and may tighten or
relax this per its needs (same mechanism as ADR-0050's `member_rule` and ADR-0040's tiers): the engine
reads the rule from the embedded, versioned schema and applies it — it does not itself decide policy.

### 4. Library / py-binding surface

The write API requires the caller to supply `Producer` + `Generation` when authoring a block, so a
DAQ/SIM **cannot seal an anonymous product**. `tessera-io`'s `ProvenanceOpts` gains `producer:
Producer` + `generation: Generation` (the deterministic, sealed pair); `ingested_at`/`host` stay where
ADR-0042 put them (unsealed `aux/provenance.json`). The ingest `--spec` (ADR-0035) gains an optional
`[producer]` + `[generation.config]` (or `generation.config_ref`) per member, so a declarative ingest
records the recipe without code.

### 5. Seal-time identity inheritance (#342) — *what identity this carries*, **schema-driven**

A seal-time pass walks `sources[derived_from]` to the ancestor(s) and copies **inheritable identity**
fields into the product's sealed `metadata`, unless the product already sets them. **Which fields are
inheritable is declared by the product schema — never hardcoded in the engine.** Tessera is general
tooling; it is not opinionated about what is a patient vs a recon parameter — the schema is. The
`FieldSpec` carries an `inherit` policy *alongside* the sensitivity tier it already carries (ADR-0040)
— one per-field descriptor, two **orthogonal** axes:

- **sensitivity tier** (`public`/`coded`/`sensitive`/`identifying`, ADR-0040) — governs anonymization,
  `redact`, and crypto-shred;
- **inheritance** (`inherit: true|false`, this ADR) — governs whether the field flows raw→derived.

A GE-listmode / DICOM schema *declares* (this is the schema's choice, not the format's) e.g.
`patient_id` (`identifying`, `inherit`), `study_instance_uid` (`identifying`, `inherit`),
`modality`/`manufacturer`/`model_name` (`public`, `inherit`); and declares recon params / quantization
scales / coincidence window **not** inheritable (they belong to each product's own `generation.config`,
§2). For a DICOM **blob-series** the same mechanism surfaces the series-constant DICOM identity
(`modality`/`study_instance_uid`/`series_instance_uid`/`study_date`/`manufacturer`/`model_name`/`exam`/
`sop_class_uid`/`file_count`) onto the **blob** manifest, so the cold tier is discoverable via
`inspect` without dereferencing DICOM bytes.

**Inheritance carries the field's sensitivity tier with it** — an inherited `patient_id` is still
`identifying` downstream, so the same schema tier that anonymizes / crypto-shreds it at the raw level
governs it at every derived level. Anonymizing a study (dropping/encrypting the `sensitive`+
`identifying` fields, ADR-0040) and inheriting identity are **the same per-field schema mechanism**
viewed from two directions: one removes the tiered fields, the other propagates them (tier included).

Inheritance writes to sealed `metadata` (products fill `metadata` per-ingest already → additive per
product, not a corpus-wide format change). The core ships a permissive default; each domain schema
curates its own inheritable set — unlimited fields, zero engine change (symmetry with ADR-0050's
schema-registered collection levels).

## Consequences

- **A single derived `.tsra` becomes self-describing** — `inspect` alone yields patient/exam/study/
  instrument (§5) + producer + recipe (§1/§2), closing the #1 root cause both reviewers converged on.
- **Reproducibility is tamper-evident** — the recipe is in `manifest_hash`; you cannot alter the
  recorded config/producer without changing the product id. Different config ⇒ different id, which is
  *correct* content-addressing.
- **Writer-determinism holds** (release gate untouched): every sealed addition is deterministic; only
  wall-clock/host remain unsealed (ADR-0042 invariant intact).
- **One-time conformance-corpus regen** for the new sealed fields (accept — ADR-0049 precedent). Old
  manifests stay *readable* via `#[serde(default)]`; they simply lack the new fields until re-ingested.
- **The DUPLET archive is re-ingested** to gain the fields (planned regardless): listmode chain +
  DICOM two-tier both pick up inherited identity + generation records; the DAQ `.cfg` rides as a
  `config_ref` block.
- **Generic, not opinionated** — the config bag means a future instrument Tessera has never seen is
  self-describing with zero format change; only `producer{tool,version}` + "bag non-empty" are the
  enforced minimum. Likewise the **inheritable-identity set and the enforcement rule live in the
  schema, not the engine** — tessera stays domain-agnostic (ADR-0003/0040/0050); adding a new
  inheritable field or a new required-provenance rule is a schema edit, never an engine change.

## Non-decisions / deferred

- Cross-product **generation-graph** queries (`which config produced this cohort?`) — a downstream
  index concern (#297/#299), not a format change.
- Validating `config` key *semantics* (units on settings, etc.) — a `--strict` lint (cf. ADR-0045's
  `--strict-units`), not a seal-time block.
- Signing the generation record separately from the manifest — unnecessary: it is inside
  `manifest_hash`, which ADR-0037 already signs.
