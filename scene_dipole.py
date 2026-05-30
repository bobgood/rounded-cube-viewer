"""scene_dipole.py — Single metal rod on edge e12 with one sleeve coil (dipole experiment)."""

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
    FEA_GRID_DEBUG_COLOR,
    FEA_SOLVE_ENABLED,
    DIPOLE_EDGE_ID,
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

# Reuse voxel + skeleton helpers from the frame builder.
import fea_model as _fm
from fea_model import (
    _skeleton_dims,
    _cube_corner_positions_mm,
    _cylinder_voxels_x,
    _annulus_cylinder_voxels_x,
    _rotate_z,
    _translate,
    _perp_basis,
)
from scene_render import fea_grid_payload, frame_config_dict, scene_point_mm, to_scene_mm

_scene_cache = None


def _edge_endpoints_mm(vertices, half_h: float, edge_id: str) -> tuple[tuple, tuple]:
    pos = _cube_corner_positions_mm(vertices, half_h)
    key = normalize_edge_key(edge_id)
    for c1 in range(1, 9):
        for c2 in range(1, 9):
            if normalize_edge_key(f"e{c1}{c2}") == key:
                return pos[c1], pos[c2]
            if normalize_edge_key(f"e{c2}{c1}") == key:
                return pos[c2], pos[c1]
    raise ValueError(f"unknown edge {edge_id!r}")


def _voxels_along_edge(p1, p2, length_mm, r_outer_mm, r_inner_mm=None):
    """Solid or annular cylinder along p1→p2."""
    mx = (p1[0] + p2[0]) / 2.0
    my = (p1[1] + p2[1]) / 2.0
    mz = (p1[2] + p2[2]) / 2.0
    angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    if r_inner_mm is None:
        tpl = _cylinder_voxels_x(length_mm, r_outer_mm)
    else:
        tpl = _annulus_cylinder_voxels_x(length_mm, r_outer_mm, r_inner_mm)
    return _translate(_rotate_z(tpl, angle), mx, my, mz)


def _axis_unit(p1, p2, length_mm):
    return (
        (p2[0] - p1[0]) / length_mm,
        (p2[1] - p1[1]) / length_mm,
        (p2[2] - p1[2]) / length_mm,
    )


def _azimuthal_tangent(ux, uy, uz, rx, ry, rz):
    """Circulation tangent = u x r_hat (current winds around the axis)."""
    rl = math.sqrt(rx * rx + ry * ry + rz * rz)
    if rl < 1e-9:
        return None
    rx, ry, rz = rx / rl, ry / rl, rz / rl
    tx = uy * rz - uz * ry
    ty = uz * rx - ux * rz
    tz = ux * ry - uy * rx
    tl = math.sqrt(tx * tx + ty * ty + tz * tz)
    if tl < 1e-9:
        return None
    return tx / tl, ty / tl, tz / tl


def _coil_j_voxels(p1, p2, length_mm, weight: float) -> list:
    """Sleeve voxels with J circulating azimuthally around the rod (solenoid winding)."""
    w = float(weight)
    if abs(w) < 1e-9:
        return []
    r_in = DIPOLE_ROD_RADIUS_MM + DIPOLE_COIL_CLEARANCE_MM
    r_out = r_in + DIPOLE_COIL_THICKNESS_MM
    vox = _voxels_along_edge(p1, p2, length_mm, r_out, r_in)
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


def _arrow_sites(p1, p2, weight: float,
                 axial_steps: int = 10, azim_steps: int = 12) -> tuple[list, list, list]:
    """Circulation arrows around the rod so the coil current direction is visible.

    axial_steps: positions along the rod length.
    azim_steps:  arrows per ring (spaced evenly around the circumference).
    """
    w = float(weight)
    if abs(w) < 1e-9:
        return [], [], []
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
    ux, uy, uz = _axis_unit(p1, p2, length)
    basis = _perp_basis((ux, uy, uz))
    if basis is None:
        return [], [], []
    (vx, vy, vz), (wx, wy, wz) = basis
    r_coil = DIPOLE_ROD_RADIUS_MM + DIPOLE_COIL_CLEARANCE_MM + DIPOLE_COIL_THICKNESS_MM * 0.5
    j_sign = 1.0 if w >= 0 else -1.0
    pos, dirs, amps = [], [], []
    for ai in range(axial_steps):
        t = (ai + 0.5) / axial_steps
        cx = p1[0] + t * (p2[0] - p1[0])
        cy = p1[1] + t * (p2[1] - p1[1])
        cz = p1[2] + t * (p2[2] - p1[2])
        for zi in range(azim_steps):
            ang = 2.0 * math.pi * zi / azim_steps
            ca, sa = math.cos(ang), math.sin(ang)
            rx = ca * vx + sa * wx
            ry = ca * vy + sa * wy
            rz = ca * vz + sa * wz
            tang = _azimuthal_tangent(ux, uy, uz, rx, ry, rz)
            if tang is None:
                continue
            tx, ty, tz = tang
            pos.append((cx + r_coil * rx, cy + r_coil * ry, cz + r_coil * rz))
            dirs.append((j_sign * tx, j_sign * ty, j_sign * tz))
            amps.append(w)
    return pos, dirs, amps


