"""scene_ngmesh.py — NGSolve/Netgen tetrahedral mesh of a rod + coil.

A steel rod with a coaxial solenoid coil, built from analytic OCC primitives
and meshed with Netgen instead of voxelized. Geometry is driven entirely by
ng_config.py. This is the starting point for the real edge-element
magnetostatic solver; for now it only builds and ships the surface mesh so we
can SEE it in the viewer.

Scene message format
--------------------
{
  "type": "fea_mesh",
  "scene_id": "ngmesh",
  "frame_config": { ... same as other scenes (Ou outline + hover corners) ... },
  "vertices": [[x, y, z], ...],            # scene units (mm * MM_TO_SCENE)
  "regions": [
    {"name": "steel", "color": [r,g,b], "triangles": [[i,j,k], ...]},
    {"name": "coil",  "color": [r,g,b], "triangles": [[i,j,k], ...]}
  ],
  "meta": { n_points, n_tris, maxh_mm, regions: {...}, error?: str }
}
Triangle indices are 0-based into "vertices".
"""

from __future__ import annotations

import time

from cube_config import FRAME_EDGE_MM, FRAME_INSET_MM, MM_TO_SCENE
from fea_config import FRAME_GAP_MM
from coil_init import export_coil_table
from fea_model import _skeleton_dims, _cube_corner_positions_mm
from scene_render import frame_config_dict
from ng_config import (
    NG_ROD_RADIUS_MM,
    NG_ROD_LENGTH_MM,
    NG_COIL_INNER_RADIUS_MM,
    NG_COIL_OUTER_RADIUS_MM,
    NG_COIL_LENGTH_MM,
    NG_CENTERLINE_OFFSET_FROM_EDGE_MM,
    NG_AIR_PADDING_MM,
    NG_MESH_MAXH_MM,
    NG_MESH_MAXH_DEVICE_MM,
)

# Region appearance (RGB 0..1) — steel cool grey, coil warm amber, air faint blue.
STEEL_COLOR = (0.80, 0.82, 0.85)
COIL_COLOR = (1.00, 0.72, 0.12)
AIR_COLOR = (0.35, 0.65, 1.00)

# Per-region render opacities (solid, wire). Air is a faint ghost box.
STEEL_OPACITY = (0.18, 0.75)
COIL_OPACITY = (0.18, 0.75)
AIR_OPACITY = (0.02, 0.10)

# Volume domain numbering follows the Glue order below.
_DOMAIN_STEEL = 1
_DOMAIN_COIL = 2
_DOMAIN_AIR = 3
_EXTERIOR = 0

_scene_cache = None


def invalidate_cache():
    global _scene_cache
    _scene_cache = None


def _device_centerline():
    """Rod/coil centreline point in the y–z plane (mm), offset in from the cube edge."""
    half = FRAME_EDGE_MM / 2.0
    c = half - NG_CENTERLINE_OFFSET_FROM_EDGE_MM
    return c


def _corner_positions_mm():
    """Cube envelope corners (mm) for the Ou outline + corner hover in the viewer."""
    sk = _skeleton_dims(FRAME_EDGE_MM, FRAME_EDGE_MM, FRAME_INSET_MM, 4, FRAME_GAP_MM)
    return _cube_corner_positions_mm(sk["vertices"], sk["half_h"])


def _air_half_extent_mm() -> float:
    """Half-width of the air box: cube half-envelope + padding on every face."""
    return FRAME_EDGE_MM / 2.0 + NG_AIR_PADDING_MM


