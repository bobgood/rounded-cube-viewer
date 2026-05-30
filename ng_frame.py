"""ng_frame.py — NGSolve/Netgen geometry+mesh of the full frame ("30 coils").

Ported from the old voxel "frame" scene. The steel skeleton is:
  - 12 edge rods           (one cylinder centred on each cube edge)
  - 8 corner caps          (a sphere at each corner + 3 collar stubs toward its
                            three edges, joining the rods into one body)
  - 6 face horseshoes      (two coaxial nested pipes + a back washer per face)
all fused into a single "steel" solid. The 30 coils are:
  - 24 split edge coils    (two per edge: E{a}{b} near corner a and E{b}{a} near
                            corner b, with a bare-rod gap at the edge midpoint)
  - 6 face coils           (one in each horseshoe annulus, between the two pipes)
each its own "coil{i}" material so the solver can drive J per region.

Geometry is driven entirely by ng_config (NG30_* + NG_CUBE_* + shared mesh
density); coil weights come from NG30_COIL_CURRENTS (corner-keyed for edges,
face-keyed for faces — this reproduces the "common pole at each corner" wiring).
No fea_* dependency. Surface triangles are classified GEOMETRICALLY against the
analytic primitives, so the result renders like every other NGSolve scene:
steel skin (parts slider), coil arrows (current slider), mesh overlay (mesh).
"""

from __future__ import annotations

import math
import time
from functools import reduce

from cube_config import FRAME_EDGE_MM
from ng_config import (
    NG_CUBE_HALF_MM,
    NG_AIR_PADDING_MM,
    NG_MESH_MAXH_MM,
    NG_MESH_MAXH_DEVICE_MM,
    NG30_ROD_RADIUS_MM,
    NG30_ROD_LENGTH_MM,
    NG30_CAP_RADIUS_MM,
    NG30_COLLAR_RADIUS_MM,
    NG30_COLLAR_LENGTH_MM,
    NG30_CV_GAP_FROM_CORNER_MM,
    NG30_CV_EXTEND_MM,
    NG30_CV_THICKNESS_MM,
    NG30_CV_CLEARANCE_FROM_ROD_MM,
    NG30_HS_INNER_PIPE_OD_MM,
    NG30_HS_OUTER_PIPE_OD_MM,
    NG30_HS_WALL_THICKNESS_MM,
    NG30_HS_LENGTH_MM,
    NG30_HS_WASHER_THICKNESS_MM,
    NG30_CU_CLEARANCE_FROM_HS_INNER_MM,
    NG30_CU_CLEARANCE_FROM_HS_OUTER_MM,
    NG30_CU_WALL_THICKNESS_MM,
    NG30_CU_EXTENSION_MM,
    NG30_COIL_CURRENTS,
)
import ng_dipoles
from ng_dipoles import (
    cube_corner_positions, _unit, dipole_arrows,
    STEEL_COLOR, COIL_COLOR, AIR_COLOR,
    STEEL_OPACITY, COIL_OPACITY, AIR_OPACITY,
)

_scene_cache = None


def invalidate_cache():
    global _scene_cache
    _scene_cache = None


# ── Topology (matches geometry_ids / cube_corner_positions numbering) ─────────
# Undirected cube edges as (a, b); see cube_corner_positions for corner coords.
_EDGES = [
    (1, 2), (2, 3), (3, 4), (4, 1),     # top ring  (+Z)
    (5, 6), (6, 7), (7, 8), (8, 5),     # bottom ring (−Z)
    (1, 5), (2, 6), (3, 7), (4, 8),     # vertical struts
]
# Faces: clockwise key + outward normal (face centred at normal * FRAME_EDGE/2).
_FACES = [
    ("f1234", (0.0, 0.0, 1.0)), ("f5678", (0.0, 0.0, -1.0)),
    ("f1265", (1.0, 0.0, 0.0)), ("f3487", (-1.0, 0.0, 0.0)),
    ("f1485", (0.0, 1.0, 0.0)), ("f3276", (0.0, -1.0, 0.0)),
]


def _air_half_extent_mm() -> float:
    return FRAME_EDGE_MM / 2.0 + NG_AIR_PADDING_MM