def build_dipole_scene(force: bool = False, fea_strength_scale: float = 1.0):
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

    edge_id = normalize_edge_key(DIPOLE_EDGE_ID)
    p1_full, p2_full = _edge_endpoints_mm(vertices, half_h, edge_id)
    full_length_mm = math.hypot(
        p2_full[0] - p1_full[0],
        p2_full[1] - p1_full[1],
        p2_full[2] - p1_full[2],
    )

    # Trim rod by end-gap from each endpoint.
    if DIPOLE_ROD_END_GAP_MM > 0.0:
        frac = DIPOLE_ROD_END_GAP_MM / full_length_mm
        p1 = tuple(p1_full[i] + frac * (p2_full[i] - p1_full[i]) for i in range(3))
        p2 = tuple(p2_full[i] - frac * (p2_full[i] - p1_full[i]) for i in range(3))
    else:
        p1, p2 = p1_full, p2_full
    length_mm = math.hypot(p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])

    # coil_init weight; fea_strength_scale only when rebuilding via fea_start / Strength slider.
    weight = max(-1.0, min(1.0, float(edge_coil_weight(edge_id)) * float(fea_strength_scale)))

    cyl_raw = _voxels_along_edge(p1, p2, length_mm, DIPOLE_ROD_RADIUS_MM)
    coil_voxels = _coil_j_voxels(p1, p2, length_mm, weight)

    c1 = int(edge_id[1])
    c2 = int(edge_id[2])
    cyl_objects = [{
        "id": "cy0",
        "label": edge_id,
        "edge": edge_id,
        "corners": [c1, c2],
        "ends": [scene_point_mm(*p1, 1.0), scene_point_mm(*p2, 1.0)],
        "start": 0,
        "count": len(cyl_raw),
    }]

    cv_pos, cv_dir, cv_amp = _arrow_sites(p1, p2, weight)
    cv_objects = []
    if cv_pos:
        cv_objects.append({
            "id": "cv0",
            "label": edge_id,
            "edge": edge_id,
            "coil_key": edge_id,
            "corners": [c1, c2],
            "start": 0,
            "count": len(cv_pos),
            "amplitude": round(weight, 4),
        })

    _fm._last_fea_inputs = {
        "cyl_raw": cyl_raw,
        "cap_raw": [],
        "plate_raw": [],
        "hs_raw": [],
        "coil_voxels": coil_voxels,
        "outer_edge_mm": E,
        "outer_height_mm": H,
    }

    fea_grid = build_fea_grid(
        cyl_raw, [], [], [],
        coil_voxels=coil_voxels,
        outer_edge_mm=E,
        outer_height_mm=H,
        voxel_size_mm=VOXEL_SIZE_MM,
        pad_mm=FEA_GRID_PAD_MM,
        steel_material_id=FEA_METAL_MATERIAL_ID,
        steel_mu_r=FEA_METAL_MU_R,
        coil_material_id=FEA_COIL_MATERIAL_ID,
        coil_mu_r=FEA_COIL_MU_R,
    )

    print(
        f"[fea] scene=dipole  edge={edge_id}  length={length_mm:.1f}mm  "
        f"rod_r={DIPOLE_ROD_RADIUS_MM:g}mm  gap={DIPOLE_COIL_CLEARANCE_MM:g}mm  "
        f"coil_t={DIPOLE_COIL_THICKNESS_MM:g}mm  end_gap={DIPOLE_ROD_END_GAP_MM:g}mm  "
        f"I={weight:+.2f}"
    )
    mg = fea_grid["metal"]
    cells = fea_grid["cells"]
    print(
        f"[fea] FEA grid {fea_grid['size'][0]}x{fea_grid['size'][1]}x{fea_grid['size'][2]}  "
        f"steel={cells['steel_count']:,}  coil+J={cells['coil_count']:,}"
    )

    if FEA_SOLVE_ENABLED:
        t0 = time.perf_counter()
        bfield = solve_magnetostatic(fea_grid)
        fea_grid["B_field"] = {
            "max_T": bfield["meta"]["max_B_T"],
            "mean_T": bfield["meta"]["mean_B_T"],
            "solve_meta": bfield["meta"],
        }
        print(f"[fea] B solve {time.perf_counter() - t0:.2f}s")

    sc = MM_TO_SCENE
    grid_payload = fea_grid_payload(fea_grid, sc)

    scene = {
        "type": "voxel_scene",
        "scene_id": "dipole",
        "voxel_size": round(VOXEL_SIZE_MM * sc, 4),
        "frame_config": frame_config_dict(
            edge_mm=E,
            height_mm=H,
            inset_mm=ins,
            corner_pos_mm=corner_pos_mm,
            coil_weights=export_coil_table(),
            sc=sc,
        ),
        "cylinders": {
            "color": list(CYLINDER_COLOR),
            "objects": cyl_objects,
            "positions": to_scene_mm(cyl_raw, sc),
        },
        "caps": {"color": list(CYLINDER_COLOR), "objects": [], "positions": []},
        "coil": {
            "weights": export_coil_table(),
            "color_positive": list(COIL_ARROW_COLOR_POSITIVE),
            "color_negative": list(COIL_ARROW_COLOR_NEGATIVE),
            "groups": {"edge": f"{edge_id} (single sleeve on {edge_id})"},
        },
        "cv": {
            "objects": cv_objects,
            "color_positive": list(COIL_ARROW_COLOR_POSITIVE),
            "color_negative": list(COIL_ARROW_COLOR_NEGATIVE),
            "sites": {
                "positions": to_scene_mm(cv_pos, sc),
                "directions": [[round(a, 4), round(b, 4), round(c, 4)] for (a, b, c) in cv_dir],
                "amplitudes": [round(a, 4) for a in cv_amp],
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
