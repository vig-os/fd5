# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- **Physical units convention helpers** ([#13](https://github.com/vig-os/fd5/issues/13))
  - `write_quantity` creates a sub-group with `value`, `units`, `unitSI` attrs
  - `read_quantity` returns `(value, units, unit_si)` from a quantity sub-group
  - `set_dataset_units` sets `units` and `unitSI` attrs on an HDF5 dataset

### Changed

### Removed

### Fixed

### Security
