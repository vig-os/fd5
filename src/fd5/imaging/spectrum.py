"""fd5.imaging.spectrum — Spectrum product schema for histogrammed/binned data.

Implements the ``spectrum`` product schema per white-paper.md § spectrum.
Handles 1D/2D/ND float32 histograms: energy spectra, positron lifetime
distributions (PALS), Doppler broadening, coincidence matrices, angular
correlations (ACAR), TOF histograms, and any other binned statistical summary.
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np

_SCHEMA_VERSION = "1.0.0"

_GZIP_LEVEL = 4

_ID_INPUTS = ["timestamp", "scanner", "measurement_id"]


class SpectrumSchema:
    """Product schema for histogrammed / binned data (``spectrum``)."""

    product_type: str = "spectrum"
    schema_version: str = _SCHEMA_VERSION

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "spectrum"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "n_dimensions": {"type": "integer"},
            },
            "required": ["_schema_version", "product", "name", "description"],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {
            "product": "spectrum",
            "domain": "medical_imaging",
        }

    def id_inputs(self) -> list[str]:
        return list(_ID_INPUTS)

    def write(self, target: h5py.File | h5py.Group, data: dict[str, Any]) -> None:
        """Write spectrum data to *target*.

        *data* must contain:
        - ``counts``: numpy float32 array (1D or 2D histogram)
        - ``axes``: list of dicts, one per dimension, each with
          ``label``, ``units``, ``unitSI``, ``bin_edges``, and ``description``

        Optional keys:
        - ``counts_errors``: numpy float32 array, same shape as ``counts``
        - ``metadata``: dict with ``method`` and/or ``acquisition`` sub-dicts
        - ``fit``: dict with fit results (curve, residuals, components, parameters)
        """
        counts = data["counts"]
        axes = data["axes"]

        target.attrs["n_dimensions"] = np.int64(counts.ndim)
        target.attrs["default"] = data.get("default", "counts")

        self._write_counts(target, counts)

        if "counts_errors" in data:
            self._write_counts_errors(target, data["counts_errors"])

        self._write_axes(target, axes)

        if "metadata" in data:
            self._write_metadata(target, data["metadata"])

        if "fit" in data:
            self._write_fit(target, data["fit"])

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------

    def _write_counts(
        self,
        target: h5py.File | h5py.Group,
        counts: np.ndarray,
    ) -> None:
        ds = target.create_dataset(
            "counts",
            data=counts.astype(np.float32),
            compression="gzip",
            compression_opts=_GZIP_LEVEL,
        )
        ds.attrs["description"] = "Binned counts (or rates, or normalized intensity)"

    # ------------------------------------------------------------------
    # Counts errors
    # ------------------------------------------------------------------

    def _write_counts_errors(
        self,
        target: h5py.File | h5py.Group,
        errors: np.ndarray,
    ) -> None:
        ds = target.create_dataset(
            "counts_errors",
            data=errors.astype(np.float32),
            compression="gzip",
            compression_opts=_GZIP_LEVEL,
        )
        ds.attrs["description"] = "Statistical uncertainties on counts (1-sigma)"

    # ------------------------------------------------------------------
    # Axes
    # ------------------------------------------------------------------

    def _write_axes(
        self,
        target: h5py.File | h5py.Group,
        axes: list[dict[str, Any]],
    ) -> None:
        axes_grp = target.create_group("axes")
        for i, ax in enumerate(axes):
            ax_grp = axes_grp.create_group(f"ax{i}")
            ax_grp.attrs["label"] = ax["label"]
            ax_grp.attrs["units"] = ax["units"]
            ax_grp.attrs["unitSI"] = np.float64(ax["unitSI"])
            ax_grp.attrs["description"] = ax["description"]

            bin_edges = np.asarray(ax["bin_edges"], dtype=np.float64)
            ax_grp.create_dataset("bin_edges", data=bin_edges)

            bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
            ax_grp.create_dataset("bin_centers", data=bin_centers)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _write_metadata(
        self,
        target: h5py.File | h5py.Group,
        metadata: dict[str, Any],
    ) -> None:
        meta_grp = target.create_group("metadata")

        if "method" in metadata:
            self._write_method(meta_grp, metadata["method"])

        if "acquisition" in metadata:
            self._write_acquisition(meta_grp, metadata["acquisition"])

    def _write_method(
        self,
        meta_grp: h5py.Group,
        method: dict[str, Any],
    ) -> None:
        method_grp = meta_grp.create_group("method")
        method_grp.attrs["_type"] = method["_type"]
        method_grp.attrs["_version"] = np.int64(method.get("_version", 1))
        method_grp.attrs["description"] = method.get("description", "")

        for key, value in method.items():
            if key in ("_type", "_version", "description"):
                continue
            if isinstance(value, dict):
                sub = method_grp.create_group(key)
                for sk, sv in value.items():
                    if isinstance(sv, (list, tuple)):
                        sub.attrs[sk] = np.array(sv, dtype=np.float64)
                    elif isinstance(sv, float):
                        sub.attrs[sk] = np.float64(sv)
                    elif isinstance(sv, int):
                        sub.attrs[sk] = np.int64(sv)
                    else:
                        sub.attrs[sk] = sv
            elif isinstance(value, float):
                method_grp.attrs[key] = np.float64(value)
            elif isinstance(value, int):
                method_grp.attrs[key] = np.int64(value)
            elif isinstance(value, str):
                method_grp.attrs[key] = value

    def _write_acquisition(
        self,
        meta_grp: h5py.Group,
        acquisition: dict[str, Any],
    ) -> None:
        acq_grp = meta_grp.create_group("acquisition")
        acq_grp.attrs["total_counts"] = np.int64(acquisition["total_counts"])
        acq_grp.attrs["dead_time_fraction"] = np.float64(
            acquisition["dead_time_fraction"]
        )
        acq_grp.attrs["description"] = acquisition.get(
            "description", "Acquisition statistics"
        )

        if "live_time" in acquisition:
            lt_grp = acq_grp.create_group("live_time")
            lt = acquisition["live_time"]
            lt_grp.attrs["value"] = np.float64(lt["value"])
            lt_grp.attrs["units"] = lt.get("units", "s")
            lt_grp.attrs["unitSI"] = np.float64(lt.get("unitSI", 1.0))

        if "real_time" in acquisition:
            rt_grp = acq_grp.create_group("real_time")
            rt = acquisition["real_time"]
            rt_grp.attrs["value"] = np.float64(rt["value"])
            rt_grp.attrs["units"] = rt.get("units", "s")
            rt_grp.attrs["unitSI"] = np.float64(rt.get("unitSI", 1.0))

    # ------------------------------------------------------------------
    # Fit
    # ------------------------------------------------------------------

    def _write_fit(
        self,
        target: h5py.File | h5py.Group,
        fit: dict[str, Any],
    ) -> None:
        fit_grp = target.create_group("fit")
        fit_grp.attrs["_type"] = fit["_type"]
        fit_grp.attrs["_version"] = np.int64(fit.get("_version", 1))
        fit_grp.attrs["chi_squared"] = np.float64(fit["chi_squared"])
        fit_grp.attrs["degrees_of_freedom"] = np.int64(fit["degrees_of_freedom"])
        fit_grp.attrs["description"] = fit.get(
            "description", "Model fit to the spectrum data"
        )

        if "curve" in fit:
            ds = fit_grp.create_dataset(
                "curve",
                data=np.asarray(fit["curve"], dtype=np.float32),
                compression="gzip",
                compression_opts=_GZIP_LEVEL,
            )
            ds.attrs["description"] = "Evaluated fit function"

        if "residuals" in fit:
            ds = fit_grp.create_dataset(
                "residuals",
                data=np.asarray(fit["residuals"], dtype=np.float32),
                compression="gzip",
                compression_opts=_GZIP_LEVEL,
            )
            ds.attrs["description"] = "Fit residuals (counts - curve)"

        if "components" in fit:
            self._write_components(fit_grp, fit["components"])

        if "parameters" in fit:
            self._write_parameters(fit_grp, fit["parameters"])

    def _write_components(
        self,
        fit_grp: h5py.Group,
        components: list[dict[str, Any]],
    ) -> None:
        comp_grp = fit_grp.create_group("components")
        for i, comp in enumerate(components):
            c_grp = comp_grp.create_group(f"component_{i}")
            c_grp.attrs["label"] = comp["label"]
            c_grp.attrs["description"] = comp.get("description", "")

            if "intensity" in comp:
                c_grp.attrs["intensity"] = np.float64(comp["intensity"])
            if "intensity_error" in comp:
                c_grp.attrs["intensity_error"] = np.float64(comp["intensity_error"])

            if "lifetime" in comp:
                lt = comp["lifetime"]
                lt_grp = c_grp.create_group("lifetime")
                lt_grp.attrs["value"] = np.float64(lt["value"])
                lt_grp.attrs["units"] = lt.get("units", "ns")
                lt_grp.attrs["unitSI"] = np.float64(lt.get("unitSI", 1e-9))

            if "lifetime_error" in comp:
                lte = comp["lifetime_error"]
                lte_grp = c_grp.create_group("lifetime_error")
                lte_grp.attrs["value"] = np.float64(lte["value"])
                lte_grp.attrs["units"] = lte.get("units", "ns")
                lte_grp.attrs["unitSI"] = np.float64(lte.get("unitSI", 1e-9))

            if "curve" in comp:
                ds = c_grp.create_dataset(
                    "curve",
                    data=np.asarray(comp["curve"], dtype=np.float32),
                    compression="gzip",
                    compression_opts=_GZIP_LEVEL,
                )
                ds.attrs["description"] = f"Component {i} contribution"

    def _write_parameters(
        self,
        fit_grp: h5py.Group,
        parameters: dict[str, Any],
    ) -> None:
        param_grp = fit_grp.create_group("parameters")
        dt = h5py.special_dtype(vlen=str)
        param_grp.attrs.create("names", data=parameters["names"], dtype=dt)
        param_grp.attrs["values"] = np.array(parameters["values"], dtype=np.float64)
        param_grp.attrs["errors"] = np.array(parameters["errors"], dtype=np.float64)
        param_grp.attrs["description"] = parameters.get(
            "description", "All fit parameters as arrays"
        )
