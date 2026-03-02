//! # fd5
//!
//! Rust implementation of fd5 Merkle-tree hashing, verification, and editing
//! for immutable HDF5 data products sealed with `content_hash`.

pub mod attr_ser;
pub mod edit;
pub mod error;
pub mod hash;
pub mod schema;
pub mod verify;

pub use error::{Fd5Error, Fd5Result};
pub use hash::{compute_content_hash, compute_id};
pub use verify::{Fd5Status, verify};