def _edge_weight(near: int, far: int, currents: dict) -> float:
    """Weight for the edge coil near `near` (far corner `far`).

    Prefer an explicit directed-edge key e{near}{far}; otherwise fall back to the
    corner key c{near} (the "common pole" wiring used by the default frame)."""
    for key in (f"e{near}{far}", f"c{near}"):
        if key in currents:
            return float(currents[key])
    return 0.0


# ── Geometry specs (mm) ───────────────────────────────────────────────────────

def build_specs():
    """Return (metal_prims, coils) describing the whole frame in mm.

    metal_prims: list of {kind: 'cyl'|'sphere'|'tube', ...} steel primitives
                 (all fused into one steel body; also used for classification).
    coils:       list of coil param dicts (ng_dipoles format: name/coil_mat/
                 center/axis/coil_half/coil_inner/coil_outer/weight/has_coil).
    """
    corners = cube_corner_positions(NG_CUBE_HALF_MM)
    metal = []
    coils = []

    rod_half = NG30_ROD_LENGTH_MM / 2.0
    cv_in = NG30_ROD_RADIUS_MM + NG30_CV_CLEARANCE_FROM_ROD_MM
    cv_out = cv_in + NG30_CV_THICKNESS_MM
    cv_half = NG30_CV_EXTEND_MM / 2.0
    cv_mid_s = NG30_CV_GAP_FROM_CORNER_MM + cv_half   # arc dist corner→coil centre

    # Collar directions per corner (toward each of its 3 edge neighbours).
    collar_dirs = {c: [] for c in corners}
    for a, b in _EDGES:
        pa, pb = corners[a], corners[b]
        collar_dirs[a].append(_unit((pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])))
        collar_dirs[b].append(_unit((pa[0] - pb[0], pa[1] - pb[1], pa[2] - pb[2])))

    # 12 edge rods (centred on each edge midpoint).
    for a, b in _EDGES:
        pa, pb = corners[a], corners[b]
        mid = tuple((pa[i] + pb[i]) / 2.0 for i in range(3))
        axis = _unit((pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]))
        metal.append({"kind": "cyl", "center": mid, "axis": axis,
                      "half": rod_half, "r": NG30_ROD_RADIUS_MM})

    # 8 corner caps: sphere + 3 collar stubs (inner end at the corner).
    coff = NG30_COLLAR_LENGTH_MM / 2.0
    for c, pc in corners.items():
        metal.append({"kind": "sphere", "center": pc, "r": NG30_CAP_RADIUS_MM})
        for d in collar_dirs[c]:
            ctr = (pc[0] + d[0] * coff, pc[1] + d[1] * coff, pc[2] + d[2] * coff)
            metal.append({"kind": "cyl", "center": ctr, "axis": d,
                          "half": coff, "r": NG30_COLLAR_RADIUS_MM})

    # 24 split edge coils (two per edge, named by their near corner).
    for a, b in _EDGES:
        pa, pb = corners[a], corners[b]
        u = _unit((pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]))   # a → b
        for near, far, anchor, axis in (
            (a, b, pa, u), (b, a, pb, (-u[0], -u[1], -u[2])),
        ):
            ctr = (anchor[0] + axis[0] * cv_mid_s,
                   anchor[1] + axis[1] * cv_mid_s,
                   anchor[2] + axis[2] * cv_mid_s)
            coils.append({
                "name": f"e{near}{far}", "center": ctr, "axis": axis,
                "coil_half": cv_half, "coil_inner": cv_in, "coil_outer": cv_out,
                "weight": _edge_weight(near, far, NG30_COIL_CURRENTS),
                "has_coil": True,
            })

    # 6 face horseshoes (nested pipes + back washer) and their face coils.
    face_half = FRAME_EDGE_MM / 2.0
    r_io = NG30_HS_INNER_PIPE_OD_MM / 2.0
    r_ii = r_io - NG30_HS_WALL_THICKNESS_MM
    r_oo = NG30_HS_OUTER_PIPE_OD_MM / 2.0
    r_oi = r_oo - NG30_HS_WALL_THICKNESS_MM
    pipe_half = NG30_HS_LENGTH_MM / 2.0
    wash_half = NG30_HS_WASHER_THICKNESS_MM / 2.0
    cu_in = r_io + NG30_CU_CLEARANCE_FROM_HS_INNER_MM
    cu_out = min(cu_in + NG30_CU_WALL_THICKNESS_MM, r_oi - NG30_CU_CLEARANCE_FROM_HS_OUTER_MM)
    cu_half = (NG30_HS_LENGTH_MM + NG30_CU_EXTENSION_MM) / 2.0

    for facekey, n in _FACES:
        inward = (-n[0], -n[1], -n[2])
        # Pipe centre: face_half inward by pipe_half; washer sits behind the pipes.
        pc = tuple(n[i] * face_half + inward[i] * pipe_half for i in range(3))
        wc = tuple(n[i] * face_half + inward[i] * (NG30_HS_LENGTH_MM + wash_half)
                   for i in range(3))
        cc = tuple(n[i] * face_half + inward[i] * cu_half for i in range(3))
        metal.append({"kind": "tube", "center": pc, "axis": n,
                      "half": pipe_half, "r_in": r_ii, "r_out": r_io})    # inner pipe
        metal.append({"kind": "tube", "center": pc, "axis": n,
                      "half": pipe_half, "r_in": r_oi, "r_out": r_oo})    # outer pipe
        metal.append({"kind": "tube", "center": wc, "axis": n,
                      "half": wash_half, "r_in": r_ii, "r_out": r_oo})    # back washer
        coils.append({
            "name": facekey, "center": cc, "axis": n,
            "coil_half": cu_half, "coil_inner": cu_in, "coil_outer": cu_out,
            "weight": float(NG30_COIL_CURRENTS.get(facekey, 0.0)),
            "has_coil": True,
        })

    return metal, coils