def build_geometry(length_scale: float = 1.0):
    """Build the rod + coil + air OCC model and return (netgen_mesh, params).

    Both bodies are centred at x=0, axis along +X, at (·, c, c) where c is the
    centreline offset. The air region is the cube envelope expanded by
    NG_AIR_PADDING_MM, minus the rod and coil so the mesh is conforming.
    Domains: "steel" (rod), "coil" (sleeve), "air". Outer box boundary = "outer".

    length_scale multiplies every dimension (and maxh). Use 1.0 for the mm render
    mesh; the solver passes 1e-3 to mesh in metres so B = curl(A) comes out in
    real Tesla (saturation needs a physical field scale, not mm-arbitrary units).

    params describe the placement (in the SAME scaled units) so the solver can
    build the coil current and sample B without re-deriving geometry.
    """
    from netgen.occ import Cylinder, Box, Pnt, Dir, Glue, OCCGeometry

    s = float(length_scale)
    c = _device_centerline() * s
    axis = Dir(1.0, 0.0, 0.0)
    rod_len = NG_ROD_LENGTH_MM * s
    coil_len = NG_COIL_LENGTH_MM * s

    rod_base = Pnt(-rod_len / 2.0, c, c)
    rod = Cylinder(rod_base, axis, r=NG_ROD_RADIUS_MM * s, h=rod_len)
    rod.mat("steel")

    coil_base = Pnt(-coil_len / 2.0, c, c)
    coil = (
        Cylinder(coil_base, axis, r=NG_COIL_OUTER_RADIUS_MM * s, h=coil_len)
        - Cylinder(coil_base, axis, r=NG_COIL_INNER_RADIUS_MM * s, h=coil_len)
    )
    coil.mat("coil")

    if NG_MESH_MAXH_DEVICE_MM is not None:
        rod.maxh = float(NG_MESH_MAXH_DEVICE_MM) * s
        coil.maxh = float(NG_MESH_MAXH_DEVICE_MM) * s

    h = _air_half_extent_mm() * s
    box = Box(Pnt(-h, -h, -h), Pnt(h, h, h))
    box.faces.name = "outer"            # far-field boundary for the solver
    air = box - rod - coil
    air.mat("air")

    geo = OCCGeometry(Glue([rod, coil, air]))
    ngmesh = geo.GenerateMesh(maxh=float(NG_MESH_MAXH_MM) * s)
    params = {
        "center": c,
        "axis": (1.0, 0.0, 0.0),
        "half_extent": h,
        "length_scale": s,
        "rod_length": rod_len,
        "coil_length": coil_len,
    }
    return ngmesh, params


def _build_ng_mesh():
    """Back-compat: just the netgen mesh (surface render path)."""
    ngmesh, _params = build_geometry()
    return ngmesh


def _extract_surface(ngmesh, sc: float):
    """Pull vertices (scaled to scene units) and triangle lists by render region.

    Each surface triangle borders two volume domains (domin/domout); we classify
    by which domains it touches:
      - touches steel (1)            → "steel"  (rod surface)
      - touches coil (2)             → "coil"   (coil sleeve surface)
      - touches the exterior (0)     → "air"    (outer air-box boundary only)
    Internal air-device interfaces are already captured as steel/coil, so the
    "air" bucket is just the outer box — a clean ghost boundary to render.
    """
    verts = []
    for mp in ngmesh.Points():
        x, y, z = mp.p[0], mp.p[1], mp.p[2]
        verts.append([round(x * sc, 4), round(y * sc, 4), round(z * sc, 4)])
    n_pts = len(verts)

    descriptors = list(ngmesh.FaceDescriptors())

    def doms_of(surf_index: int) -> set[int]:
        idx = surf_index - 1
        if 0 <= idx < len(descriptors):
            fd = descriptors[idx]
            return {fd.domin, fd.domout}
        return {0}

    def region_of(surf_index: int) -> str | None:
        doms = doms_of(surf_index)
        if _DOMAIN_STEEL in doms:
            return "steel"
        if _DOMAIN_COIL in doms:
            return "coil"
        if _EXTERIOR in doms:
            return "air"
        return None

    tris: dict[str, list] = {"steel": [], "coil": [], "air": []}
    for el in ngmesh.Elements2D():
        region = region_of(el.index)
        if region is None:
            continue
        bucket = tris[region]
        vs = el.vertices
        tri = [vs[0].nr - 1, vs[1].nr - 1, vs[2].nr - 1]
        if all(0 <= i < n_pts for i in tri):
            bucket.append(tri)
        # Quads (rare here) → split into two triangles.
        if len(vs) == 4:
            quad = [vs[0].nr - 1, vs[2].nr - 1, vs[3].nr - 1]
            if all(0 <= i < n_pts for i in quad):
                bucket.append(quad)

    return verts, tris


