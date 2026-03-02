"""fd5.imaging.sim — Sim product schema for Monte Carlo simulation data.

Implements the ``sim`` product schema per white-paper.md § sim.
Handles ground truth phantom volumes (activity, attenuation), simulated
detector events (compound tables), and simulation parameters (GATE config,
geometry, source distribution).
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np

_SCHEMA_VERSION = "1.0.0"

_GZIP_LEVEL = 4

_ID_INPUTS = ["simulator", "phantom", "random_seed"]


class SimSchema:
    """Product schema for Monte Carlo simulation data (``sim``)."""

    product_type: str = "sim"
    schema_version: str = _SCHEMA_VERSION

    def json_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "_schema_version": {"type": "integer"},
                "product": {"type": "string", "const": "sim"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "domain": {"type": "string"},
                "ground_truth": {
                    "type": "object",
                    "description": "Ground truth distributions (activity, attenuation)",
                },
            },
            "required": ["_schema_version", "product", "name", "description"],
        }

    def required_root_attrs(self) -> dict[str, Any]:
        return {
            "product": "sim",
            "domain": "medical_imaging",
        }

    def id_inputs(self) -> list[str]:
        return list(_ID_INPUTS)

    def write(self, target: h5py.File | h5py.Group, data: dict[str, Any]) -> None:
        """Write sim data to *target*.

        *data* must contain:
        - ``ground_truth``: dict with ``activity`` and/or ``attenuation``
          numpy float32 arrays of shape (Z, Y, X)

        Optional keys:
        - ``events``: dict with ``events_2p`` and/or ``events_3p``
          structured numpy arrays
        - ``simulation``: dict with simulation parameters (written to
          ``metadata/simulation/``)
        """
        target.attrs["default"] = "phantom"

        self._write_ground_truth(target, data["ground_truth"])

        if "events" in data:
            self._write_events(target, data["events"])

        if "simulation" in data:
            self._write_simulation_metadata(target, data["simulation"])

    # ------------------------------------------------------------------
    # Ground truth
    # ------------------------------------------------------------------

    def _write_ground_truth(
        self,
        target: h5py.File | h5py.Group,
        ground_truth: dict[str, np.ndarray],
    ) -> None:
        grp = target.create_group("ground_truth")
        grp.attrs["description"] = "Known true distributions (unique to simulation)"

        for name, volume in ground_truth.items():
            chunks = (1,) + volume.shape[1:]
            ds = grp.create_dataset(
                name,
                data=volume,
                chunks=chunks,
                compression="gzip",
                compression_opts=_GZIP_LEVEL,
            )
            ds.attrs["description"] = f"Ground truth {name} map"

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _write_events(
        self,
        target: h5py.File | h5py.Group,
        events: dict[str, np.ndarray],
    ) -> None:
        grp = target.create_group("events")
        grp.attrs["description"] = (
            "Simulated detector events (same structure as listmode)"
        )

        for name, table in events.items():
            grp.create_dataset(name, data=table)
            grp[name].attrs["description"] = f"Simulated {name} event table"

    # ------------------------------------------------------------------
    # Simulation metadata
    # ------------------------------------------------------------------

    def _write_simulation_metadata(
        self,
        target: h5py.File | h5py.Group,
        simulation: dict[str, Any],
    ) -> None:
        if "metadata" not in target:
            meta_grp = target.create_group("metadata")
        else:
            meta_grp = target["metadata"]

        sim_grp = meta_grp.create_group("simulation")
        sim_grp.attrs["_type"] = simulation.get("_type", "gate")
        sim_grp.attrs["_version"] = np.int64(simulation.get("_version", 1))

        for key in ("gate_version", "physics_list", "n_primaries", "random_seed"):
            if key in simulation:
                val = simulation[key]
                if isinstance(val, int):
                    sim_grp.attrs[key] = np.int64(val)
                else:
                    sim_grp.attrs[key] = val

        if "geometry" in simulation:
            geo_grp = sim_grp.create_group("geometry")
            for k, v in simulation["geometry"].items():
                geo_grp.attrs[k] = v

        if "source" in simulation:
            src_grp = sim_grp.create_group("source")
            for k, v in simulation["source"].items():
                src_grp.attrs[k] = v