# ── OCC geometry + Netgen mesh ────────────────────────────────────────────────

def _scale_coil(co: dict, s: float) -> dict:
    """Coil param dict scaled to mesh units (coil_mat set by the caller)."""
    return {
        "name": co["name"],
        "center": tuple(v * s for v in co["center"]), "axis": co["axis"],
        "coil_half": co["coil_half"] * s,
        "coil_inner": co["coil_inner"] * s, "coil_outer": co["coil_outer"] * s,
        "weight": co["weight"], "has_coil": co["has_coil"],
    }


def _occ_metal(prim, s, Cylinder, Sphere, Pnt, Dir):
    c = prim["center"]
    if prim["kind"] == "sphere":
        return Sphere(Pnt(c[0] * s, c[1] * s, c[2] * s), prim["r"] * s)
    ax = prim["axis"]
    half = prim["half"] * s
    base = Pnt(c[0] * s - ax[0] * half, c[1] * s - ax[1] * half, c[2] * s - ax[2] * half)
    d = Dir(ax[0], ax[1], ax[2])
    h = 2.0 * half
    if prim["kind"] == "cyl":
        return Cylinder(base, d, r=prim["r"] * s, h=h)
    return Cylinder(base, d, r=prim["r_out"] * s, h=h) - Cylinder(base, d, r=prim["r_in"] * s, h=h)


def build_frame_mesh(metal, coils, *, air_half_extent_mm, maxh_mm,
                     maxh_device_mm=None, length_scale=1.0):
    """Fuse the steel, build each coil, mesh inside one air box.

    Returns (ngmesh, coil_params, meta). coil_params are scaled to mesh units and
    each carries a unique "coil{i}" material so the solver sets J per region.
    """
    from netgen.occ import Cylinder, Sphere, Box, Pnt, Dir, Glue, OCCGeometry

    s = float(length_scale)
    md = None if maxh_device_mm is None else float(maxh_device_mm) * s

    # Union all steel primitives into one body (pairwise + measured faster here
    # than a one-shot Fuse for this ~60-solid frame).
    steel = reduce(lambda x, y: x + y,
                   (_occ_metal(p, s, Cylinder, Sphere, Pnt, Dir) for p in metal))
    steel.mat("steel")
    if md is not None:
        steel.maxh = md

    coil_solids = []
    coil_params = []
    for i, co in enumerate(coils):
        ax = co["axis"]
        c = co["center"]
        half = co["coil_half"] * s
        base = Pnt(c[0] * s - ax[0] * half, c[1] * s - ax[1] * half, c[2] * s - ax[2] * half)
        d = Dir(ax[0], ax[1], ax[2])
        h = 2.0 * half
        tube = (Cylinder(base, d, r=co["coil_outer"] * s, h=h)
                - Cylinder(base, d, r=co["coil_inner"] * s, h=h))
        mat = f"coil{i}"
        tube.mat(mat)
        if md is not None:
            tube.maxh = md
        coil_solids.append(tube)
        cp = _scale_coil(co, s)
        cp["coil_mat"] = mat
        coil_params.append(cp)

    h = float(air_half_extent_mm) * s
    box = Box(Pnt(-h, -h, -h), Pnt(h, h, h))
    box.faces.name = "outer"
    air = box - steel
    for cs in coil_solids:
        air = air - cs
    air.mat("air")

    geo = OCCGeometry(Glue([steel] + coil_solids + [air]))
    ngmesh = geo.GenerateMesh(maxh=float(maxh_mm) * s)
    meta = {"half_extent": h, "length_scale": s}
    return ngmesh, coil_params, meta