def build_ngmesh_scene(force: bool = False, fea_strength_scale: float = 1.0):
    global _scene_cache
    if _scene_cache is not None and not force:
        return _scene_cache

    sc = MM_TO_SCENE
    corner_pos_mm = _corner_positions_mm()

    frame_config = frame_config_dict(
        edge_mm=FRAME_EDGE_MM,
        height_mm=FRAME_EDGE_MM,
        inset_mm=FRAME_INSET_MM,
        corner_pos_mm=corner_pos_mm,
        coil_weights=export_coil_table(),
        sc=sc,
    )

    scene = {
        "type": "fea_mesh",
        "scene_id": "ngmesh",
        "frame_config": frame_config,
        "vertices": [],
        "regions": [],
        "meta": {},
    }

    try:
        t0 = time.perf_counter()
        ngmesh = _build_ng_mesh()
        verts, tris = _extract_surface(ngmesh, sc)
        dt = time.perf_counter() - t0

        steel_tris = tris["steel"]
        coil_tris = tris["coil"]
        air_tris = tris["air"]
        n_tris = len(steel_tris) + len(coil_tris) + len(air_tris)

        scene["vertices"] = verts
        scene["regions"] = [
            {"name": "steel", "color": list(STEEL_COLOR), "triangles": steel_tris,
             "solid_opacity": STEEL_OPACITY[0], "wire_opacity": STEEL_OPACITY[1]},
            {"name": "coil", "color": list(COIL_COLOR), "triangles": coil_tris,
             "solid_opacity": COIL_OPACITY[0], "wire_opacity": COIL_OPACITY[1]},
            {"name": "air", "color": list(AIR_COLOR), "triangles": air_tris,
             "solid_opacity": AIR_OPACITY[0], "wire_opacity": AIR_OPACITY[1]},
        ]
        scene["meta"] = {
            "rod_radius_mm": NG_ROD_RADIUS_MM,
            "rod_length_mm": NG_ROD_LENGTH_MM,
            "coil_inner_mm": NG_COIL_INNER_RADIUS_MM,
            "coil_outer_mm": NG_COIL_OUTER_RADIUS_MM,
            "coil_length_mm": NG_COIL_LENGTH_MM,
            "centerline_offset_mm": NG_CENTERLINE_OFFSET_FROM_EDGE_MM,
            "air_padding_mm": NG_AIR_PADDING_MM,
            "air_box_mm": round(2.0 * _air_half_extent_mm(), 2),
            "maxh_mm": NG_MESH_MAXH_MM,
            "maxh_device_mm": NG_MESH_MAXH_DEVICE_MM,
            "n_points": len(verts),
            "n_tris": n_tris,
            "regions": {"steel": len(steel_tris), "coil": len(coil_tris), "air": len(air_tris)},
            "mesh_s": round(dt, 2),
        }
        print(
            f"[ng] scene=ngmesh  rod r={NG_ROD_RADIUS_MM}mm L={NG_ROD_LENGTH_MM}mm  "
            f"coil {NG_COIL_INNER_RADIUS_MM}-{NG_COIL_OUTER_RADIUS_MM}mm L={NG_COIL_LENGTH_MM}mm  "
            f"air_pad={NG_AIR_PADDING_MM}mm (box {2.0 * _air_half_extent_mm():.0f}mm)  "
            f"maxh={NG_MESH_MAXH_MM}mm  points={len(verts):,}  tris={n_tris:,} "
            f"(steel={len(steel_tris):,} coil={len(coil_tris):,} air={len(air_tris):,})  {dt:.2f}s"
        )
    except Exception as exc:  # noqa: BLE001 — never crash scene build / server startup
        scene["meta"] = {"error": f"{type(exc).__name__}: {exc}"}
        print(f"[ng] mesh build FAILED: {type(exc).__name__}: {exc}")

    if force or fea_strength_scale == 1.0:
        _scene_cache = scene
    return scene
