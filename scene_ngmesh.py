"""scene_ngmesh.py — NGSolve/Netgen mesh of one steel rod + coaxial coil ("1dipole").

A single dipole (rod + solenoid coil on cube edge e14), built from analytic OCC
primitives via the shared ng_dipoles builder and meshed with Netgen. Geometry is
driven entirely by ng_config.py; no fea_* dependency.

Emits the standard "fea_mesh" payload (see ng_dipoles.assemble_scene_payload):
steel solid skin (parts slider), coil current arrows (current slider, coloured by
polarity), and a steel/coil/air mesh overlay (mesh slider).
"""

from __future__ import annotations

from cube_config import FRAME_EDGE_MM
from ng_config import (
    NG_CUBE_HALF_MM,
    NG_ROD_RADIUS_MM,
    NG_ROD_LENGTH_MM,
    NG_COIL_INNER_RADIUS_MM,
    NG_COIL_OUTER_RADIUS_MM,
    NG_COIL_LENGTH_MM,
    NG_CENTERLINE_OFFSET_FROM_EDGE_MM,
    NG_AIR_PADDING_MM,
    NG_MESH_MAXH_MM,
    NG_MESH_MAXH_DEVICE_MM,
    NG_COIL_CURRENTS,
)
import ng_dipoles
from ng_dipoles import DipoleSpec

_scene_cache = None


def invalidate_cache():
    global _scene_cache
    _scene_cache = None


def _centerline_mm() -> float:
    """Rod/coil centreline in the y–z plane (mm), offset in from the cube edge."""
    return FRAME_EDGE_MM / 2.0 - NG_CENTERLINE_OFFSET_FROM_EDGE_MM


def _air_half_extent_mm() -> float:
    return FRAME_EDGE_MM / 2.0 + NG_AIR_PADDING_MM


def build_specs() -> list:
    """The single dipole: rod along +X at (·, c, c), driven on edge e14."""
    c = _centerline_mm()
    return [DipoleSpec(
        name="e14",
        center_mm=(0.0, c, c),
        axis=(1.0, 0.0, 0.0),
        rod_length_mm=NG_ROD_LENGTH_MM,
        rod_radius_mm=NG_ROD_RADIUS_MM,
        coil_inner_mm=NG_COIL_INNER_RADIUS_MM,
        coil_outer_mm=NG_COIL_OUTER_RADIUS_MM,
        coil_length_mm=NG_COIL_LENGTH_MM,
        weight=float(NG_COIL_CURRENTS.get("e14", 1.0)),
    )]


def build_geometry(length_scale: float = 1.0):
    """Build the rod + coil + air OCC model + mesh. Returns (ngmesh, params, meta).

    length_scale multiplies every dimension; the solver passes 1e-3 to mesh in
    metres so B = curl(A) comes out in real Tesla.
    """
    return ng_dipoles.build_dipole_mesh(
        build_specs(),
        air_half_extent_mm=_air_half_extent_mm(),
        maxh_mm=NG_MESH_MAXH_MM,
        maxh_device_mm=NG_MESH_MAXH_DEVICE_MM,
        length_scale=length_scale,
    )


def build_ngmesh_scene(force: bool = False, fea_strength_scale: float = 1.0):
    global _scene_cache
    if _scene_cache is not None and not force:
        return _scene_cache

    scene, _build_s = ng_dipoles.assemble_scene_payload(
        "1dipole", build_specs(), NG_COIL_CURRENTS,
        air_half_extent_mm=_air_half_extent_mm(),
        maxh_mm=NG_MESH_MAXH_MM, maxh_device_mm=NG_MESH_MAXH_DEVICE_MM,
        arrow_radius_mm=NG_ROD_RADIUS_MM, half=NG_CUBE_HALF_MM,
    )

    m = scene["meta"]
    if m.get("error"):
        print(f"[ng] 1dipole mesh build FAILED: {m['error']}")
    else:
        m.update({
            "rod_radius_mm": NG_ROD_RADIUS_MM, "rod_length_mm": NG_ROD_LENGTH_MM,
            "coil_inner_mm": NG_COIL_INNER_RADIUS_MM, "coil_outer_mm": NG_COIL_OUTER_RADIUS_MM,
            "coil_length_mm": NG_COIL_LENGTH_MM,
            "centerline_offset_mm": NG_CENTERLINE_OFFSET_FROM_EDGE_MM,
            "air_padding_mm": NG_AIR_PADDING_MM,
        })
        print(
            f"[ng] scene=1dipole  rod r={NG_ROD_RADIUS_MM}mm L={NG_ROD_LENGTH_MM}mm  "
            f"coil {NG_COIL_INNER_RADIUS_MM}-{NG_COIL_OUTER_RADIUS_MM}mm L={NG_COIL_LENGTH_MM}mm  "
            f"air_pad={NG_AIR_PADDING_MM}mm (box {m['air_box_mm']:.0f}mm)  maxh={NG_MESH_MAXH_MM}mm  "
            f"points={m['n_points']:,}  steel={m['n_steel_tris']:,}  coil={m['n_coil_tris']:,}  "
            f"air={m['n_air_tris']:,}  {m['mesh_s']}s"
        )

    if force or fea_strength_scale == 1.0:
        _scene_cache = scene
    return scene