# ── Geometric surface classification ──────────────────────────────────────────

def _inside_metal(prim, p, eps) -> bool:
    c = prim["center"]
    dx, dy, dz = p[0] - c[0], p[1] - c[1], p[2] - c[2]
    if prim["kind"] == "sphere":
        return dx * dx + dy * dy + dz * dz <= (prim["r"] + eps) ** 2
    ax = prim["axis"]
    t = dx * ax[0] + dy * ax[1] + dz * ax[2]
    if abs(t) > prim["half"] + eps:
        return False
    rx, ry, rz = dx - t * ax[0], dy - t * ax[1], dz - t * ax[2]
    r = math.sqrt(rx * rx + ry * ry + rz * rz)
    if prim["kind"] == "cyl":
        return r <= prim["r"] + eps
    return prim["r_in"] - eps <= r <= prim["r_out"] + eps


def _inside_coil(co, p, eps) -> bool:
    c = co["center"]
    ax = co["axis"]
    dx, dy, dz = p[0] - c[0], p[1] - c[1], p[2] - c[2]
    t = dx * ax[0] + dy * ax[1] + dz * ax[2]
    if abs(t) > co["coil_half"] + eps:
        return False
    rx, ry, rz = dx - t * ax[0], dy - t * ax[1], dz - t * ax[2]
    r = math.sqrt(rx * rx + ry * ry + rz * rz)
    return co["coil_inner"] - eps <= r <= co["coil_outer"] + eps


def _classify(p, metal, coil_params, eps):
    for prim in metal:
        if _inside_metal(prim, p, eps):
            return "steel"
    for co in coil_params:
        if _inside_coil(co, p, eps):
            return "coil"
    return "air"


def extract_surface(ngmesh, metal, coil_params, sc, eps=0.3):
    """Vertices (scene units) + steel/coil/air triangle lists."""
    verts = []
    pts = []
    for mp in ngmesh.Points():
        x, y, z = mp.p[0], mp.p[1], mp.p[2]
        pts.append((x, y, z))
        verts.append([round(x * sc, 4), round(y * sc, 4), round(z * sc, 4)])
    n_pts = len(verts)

    tris = {"steel": [], "coil": [], "air": []}
    for el in ngmesh.Elements2D():
        vs = el.vertices
        idx = [v.nr - 1 for v in vs]
        if not all(0 <= i < n_pts for i in idx):
            continue
        tri = idx[:3]
        cx = (pts[tri[0]][0] + pts[tri[1]][0] + pts[tri[2]][0]) / 3.0
        cy = (pts[tri[0]][1] + pts[tri[1]][1] + pts[tri[2]][1]) / 3.0
        cz = (pts[tri[0]][2] + pts[tri[1]][2] + pts[tri[2]][2]) / 3.0
        region = _classify((cx, cy, cz), metal, coil_params, eps)
        tris[region].append(tri)
        if len(vs) == 4:
            tris[region].append([idx[0], idx[2], idx[3]])
    return verts, tris


# ── Scene assembly ────────────────────────────────────────────────────────────

def build_geometry(length_scale: float = 1.0):
    """Build the frame OCC model + mesh. Returns (ngmesh, coil_params, meta)."""
    metal, coils = build_specs()
    return build_frame_mesh(
        metal, coils,
        air_half_extent_mm=_air_half_extent_mm(),
        maxh_mm=NG_MESH_MAXH_MM, maxh_device_mm=NG_MESH_MAXH_DEVICE_MM,
        length_scale=length_scale,
    )


