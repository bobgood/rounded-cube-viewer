"""scene_12dipoles.py — All 12 cube edges, each with a dipole rod + solenoid coil.

Current convention (matches scene_dipole.py):
  positive coil weight → B points toward the FIRST named corner of the edge.
  e.g. e12 weight=+1 → B points toward c1.
"""

from __future__ import annotations

import math
import time

from cube_config import FRAME_EDGE_MM, FRAME_INSET_MM, MM_TO_SCENE
from fea_config import (
    VOXEL_SIZE_MM,
    FRAME_GAP_MM,
    CYLINDER_COLOR,
    FEA_GRID_PAD_MM,
    FEA_METAL_MATERIAL_ID,
    FEA_METAL_MU_R,
    FEA_COIL_MATERIAL_ID,
    FEA_COIL_MU_R,
    FEA_CURRENT_NOM_A_MM2,
    FEA_SOLVE_ENABLED,
    DIPOLE_ROD_RADIUS_MM,
    DIPOLE_ROD_END_GAP_MM,
    DIPOLE_COIL_CLEARANCE_MM,
    DIPOLE_COIL_THICKNESS_MM,
    COIL_ARROW_COLOR_POSITIVE,
    COIL_ARROW_COLOR_NEGATIVE,
)
from coil_init import edge_coil_weight, export_coil_table
from fea_grid import build_fea_grid
from fea_solve import solve_magnetostatic
from geometry_ids import normalize_edge_key

import fea_model as _fm
from fea_model import (
    _skeleton_dims,
    _cube_corner_positions_mm,
    _cylinder_voxels_x,
    _annulus_cylinder_voxels_x,
    _translate,
    _perp_basis,
)
from scene_dipole import (
    _edge_endpoints_mm,
    _axis_unit,
    _azimuthal_tangent,
    _arrow_sites,
)
from scene_render import fea_grid_payload, frame_config_dict, scene_point_mm, to_scene_mm

# All 12 directed cube edges. Positive weight → B toward the first-named corner.
# Top ring (z=+11):    e12, e23, e34, e41
# Bottom ring (z=-11): e56, e67, e78, e85
# Vertical struts:     e15, e26, e37, e48
ALL_12_EDGES: tuple[str, ...] = (
    "e12", "e23", "e34", "e41",
    "e56", "e67", "e78", "e85",
    "e15", "e26", "e37", "e48",
)

_scene_cache = None


def _dipole_rod_length_mm() -> float:
    """Rod/coil axial length from outer cube envelope (mm).

    length = FRAME_EDGE_MM - 4*rod_radius - 4*coil_thickness - gap
    (4x terms = two ends, each reserving 2*radius and 2*coil thickness at corners)
    """
    gap = max(float(DIPOLE_ROD_END_GAP_MM), float(FRAME_GAP_MM))
    return max(
        VOXEL_SIZE_MM,
        float(FRAME_EDGE_MM)
        - 4.0 * float(DIPOLE_ROD_RADIUS_MM)
        - 4.0 * float(DIPOLE_COIL_THICKNESS_MM)
        - gap,
    )


