"""scene_ng12dipoles.py — NGSolve/Netgen mesh of 12 dipoles (one per cube edge).

A steel rod + coaxial coil centred on each of the 12 edges of the inset cube
skeleton, built from analytic OCC primitives via the shared ng_dipoles builder
and meshed with Netgen. Geometry is driven entirely by ng_config.py
(NG12_* + NG_CUBE_* + shared mesh density). No fea_* dependency.

Emits the same "fea_mesh" payload as the 1-dipole scene, so the viewer renders
it identically: steel solid skin (parts slider), coil current arrows (current
slider, coloured by polarity), and a steel/coil/air mesh overlay (mesh slider).
"""

from __future__ import annotations

from cube_config import FRAME_EDGE_MM
import ng_config
from ng_config import (
    NG_CUBE_HALF_MM,
    NG_MESH_MAXH_DEVICE_MM,
    NG12_ROD_RADIUS_MM,
    NG12_COIL_CLEARANCE_MM,
    NG12_COIL_THICKNESS_MM,
    NG12_ROD_LENGTH_MM,
    NG12_COIL_LENGTH_MM,
)
import ng_dipoles

_scene_cache = None


def invalidate_cache():
    global _scene_cache
    _scene_cache = None


def _air_half_extent_mm() -> float:
    return FRAME_EDGE_MM / 2.0 + ng_config.air_padding_mm()


def build_specs() -> list:
    """The 12 edge dipoles, weights from the active config (key order = build order)."""
    return ng_dipoles.edge_dipole_specs(
        ng_config.ng12_currents(),
        rod_radius_mm=NG12_ROD_RADIUS_MM,
        coil_clearance_mm=NG12_COIL_CLEARANCE_MM,
        coil_thickness_mm=NG12_COIL_THICKNESS_MM,
        rod_length_mm=NG12_ROD_LENGTH_MM,
        coil_length_mm=NG12_COIL_LENGTH_MM,
        half=NG_CUBE_HALF_MM,
    )


def coil_update() -> dict:
    """Arrows + frame polarity + drive totals for the active config — no re-mesh."""
    upd = ng_dipoles.assemble_coil_update(
        "12dipoles_ng", build_specs(), ng_config.ng12_currents(),
        arrow_radius_mm=NG12_ROD_RADIUS_MM, half=NG_CUBE_HALF_MM,
    )
    upd["meta"]["config"] = ng_config.NG12_CONFIG_ACTIVE
    return upd


def build_geometry(length_scale: float = 1.0):
    """Build the 12-dipole OCC model + mesh. Returns (ngmesh, params, meta)."""
    specs = build_specs()
    return ng_dipoles.build_dipole_mesh(
        specs,
        air_half_extent_mm=_air_half_extent_mm(),
        maxh_mm=ng_config.mesh_maxh_mm(),
        maxh_device_mm=NG_MESH_MAXH_DEVICE_MM,
        length_scale=length_scale,
    )


def build_scene(force: bool = False, fea_strength_scale: float = 1.0):
    global _scene_cache
    if _scene_cache is not None and not force:
        return _scene_cache

    currents = ng_config.ng12_currents()
    scene, _build_s = ng_dipoles.assemble_scene_payload(
        "12dipoles_ng", build_specs(), currents,
        air_half_extent_mm=_air_half_extent_mm(),
        maxh_mm=ng_config.mesh_maxh_mm(), maxh_device_mm=NG_MESH_MAXH_DEVICE_MM,
        arrow_radius_mm=NG12_ROD_RADIUS_MM, half=NG_CUBE_HALF_MM,
    )

    n_active = sum(1 for v in currents.values() if abs(float(v)) > 1e-9)
    m = scene["meta"]
    if m.get("error"):
        print(f"[ng] 12dipole mesh build FAILED: {m['error']}")
    else:
        m.update({
            "n_dipoles": len(currents),
            "n_active_coils": n_active,
            "config": ng_config.NG12_CONFIG_ACTIVE,
            "rod_radius_mm": NG12_ROD_RADIUS_MM, "rod_length_mm": NG12_ROD_LENGTH_MM,
            "coil_length_mm": NG12_COIL_LENGTH_MM, "air_padding_mm": ng_config.air_padding_mm(),
            "extended_grid": ng_config.NG_EXTENDED_GRID,
        })
        print(
            f"[ng] scene=12dipoles_ng config={ng_config.NG12_CONFIG_ACTIVE}  dipoles={len(currents)} (active coils={n_active})  "
            f"rod r={NG12_ROD_RADIUS_MM}mm L={NG12_ROD_LENGTH_MM}mm  "
            f"air_pad={ng_config.air_padding_mm()}mm (box {m['air_box_mm']:.0f}mm){' [EXT]' if ng_config.NG_EXTENDED_GRID else ''}  "
            f"maxh={ng_config.mesh_maxh_mm()}mm  "
            f"points={m['n_points']:,}  steel={m['n_steel_tris']:,}  coil={m['n_coil_tris']:,}  "
            f"air={m['n_air_tris']:,}  {m['mesh_s']}s"
        )

    if force or fea_strength_scale == 1.0:
        _scene_cache = scene
    return scene
