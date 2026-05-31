"""scene_potcore.py — a single nested-pipe pot-core (cup-core) assembly.

One face assembly lifted out of the 30-coils frame (ng_frame): two coaxial
steel pipes joined by a back washer with one coil in the annular gap. Energised,
the inner pipe is one pole and the outer pipe the other, both emerging from the
open face — the rotationally-symmetric cousin of a horseshoe (U) magnet.

Geometry, meshing, surface classification and payload assembly are all reused
from ng_frame so this scene stays a thin wrapper around the shared helpers.
Driven entirely by ng_config (NGPC_* placement/current + NG30_HS_*/NG30_CU_*
dimensions + shared mesh density). Renders like every other NGSolve scene:
steel skin (parts slider), coil arrow (current slider), mesh overlay (mesh).
"""

from __future__ import annotations

import ng_frame
from ng_config import NGPC_FACE_KEY, NGPC_NORMAL, NGPC_CURRENT

SCENE_ID = "potcore_ng"

_scene_cache = None


def invalidate_cache():
    global _scene_cache
    _scene_cache = None


def build_specs():
    """Return (metal_prims, coils) for the single pot core (ng_frame format)."""
    metal, coil = ng_frame.face_horseshoe(NGPC_FACE_KEY, NGPC_NORMAL, NGPC_CURRENT)
    return metal, [coil]


def build_geometry(length_scale: float = 1.0):
    """Build the OCC model + Netgen mesh. Returns (ngmesh, coil_params, meta)."""
    from ng_config import NG_MESH_MAXH_MM, NG_MESH_MAXH_DEVICE_MM

    metal, coils = build_specs()
    return ng_frame.build_frame_mesh(
        metal, coils,
        air_half_extent_mm=ng_frame._air_half_extent_mm(),
        maxh_mm=NG_MESH_MAXH_MM, maxh_device_mm=NG_MESH_MAXH_DEVICE_MM,
        length_scale=length_scale,
    )


def build_scene(force: bool = False, fea_strength_scale: float = 1.0):
    global _scene_cache
    if _scene_cache is not None and not force:
        return _scene_cache

    metal, coils = build_specs()
    scene, _build_s = ng_frame.assemble_payload(
        metal, coils, SCENE_ID, {NGPC_FACE_KEY: NGPC_CURRENT})

    m = scene["meta"]
    if m.get("error"):
        print(f"[ng] potcore mesh build FAILED: {m['error']}")
    else:
        m.update({"n_coils": 1, "face": NGPC_FACE_KEY})
        print(
            f"[ng] scene={SCENE_ID}  coils=1 (1 pot core on {NGPC_FACE_KEY})  "
            f"air box {m['air_box_mm']:.0f}mm  maxh={m['maxh_mm']}mm  "
            f"points={m['n_points']:,}  steel={m['n_steel_tris']:,}  "
            f"coil={m['n_coil_tris']:,}  air={m['n_air_tris']:,}  {m['mesh_s']}s"
        )

    if force or fea_strength_scale == 1.0:
        _scene_cache = scene
    return scene