def _assemble_payload():
    from cube_config import MM_TO_SCENE, FRAME_INSET_MM
    from scene_render import frame_config_dict

    sc = MM_TO_SCENE
    metal, coils = build_specs()
    corners = cube_corner_positions(NG_CUBE_HALF_MM)
    frame_config = frame_config_dict(
        edge_mm=FRAME_EDGE_MM, height_mm=FRAME_EDGE_MM, inset_mm=FRAME_INSET_MM,
        corner_pos_mm=corners, coil_weights=NG30_COIL_CURRENTS, sc=sc,
    )

    # Tag coils with a material so dipole_arrows / classifier see a stable list,
    # then build arrows (no mesh needed → survive a mesh failure).
    for i, co in enumerate(coils):
        co["coil_mat"] = f"coil{i}"
    arrow_vs = round(NG30_ROD_RADIUS_MM * 0.15 * sc, 4)
    cu = dipole_arrows(coils, sc)

    scene = {
        "type": "fea_mesh", "scene_id": "30coils_ng",
        "frame_config": frame_config, "voxel_size": arrow_vs,
        "vertices": [], "cu": cu, "regions": [], "meta": {},
    }

    build_s = 0.0
    try:
        t0 = time.perf_counter()
        ngmesh, coil_params, _meta_g = build_frame_mesh(
            metal, coils, air_half_extent_mm=_air_half_extent_mm(),
            maxh_mm=NG_MESH_MAXH_MM, maxh_device_mm=NG_MESH_MAXH_DEVICE_MM,
            length_scale=1.0,
        )
        verts, tris = extract_surface(ngmesh, metal, coil_params, sc)
        build_s = time.perf_counter() - t0
        st, co_t, ai = tris["steel"], tris["coil"], tris["air"]
        scene["vertices"] = verts
        scene["regions"] = [
            {"name": "steel", "color": list(STEEL_COLOR), "triangles": st,
             "solid_opacity": STEEL_OPACITY[0], "wire_opacity": STEEL_OPACITY[1]},
            {"name": "coil", "color": list(COIL_COLOR), "triangles": co_t,
             "solid_opacity": COIL_OPACITY[0], "wire_opacity": COIL_OPACITY[1]},
            {"name": "air", "color": list(AIR_COLOR), "triangles": ai,
             "solid_opacity": AIR_OPACITY[0], "wire_opacity": AIR_OPACITY[1]},
        ]
        scene["meta"] = {
            "n_points": len(verts),
            "n_tris": len(st) + len(co_t) + len(ai),
            "n_steel_tris": len(st), "n_coil_tris": len(co_t), "n_air_tris": len(ai),
            "air_box_mm": round(2.0 * _air_half_extent_mm(), 2),
            "maxh_mm": NG_MESH_MAXH_MM, "maxh_device_mm": NG_MESH_MAXH_DEVICE_MM,
            "mesh_s": round(build_s, 2),
        }
    except Exception as exc:  # noqa: BLE001 — keep frame + arrows; report failure
        scene["meta"] = {"error": f"{type(exc).__name__}: {exc}"}

    return scene, build_s


def build_scene(force: bool = False, fea_strength_scale: float = 1.0):
    global _scene_cache
    if _scene_cache is not None and not force:
        return _scene_cache

    scene, _build_s = _assemble_payload()
    n_active = sum(1 for v in NG30_COIL_CURRENTS.values() if abs(float(v)) > 1e-9)
    m = scene["meta"]
    if m.get("error"):
        print(f"[ng] 30coils mesh build FAILED: {m['error']}")
    else:
        m.update({
            "n_coils": 30, "n_active_corner_face_keys": n_active,
            "rod_radius_mm": NG30_ROD_RADIUS_MM, "rod_length_mm": NG30_ROD_LENGTH_MM,
            "air_padding_mm": NG_AIR_PADDING_MM,
        })
        print(
            f"[ng] scene=30coils_ng  coils=30 (24 edge + 6 face)  "
            f"air_pad={NG_AIR_PADDING_MM}mm (box {m['air_box_mm']:.0f}mm)  maxh={NG_MESH_MAXH_MM}mm  "
            f"points={m['n_points']:,}  steel={m['n_steel_tris']:,}  coil={m['n_coil_tris']:,}  "
            f"air={m['n_air_tris']:,}  {m['mesh_s']}s"
        )

    if force or fea_strength_scale == 1.0:
        _scene_cache = scene
    return scene
