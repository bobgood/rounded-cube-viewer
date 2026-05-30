"""ng_dipoles.py — Flexible dipole geometry/mesh builder for NGSolve scenes.

A "dipole" here = one steel rod + one coaxial solenoid coil, placed ANYWHERE in
space (not necessarily corner-to-corner) with an arbitrary axis, name and signed
current weight. Scenes assemble a list of DipoleSpec and call:

    ngmesh, params = build_dipole_mesh(specs, air_half_extent_mm, ...)
    verts, tris    = extract_surface(ngmesh, params, sc)   # steel/coil/air tris
    cu             = dipole_arrows(params, sc)              # Cu-format coil arrows

The module is self-contained: it depends only on cube_config / ng_config and
NGSolve's Netgen mesher — NONE of the fea_* pipeline — so it can outlive those
files. Surface triangles are classified GEOMETRICALLY (by testing each triangle
centroid against the analytic rod/coil shapes), which works for any number of
bodies without relying on Netgen domain/material bookkeeping.

Conventions
-----------
- A spec's `axis` is a unit vector pointing toward the dipole's "positive" end;
  a positive `weight` drives B along +axis. For cube edges e{a}{b} the axis
  points toward the FIRST-named corner a (B toward a), matching coil_init.
- All lengths are in mm. `length_scale` multiplies geometry at build time only
  (1.0 = render mesh in mm; 1e-3 = solver mesh in metres for real Tesla).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ng_config import NG_CUBE_HALF_MM


# Region appearance (RGB 0..1) — steel cool grey, coil warm amber, air faint blue.
STEEL_COLOR = (0.80, 0.82, 0.85)
COIL_COLOR = (1.00, 0.72, 0.12)
# Air: light, airy blue so the far box reads as a faint ghost rather than a dark cage.
AIR_COLOR = (0.62, 0.80, 1.00)
COIL_COLOR_NEGATIVE = (0.35, 0.88, 1.00)

# Per-region render opacities (solid, wire), matched to the 1-dipole scene.
STEEL_OPACITY = (0.18, 0.75)
COIL_OPACITY = (0.18, 0.75)
# Air: clearly visible but LIGHT (the light-blue colour keeps it from reading
# dark even at this wire opacity). Scaled further by the Mesh slider.
AIR_OPACITY = (0.03, 0.22)


@dataclass
class DipoleSpec:
    """One rod + coil, placed by center + axis (fully general, mm)."""
    name: str
    center_mm: tuple                # (x, y, z) midpoint of the rod
    axis: tuple                     # unit vector toward the +polarity end
    rod_length_mm: float
    rod_radius_mm: float
    coil_inner_mm: float
    coil_outer_mm: float
    coil_length_mm: float
    weight: float = 1.0             # signed current; +→B along +axis; 0→no arrows
    has_coil: bool = True           # build the coil body in the mesh


# ── Cube frame (self-contained; mirrors geometry_ids corner numbering) ─────────

def cube_corner_positions(half: float = NG_CUBE_HALF_MM) -> dict:
    """8 skeleton corners c1..c8 at +/- half on each axis.

    Numbering matches geometry_ids (CORNER_BY_K_TOP) so edge labels e{a}{b}
    line up with coil_init / the old voxel scenes:
        c1(+,+,+) c2(+,-,+) c3(-,-,+) c4(-,+,+)
        c5(+,+,-) c6(+,-,-) c7(-,-,-) c8(-,+,-)
    """
    h = float(half)
    return {
        1: (h, h, h), 2: (h, -h, h), 3: (-h, -h, h), 4: (-h, h, h),
        5: (h, h, -h), 6: (h, -h, -h), 7: (-h, -h, -h), 8: (-h, h, -h),
    }


def edge_corner_ids(edge: str) -> tuple:
    """('e15' -> (1, 5)).  First id is the +polarity corner."""
    s = edge.strip().lower().lstrip("e")
    return int(s[0]), int(s[1])


def _unit(v: tuple) -> tuple:
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n < 1e-12:
        return (1.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def perp_basis(u: tuple):
    """Two unit vectors spanning the plane perpendicular to u."""
    ux, uy, uz = u
    rx, ry, rz = (0.0, 0.0, 1.0) if abs(uz) < 0.9 else (1.0, 0.0, 0.0)
    vx, vy, vz = uy * rz - uz * ry, uz * rx - ux * rz, ux * ry - uy * rx
    vl = math.sqrt(vx * vx + vy * vy + vz * vz)
    vx, vy, vz = vx / vl, vy / vl, vz / vl
    wx, wy, wz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    wl = math.sqrt(wx * wx + wy * wy + wz * wz)
    return (vx, vy, vz), (wx / wl, wy / wl, wz / wl)


def edge_dipole_specs(
    edges: dict,
    *,
    rod_radius_mm: float,
    coil_clearance_mm: float,
    coil_thickness_mm: float,
    rod_length_mm: float,
    coil_length_mm: float,
    half: float = NG_CUBE_HALF_MM,
) -> list:
    """Build DipoleSpecs centred on cube edges from a {edge: weight} dict.

    Each rod is centred on its edge midpoint, axis pointing toward the first
    corner of the edge label. Rod/coil lengths are taken from the args (shorter
    than the edge so neighbouring dipoles don't collide at the corners).
    """
    corners = cube_corner_positions(half)
    coil_inner = rod_radius_mm + coil_clearance_mm
    coil_outer = coil_inner + coil_thickness_mm
    specs = []
    for edge, weight in edges.items():
        a, b = edge_corner_ids(edge)
        pa, pb = corners[a], corners[b]
        center = tuple((pa[i] + pb[i]) / 2.0 for i in range(3))
        axis = _unit((pa[0] - pb[0], pa[1] - pb[1], pa[2] - pb[2]))  # toward a
        specs.append(DipoleSpec(
            name=edge, center_mm=center, axis=axis,
            rod_length_mm=rod_length_mm, rod_radius_mm=rod_radius_mm,
            coil_inner_mm=coil_inner, coil_outer_mm=coil_outer,
            coil_length_mm=coil_length_mm, weight=float(weight),
        ))
    return specs


# ── OCC geometry + Netgen mesh ────────────────────────────────────────────────

def specs_to_params(specs: list, length_scale: float = 1.0) -> list:
    """Per-dipole placement dicts (scaled by length_scale) — no meshing.

    These describe each dipole's coil material name, center, axis and rod/coil
    extents in the chosen units, and drive extract_surface / dipole_arrows / the
    solver's per-coil J. Computing them without OCC lets arrows + frame render
    even if meshing fails.
    """
    s = float(length_scale)
    out = []
    for i, sp in enumerate(specs):
        out.append({
            "name": sp.name,
            "coil_mat": f"coil{i}",     # distinct per coil so the solver sets J per region
            "center": tuple(v * s for v in sp.center_mm),
            "axis": sp.axis,
            "rod_half": sp.rod_length_mm * s / 2.0,
            "rod_radius": sp.rod_radius_mm * s,
            "coil_half": sp.coil_length_mm * s / 2.0,
            "coil_inner": sp.coil_inner_mm * s,
            "coil_outer": sp.coil_outer_mm * s,
            "weight": sp.weight,
            "has_coil": sp.has_coil,
        })
    return out


def build_dipole_mesh(
    specs: list,
    *,
    air_half_extent_mm: float,
    maxh_mm: float,
    maxh_device_mm=None,
    length_scale: float = 1.0,
):
    """Build all rods + coils inside one air box and mesh it.

    Returns (ngmesh, params, meta) where params is specs_to_params(...) in the
    SAME scaled units as the mesh (used by extract_surface / dipole_arrows / the
    solver), and meta carries the air half-extent and length_scale.
    """
    from netgen.occ import Cylinder, Box, Pnt, Dir, Glue, OCCGeometry

    s = float(length_scale)
    params = specs_to_params(specs, s)
    bodies = []

    for dp, sp in zip(params, specs):
        ax = Dir(sp.axis[0], sp.axis[1], sp.axis[2])
        c = dp["center"]
        rod_h = sp.rod_length_mm * s
        rod_base = Pnt(
            c[0] - sp.axis[0] * rod_h / 2.0,
            c[1] - sp.axis[1] * rod_h / 2.0,
            c[2] - sp.axis[2] * rod_h / 2.0,
        )
        rod = Cylinder(rod_base, ax, r=sp.rod_radius_mm * s, h=rod_h)
        rod.mat("steel")
        if maxh_device_mm is not None:
            rod.maxh = float(maxh_device_mm) * s
        bodies.append(rod)

        if sp.has_coil:
            coil_h = sp.coil_length_mm * s
            coil_base = Pnt(
                c[0] - sp.axis[0] * coil_h / 2.0,
                c[1] - sp.axis[1] * coil_h / 2.0,
                c[2] - sp.axis[2] * coil_h / 2.0,
            )
            coil = (
                Cylinder(coil_base, ax, r=sp.coil_outer_mm * s, h=coil_h)
                - Cylinder(coil_base, ax, r=sp.coil_inner_mm * s, h=coil_h)
            )
            coil.mat(dp["coil_mat"])
            if maxh_device_mm is not None:
                coil.maxh = float(maxh_device_mm) * s
            bodies.append(coil)

    h = float(air_half_extent_mm) * s
    box = Box(Pnt(-h, -h, -h), Pnt(h, h, h))
    box.faces.name = "outer"          # far-field boundary for the solver
    air = box
    for b in bodies:
        air = air - b
    air.mat("air")

    geo = OCCGeometry(Glue(bodies + [air]))
    ngmesh = geo.GenerateMesh(maxh=float(maxh_mm) * s)
    meta = {"half_extent": h, "length_scale": s}
    return ngmesh, params, meta


# ── Geometric surface classification ──────────────────────────────────────────

def _classify(p, params, eps: float):
    """Return 'steel' | 'coil' | 'air' for a triangle centroid p (mesh units)."""
    for dp in params:
        cx, cy, cz = dp["center"]
        ax, ay, az = dp["axis"]
        dx, dy, dz = p[0] - cx, p[1] - cy, p[2] - cz
        t = dx * ax + dy * ay + dz * az            # axial coordinate
        rx, ry, rz = dx - t * ax, dy - t * ay, dz - t * az
        r = math.sqrt(rx * rx + ry * ry + rz * rz)  # radial distance
        if abs(t) <= dp["rod_half"] + eps and r <= dp["rod_radius"] + eps:
            return "steel"
        if (dp["has_coil"] and abs(t) <= dp["coil_half"] + eps
                and dp["coil_inner"] - eps <= r <= dp["coil_outer"] + eps):
            return "coil"
    return "air"


def extract_surface(ngmesh, params, sc: float, eps: float = 0.3):
    """Vertices (scaled to scene units) + triangle lists per render region.

    Triangles are bucketed by classifying their centroid against the analytic
    dipole shapes — robust for any number of bodies. `eps` (mm in mesh units)
    absorbs the chord deflection of the faceted cylinders.
    """
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
        region = _classify((cx, cy, cz), params, eps)
        tris[region].append(tri)
        if len(vs) == 4:  # quad → second triangle
            quad = [idx[0], idx[2], idx[3]]
            tris[region].append(quad)

    return verts, tris


# ── Shared scene payload assembly (used by every NGSolve dipole scene) ─────────

def assemble_scene_payload(
    scene_id: str,
    specs: list,
    coil_weights: dict,
    *,
    air_half_extent_mm: float,
    maxh_mm: float,
    maxh_device_mm=None,
    arrow_radius_mm: float,
    half: float = NG_CUBE_HALF_MM,
    sc=None,
):
    """Mesh the specs and pack the full "fea_mesh" payload the viewer renders.

    Shared by the 1-dipole and 12-dipole scenes (and any future dipole scene):
    builds the Ou frame_config, the Netgen surface mesh (steel/coil/air region
    triangles), and the coil current arrows. Returns (scene, params, build_s).
    Raises on mesh failure; callers wrap to keep the server crash-proof.
    """
    import time
    from cube_config import MM_TO_SCENE, FRAME_EDGE_MM, FRAME_INSET_MM
    from scene_render import frame_config_dict

    sc = MM_TO_SCENE if sc is None else sc
    corners = cube_corner_positions(half)
    frame_config = frame_config_dict(
        edge_mm=FRAME_EDGE_MM, height_mm=FRAME_EDGE_MM, inset_mm=FRAME_INSET_MM,
        corner_pos_mm=corners, coil_weights=coil_weights, sc=sc,
    )
    arrow_vs = round(arrow_radius_mm * 0.15 * sc, 4)

    # Arrows + frame need no mesh, so build them first → they survive a mesh fail.
    cu = dipole_arrows(specs_to_params(specs, 1.0), sc)

    scene = {
        "type": "fea_mesh",
        "scene_id": scene_id,
        "frame_config": frame_config,
        "voxel_size": arrow_vs,
        "vertices": [],
        "cu": cu,
        "regions": [],
        "meta": {},
    }

    build_s = 0.0
    try:
        t0 = time.perf_counter()
        ngmesh, params, _meta_g = build_dipole_mesh(
            specs, air_half_extent_mm=air_half_extent_mm, maxh_mm=maxh_mm,
            maxh_device_mm=maxh_device_mm, length_scale=1.0,
        )
        verts, tris = extract_surface(ngmesh, params, sc)
        build_s = time.perf_counter() - t0

        steel_tris, coil_tris, air_tris = tris["steel"], tris["coil"], tris["air"]
        scene["vertices"] = verts
        scene["regions"] = [
            {"name": "steel", "color": list(STEEL_COLOR), "triangles": steel_tris,
             "solid_opacity": STEEL_OPACITY[0], "wire_opacity": STEEL_OPACITY[1]},
            {"name": "coil",  "color": list(COIL_COLOR),  "triangles": coil_tris,
             "solid_opacity": COIL_OPACITY[0],  "wire_opacity": COIL_OPACITY[1]},
            {"name": "air",   "color": list(AIR_COLOR),   "triangles": air_tris,
             "solid_opacity": AIR_OPACITY[0],   "wire_opacity": AIR_OPACITY[1]},
        ]
        scene["meta"] = {
            "n_points": len(verts),
            "n_tris": len(steel_tris) + len(coil_tris) + len(air_tris),
            "n_steel_tris": len(steel_tris),
            "n_coil_tris": len(coil_tris),
            "n_air_tris": len(air_tris),
            "air_box_mm": round(2.0 * air_half_extent_mm, 2),
            "maxh_mm": maxh_mm,
            "maxh_device_mm": maxh_device_mm,
            "mesh_s": round(build_s, 2),
        }
    except Exception as exc:  # noqa: BLE001 — keep frame + arrows; report the failure
        scene["meta"] = {"error": f"{type(exc).__name__}: {exc}"}

    return scene, build_s


# ── Coil current arrows (Cu-format) ───────────────────────────────────────────

def dipole_arrows(params, sc: float, *, n_axial: int = 5, n_phi: int = 8) -> dict:
    """Azimuthal current arrows around each nonzero-weight coil.

    Amplitude is the SIGN of the weight (±1) — the viewer colours by polarity,
    not magnitude. Weight 0 contributes no arrows.
    """
    positions, directions, amplitudes = [], [], []
    for dp in params:
        w = float(dp["weight"])
        if abs(w) < 1e-9 or not dp["has_coil"]:
            continue
        ax = dp["axis"]
        (vx, vy, vz), (wx, wy, wz) = perp_basis(ax)
        cx, cy, cz = dp["center"]
        r_mid = (dp["coil_inner"] + dp["coil_outer"]) / 2.0
        half = dp["coil_half"]
        pol = 1.0 if w > 0 else -1.0
        for i in range(n_axial):
            t = -half + (2.0 * half) * (i + 0.5) / n_axial
            bx, by, bz = cx + t * ax[0], cy + t * ax[1], cz + t * ax[2]
            for k in range(n_phi):
                phi = 2.0 * math.pi * k / n_phi
                cp, sp_ = math.cos(phi), math.sin(phi)
                # radial unit vector in the perpendicular plane
                rxu = cp * vx + sp_ * wx
                ryu = cp * vy + sp_ * wy
                rzu = cp * vz + sp_ * wz
                # azimuthal tangent = axis × r_hat (winding direction)
                txd = ax[1] * rzu - ax[2] * ryu
                tyd = ax[2] * rxu - ax[0] * rzu
                tzd = ax[0] * ryu - ax[1] * rxu
                positions.append([
                    round((bx + r_mid * rxu) * sc, 4),
                    round((by + r_mid * ryu) * sc, 4),
                    round((bz + r_mid * rzu) * sc, 4),
                ])
                directions.append([round(txd * pol, 4), round(tyd * pol, 4), round(tzd * pol, 4)])
                amplitudes.append(pol)

    return {
        "sites": {
            "positions": positions,
            "directions": directions,
            "amplitudes": amplitudes,
        },
        "objects": [],
        "color_positive": list(COIL_COLOR),
        "color_negative": list(COIL_COLOR_NEGATIVE),
    }