def _trim_dipole_edge(p1_full, p2_full) -> tuple[tuple, tuple, float]:
    """Center rod/coil on skeleton edge at the envelope-derived length."""
    dx = p2_full[0] - p1_full[0]
    dy = p2_full[1] - p1_full[1]
    dz = p2_full[2] - p1_full[2]
    full_len = math.sqrt(dx * dx + dy * dy + dz * dz)
    if full_len < 1e-9:
        return p1_full, p2_full, 0.0

    length_mm = min(_dipole_rod_length_mm(), full_len - VOXEL_SIZE_MM)
    length_mm = max(VOXEL_SIZE_MM, length_mm)
    half_trim = (full_len - length_mm) / 2.0
    frac = half_trim / full_len
    p1 = tuple(p1_full[i] + frac * (p2_full[i] - p1_full[i]) for i in range(3))
    p2 = tuple(p2_full[i] - frac * (p2_full[i] - p1_full[i]) for i in range(3))
    length_mm = math.hypot(p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
    return p1, p2, length_mm


# ── General 3D helpers ────────────────────────────────────────────────────────

def _voxels_along_edge_3d(p1, p2, length_mm, r_outer_mm, r_inner_mm=None):
    """Solid or annular cylinder along p1→p2 for any 3D orientation.

    Builds an X-axis template then rotates to align with the edge direction
    using an orthonormal frame from _perp_basis.
    """
    mx, my, mz = (p1[0]+p2[0])/2, (p1[1]+p2[1])/2, (p1[2]+p2[2])/2
    ux, uy, uz = _axis_unit(p1, p2, length_mm)
    tpl = (
        _cylinder_voxels_x(length_mm, r_outer_mm)
        if r_inner_mm is None
        else _annulus_cylinder_voxels_x(length_mm, r_outer_mm, r_inner_mm)
    )
    basis = _perp_basis((ux, uy, uz))
    if basis is None:
        return _translate(tpl, mx, my, mz)
    (vx, vy, vz), (wx, wy, wz) = basis
    rotated = [
        (x * ux + y * vx + z * wx,
         x * uy + y * vy + z * wy,
         x * uz + y * vz + z * wz)
        for (x, y, z) in tpl
    ]
    return _translate(rotated, mx, my, mz)


def _coil_j_voxels_3d(p1, p2, length_mm, weight: float) -> list:
    """Coil sleeve with azimuthal J for any 3D edge orientation."""
    w = float(weight)
    if abs(w) < 1e-9:
        return []
    r_in = DIPOLE_ROD_RADIUS_MM + DIPOLE_COIL_CLEARANCE_MM
    r_out = r_in + DIPOLE_COIL_THICKNESS_MM
    vox = _voxels_along_edge_3d(p1, p2, length_mm, r_out, r_in)
    ux, uy, uz = _axis_unit(p1, p2, length_mm)
    j_sign = 1.0 if w >= 0 else -1.0
    j_scale = abs(w) * FEA_CURRENT_NOM_A_MM2
    out = []
    for (x, y, z) in vox:
        dx, dy, dz = x - p1[0], y - p1[1], z - p1[2]
        t = dx * ux + dy * uy + dz * uz
        rx, ry, rz = dx - t * ux, dy - t * uy, dz - t * uz
        tang = _azimuthal_tangent(ux, uy, uz, rx, ry, rz)
        if tang is None:
            continue
        tx, ty, tz = tang
        s = j_sign * j_scale
        out.append((x, y, z, tx * s, ty * s, tz * s, w))
    return out


# ── Scene builder ─────────────────────────────────────────────────────────────

def build_12dipoles_scene(force: bool = False, fea_strength_scale: float = 1.0):
    global _scene_cache
    if _scene_cache is not None and not force and fea_strength_scale == 1.0:
        return _scene_cache

    E = FRAME_EDGE_MM
    H = FRAME_EDGE_MM
    ins = FRAME_INSET_MM
    sk = _skeleton_dims(E, H, ins, 4, FRAME_GAP_MM)
    vertices = sk["vertices"]
    half_h = sk["half_h"]
    corner_pos_mm = _cube_corner_positions_mm(vertices, half_h)

    all_cyl_raw: list = []
    all_coil_voxels: list = []
    cyl_objects: list = []
    cv_objects: list = []
    cv_all_pos: list = []
    cv_all_dir: list = []
    cv_all_amp: list = []
    cyl_offset = 0
    cv_offset = 0

    active_edges = []

    p_sample1, p_sample2 = _edge_endpoints_mm(vertices, half_h, ALL_12_EDGES[0])
    _, _, rod_len_mm = _trim_dipole_edge(p_sample1, p_sample2)

    for edge_id_raw in ALL_12_EDGES:
        edge_id = normalize_edge_key(edge_id_raw)
        weight = max(-1.0, min(1.0,
            float(edge_coil_weight(edge_id)) * float(fea_strength_scale)))

        p1_full, p2_full = _edge_endpoints_mm(vertices, half_h, edge_id)
        p1, p2, length_mm = _trim_dipole_edge(p1_full, p2_full)
        cyl_raw = _voxels_along_edge_3d(p1, p2, length_mm, DIPOLE_ROD_RADIUS_MM)
        all_cyl_raw.extend(cyl_raw)

        c1_id = int(edge_id[1])
        c2_id = int(edge_id[2])
        cyl_objects.append({
            "id": f"cy_{edge_id}",
            "label": edge_id,
            "edge": edge_id,
            "corners": [c1_id, c2_id],
            "ends": [scene_point_mm(*p1, 1.0), scene_point_mm(*p2, 1.0)],
            "start": cyl_offset,
            "count": len(cyl_raw),
        })
        cyl_offset += len(cyl_raw)

        if abs(weight) > 1e-9:
            active_edges.append(edge_id)
            coil_voxels = _coil_j_voxels_3d(p1, p2, length_mm, weight)
            all_coil_voxels.extend(coil_voxels)

            a_pos, a_dir, a_amp = _arrow_sites(p1, p2, weight)
            cv_objects.append({
                "id": f"cv_{edge_id}",
                "label": edge_id,
                "edge": edge_id,
                "coil_key": edge_id,
                "corners": [c1_id, c2_id],
                "start": cv_offset,
                "count": len(a_pos),
                "amplitude": round(weight, 4),
            })
            cv_all_pos.extend(a_pos)
            cv_all_dir.extend(a_dir)
            cv_all_amp.extend(a_amp)
            cv_offset += len(a_pos)

    _fm._last_fea_inputs = {
        "cyl_raw": all_cyl_raw,
        "cap_raw": [],
        "plate_raw": [],
        "hs_raw": [],
        "coil_voxels": all_coil_voxels,
        "outer_edge_mm": E,
        "outer_height_mm": H,
    }

    fea_grid = build_fea_grid(
        all_cyl_raw, [], [], [],
        coil_voxels=all_coil_voxels,
        outer_edge_mm=E,
        outer_height_mm=H,
        voxel_size_mm=VOXEL_SIZE_MM,
        pad_mm=FEA_GRID_PAD_MM,
        steel_material_id=FEA_METAL_MATERIAL_ID,
        steel_mu_r=FEA_METAL_MU_R,
        coil_material_id=FEA_COIL_MATERIAL_ID,
        coil_mu_r=FEA_COIL_MU_R,
    )

    cells = fea_grid["cells"]
    print(
        f"[fea] scene=12dipoles  active={active_edges}  rods=12  "
        f"rod_len={rod_len_mm:.1f}mm  (32 - 4*r - 4*t - gap)\n"
        f"[fea] FEA grid {fea_grid['size'][0]}x{fea_grid['size'][1]}x{fea_grid['size'][2]}  "
        f"steel={cells['steel_count']:,}  coil+J={cells['coil_count']:,}"
    )

    if FEA_SOLVE_ENABLED:
        t0 = time.perf_counter()
        bfield = solve_magnetostatic(fea_grid)
        fea_grid["B_field"] = {"max_T": bfield["meta"]["max_B_T"],
                               "solve_meta": bfield["meta"]}
        print(f"[fea] B solve {time.perf_counter()-t0:.2f}s")

    sc = MM_TO_SCENE
    grid_payload = fea_grid_payload(fea_grid, sc)

    scene = {
        "type": "voxel_scene",
        "scene_id": "12dipoles",
        "voxel_size": round(VOXEL_SIZE_MM * sc, 4),
        "frame_config": frame_config_dict(
            edge_mm=E, height_mm=H, inset_mm=ins,
            corner_pos_mm=corner_pos_mm,
            coil_weights=export_coil_table(),
            sc=sc,
        ),
        "cylinders": {
            "color": list(CYLINDER_COLOR),
            "objects": cyl_objects,
            "positions": to_scene_mm(all_cyl_raw, sc),
        },
        "caps": {"color": list(CYLINDER_COLOR), "objects": [], "positions": []},
        "coil": {
            "weights": export_coil_table(),
            "color_positive": list(COIL_ARROW_COLOR_POSITIVE),
            "color_negative": list(COIL_ARROW_COLOR_NEGATIVE),
            "groups": {e: f"{normalize_edge_key(e)} dipole" for e in ALL_12_EDGES},
        },
        "cv": {
            "objects": cv_objects,
            "color_positive": list(COIL_ARROW_COLOR_POSITIVE),
            "color_negative": list(COIL_ARROW_COLOR_NEGATIVE),
            "sites": {
                "positions": to_scene_mm(cv_all_pos, sc),
                "directions": [
                    [round(a, 4), round(b, 4), round(c, 4)]
                    for (a, b, c) in cv_all_dir
                ],
                "amplitudes": [round(a, 4) for a in cv_all_amp],
            },
        },
    }
    if grid_payload:
        scene["fea_grid"] = grid_payload

    if fea_strength_scale == 1.0:
        _scene_cache = scene
    return scene


def invalidate_cache():
    global _scene_cache
    _scene_cache = None
