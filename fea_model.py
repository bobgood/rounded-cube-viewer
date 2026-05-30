"""fea_model.py — Voxel frame geometry for the FEA viewer.

Generates a regular n-gon prism frame:
  - 3n cylinder rods
  - 2n corner caps  — sphere + 3 collar stubs (CAP_LENGTH_MM from centre)
  - 6 plate faces   — 4 spin-wheel quadrant panels per face (n=4 only)
  - 6 Hs assemblies — coaxial hole pipes + back washer per face (n=4 only)
  - 6 Cu FEA fields — fixed pipe volume + per-site current dir/amp (n=4; arrows in JS)
  - 24 Cv edge coils — 2 per Cy edge (n=4; arrows in JS)

FRAME_EDGE_MM  is the outer envelope. Cylinder rods sit on
an inset skeleton (see _skeleton_dims). Caps, plates, and Ou may still use
mixed semantics until aligned.

Scene message format
--------------------
{
  "type": "voxel_scene",
  "voxel_size": <float>,
  "frame_config": { edge_mm, height_mm, ou_rounding_mm, ou_color,
                    hole_diameter_mm, ho_color, mm_to_scene },
  "cylinders": { "color", "objects", "positions" },
  "caps":      { "color", "objects", "positions" },
  "plates":    { "color", "objects", "positions" }   # omitted for n != 4
  "hs":        { "color", "objects", "positions" }   # omitted for n != 4
  "cu":        { "face_amplitudes", "objects",
                  "sites": { "positions", "directions", "amplitudes" },
                  "color_positive", "color_negative" }
  "cv":        { "objects", "sites": { ... }, "color_positive", "color_negative" }
  "fea_grid":  { origin, size, metal (Gm steel debug), cells { steel, copper + J_mm } }
}
Each "objects" list: [{"id":"cy0","label":"e12","start":0,"count":N}, ...]
Cube (n=4): corners C1–C8, edges E12, faces F1234 (clockwise corner ids).
Plate ids use the format  F{face}{quad}  e.g. "F0A", "F3C".
"""

import json
import math
import time

from fea_config import (
    VOXEL_SIZE_MM,
    CYLINDER_LENGTH_MM,
    CYLINDER_SPLIT_GAP_MM,
    CYLINDER_RADIUS_MM,
    CYLINDER_COLOR,
    CAP_DIAMETER_MM,
    CAP_LENGTH_MM,
    CAP_COLOR,
    COLLAR_DIAMETER_MM,
    FRAME_SIDES,
    FRAME_EDGE_MM,
    FRAME_GAP_MM,
    FRAME_INSET_MM,
    PLATE_THICKNESS_MM,
    PLATE_GAP_MM,
    SPIN_WHEEL_OFFSET_MM,
    PLATE_EDGE_INSET_MM,
    PLATE_COLOR,
    FEA_FACE_PLATES_ENABLED,
    OU_COLOR,
    HOLE_DIAMETER_MM,
    HO_COLOR,
    HS_INNER_PIPE_OD_MM,
    HS_OUTER_PIPE_OD_MM,
    HS_WALL_THICKNESS_MM,
    HS_LENGTH_MM,
    HS_WASHER_THICKNESS_MM,
    HS_COLOR,
    CU_CLEARANCE_FROM_HS_INNER_MM,
    CU_CLEARANCE_FROM_HS_OUTER_MM,
    CU_PIPE_WALL_THICKNESS_MM,
    CU_PIPE_EXTENSION_MM,
    CU_SITE_SPACING_MM,
    COIL_ARROW_COLOR_POSITIVE,
    COIL_ARROW_COLOR_NEGATIVE,
    CU_COLOR_POSITIVE,
    CU_COLOR_NEGATIVE,
    CV_GAP_FROM_CORNER_MM,
    CV_EXTEND_MM,
    CV_THICKNESS_MM,
    CV_CLEARANCE_FROM_ROD_MM,
    CV_SITE_SPACING_MM,
    CV_COLOR_POSITIVE,
    CV_COLOR_NEGATIVE,
    CV_DEFAULT_AMPLITUDE,
    MM_TO_SCENE,
    FEA_GRID_PAD_MM,
    FEA_METAL_MATERIAL_ID,
    FEA_METAL_MU_R,
    FEA_COIL_MATERIAL_ID,
    FEA_COIL_MU_R,
    FEA_CURRENT_NOM_A_MM2,
    FEA_GRID_DEBUG_COLOR,
    FEA_SOLVE_ENABLED,
    FEA_BLINE_VOXEL_MM,
    FEA_BLINE_PAD_MM,
    FEA_BLINE_MAX_LINES,
    FEA_BLINE_STEP_MM,
    FEA_BLINE_MAX_STEPS,
    FEA_BLINE_SEED_STRIDE,
    FEA_BLINE_MIN_B_FRAC,
    FEA_BLINE_STOP_FRAC,
    FEA_BLINE_MU_R,
)

from coil_init import cu_coil_weight, cv_coil_key, cv_coil_weight, export_coil_table
from fea_grid import build_fea_grid
from fea_solve import solve_magnetostatic, solve_b_arrays
from fea_blines import trace_field_lines
from geometry_ids import (
    CORNER_BY_K_TOP,
    FACE_CLOCKWISE as _CUBE_FACE_CLOCKWISE,
    corner_id as _cube_corner,
    face_label as _cube_face_label,
    ring_edge_label as _cube_ring_edge_label,
    strut_edge_label as _cube_strut_edge_label,
)
from scene_render import fea_grid_payload, frame_config_dict, scene_point_mm, to_scene_mm


def _scene_point(x_mm: float, y_mm: float, z_mm: float, sc: float) -> list:
    return scene_point_mm(x_mm, y_mm, z_mm, sc)


def _cube_corner_positions_mm(vertices, half_h: float) -> dict:
    pos: dict = {}
    for k in range(4):
        vx, vy = vertices[k]
        c = CORNER_BY_K_TOP[k]
        pos[c] = (vx, vy, half_h)
        pos[c + 4] = (vx, vy, -half_h)
    return pos


def _closest_corner(face_corner_ids, corner_pos_mm, x, y, z) -> int:
    best_c = face_corner_ids[0]
    best_d = float("inf")
    for c in face_corner_ids:
        cx, cy, cz = corner_pos_mm[c]
        d = (x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2
        if d < best_d:
            best_d = d
            best_c = c
    return best_c


# ── Primitive voxel generators ───────────────────────────────────────────────

def _cylinder_voxels_x(length_mm, radius_mm=None, step=VOXEL_SIZE_MM,
                       split_gap_mm=0.0):
    """Solid cylinder along the +X axis, centred at origin.

    split_gap_mm: when > 0, omit voxels with |x| < split_gap_mm/2 (centre air gap).
    """
    if radius_mm is None:
        radius_mm = CYLINDER_RADIUS_MM
    half_l = length_mm / 2.0
    r_sq   = radius_mm ** 2
    n_l    = int(half_l    / step)
    n_r    = int(radius_mm / step)
    half_gap = max(0.0, float(split_gap_mm)) / 2.0
    voxels = []
    for ix in range(-n_l, n_l + 1):
        x = ix * step
        if abs(x) > half_l:
            continue
        if half_gap > 0.0 and abs(x) < half_gap:
            continue
        for iy in range(-n_r, n_r + 1):
            y = iy * step
            for iz in range(-n_r, n_r + 1):
                z = iz * step
                if y * y + z * z <= r_sq:
                    voxels.append((x, y, z))
    return voxels


def _sphere_voxels(radius_mm, step=VOXEL_SIZE_MM):
    """Solid sphere centred at origin."""
    r_sq = radius_mm ** 2
    n    = int(radius_mm / step)
    voxels = []
    for ix in range(-n, n + 1):
        x = ix * step
        for iy in range(-n, n + 1):
            y = iy * step
            for iz in range(-n, n + 1):
                z = iz * step
                if x * x + y * y + z * z <= r_sq:
                    voxels.append((x, y, z))
    return voxels


def _lattice_centers_along_axis(lo: float, hi: float, step: float) -> list[float]:
    """Voxel centres k*step whose cubes intersect [lo, hi] (same lattice as cylinders)."""
    if lo >= hi or step <= 0:
        return []
    k = int(math.ceil((lo - step / 2) / step))
    out: list[float] = []
    while True:
        c = k * step
        if c - step / 2 > hi + 1e-9:
            break
        if c + step / 2 >= lo - 1e-9:
            out.append(c)
        k += 1
    return out


def _lattice_centers_thickness(thickness: float, step: float) -> list[float]:
    """Centres k*step along W from 0 (outer face) inward to thickness."""
    if thickness <= 0 or step <= 0:
        return []
    k = 0
    out: list[float] = []
    while True:
        c = k * step
        if c - step / 2 > thickness + 1e-9:
            break
        if c + step / 2 <= thickness + 1e-9:
            out.append(c)
        k += 1
    return out


def _box_voxels(u_lo, u_hi, v_lo, v_hi, thickness, step=VOXEL_SIZE_MM):
    """Rectangular slab in UV-space; W axis runs from 0 (outer) to thickness (inward)."""
    if u_lo >= u_hi or v_lo >= v_hi or thickness <= 0:
        return []
    us = _lattice_centers_along_axis(u_lo, u_hi, step)
    vs = _lattice_centers_along_axis(v_lo, v_hi, step)
    ws = _lattice_centers_thickness(thickness, step)
    if not us or not vs or not ws:
        return []
    return [(u, v, w) for u in us for v in vs for w in ws]


def _rotate_z(voxels, angle):
    c, s = math.cos(angle), math.sin(angle)
    return [(c * x - s * y, s * x + c * y, z) for (x, y, z) in voxels]


def _translate(voxels, dx, dy, dz):
    return [(x + dx, y + dy, z + dz) for (x, y, z) in voxels]


def _annulus_cylinder_voxels_x(length_mm, r_outer_mm, r_inner_mm, step=VOXEL_SIZE_MM):
    """Hollow cylinder wall along +X (inner radius exclusive, outer inclusive)."""
    if r_inner_mm >= r_outer_mm or length_mm <= 0:
        return []
    r_outer_sq = r_outer_mm ** 2
    r_inner_sq = r_inner_mm ** 2
    half_l = length_mm / 2.0
    n_l = int(half_l / step)
    n_r = int(r_outer_mm / step)
    voxels = []
    for ix in range(-n_l, n_l + 1):
        x = ix * step
        if abs(x) > half_l:
            continue
        for iy in range(-n_r, n_r + 1):
            y = iy * step
            for iz in range(-n_r, n_r + 1):
                z = iz * step
                r2 = y * y + z * z
                if r_inner_sq < r2 <= r_outer_sq:
                    voxels.append((x, y, z))
    return voxels


def _voxels_to_axis(voxels, axis):
    """Map +X-axis template to +X, +Y, or +Z world axis."""
    if axis == "x":
        return voxels
    if axis == "y":
        return [(z, x, y) for (x, y, z) in voxels]
    if axis == "z":
        return [(y, z, x) for (x, y, z) in voxels]
    raise ValueError(f"unknown axis {axis!r}")


def _annulus_disk_voxels(axis, r_outer_mm, r_inner_mm, thickness_mm, step=VOXEL_SIZE_MM):
    """Annular washer disk in the plane perpendicular to axis (centred at origin)."""
    if r_inner_mm >= r_outer_mm or thickness_mm <= 0:
        return []
    r_outer_sq = r_outer_mm ** 2
    r_inner_sq = r_inner_mm ** 2
    half_t = thickness_mm / 2.0
    n_r = int(r_outer_mm / step)
    t_vals = [
        kt * step
        for kt in range(-int(math.ceil(half_t / step)), int(math.ceil(half_t / step)) + 1)
        if abs(kt * step) + step / 2 <= half_t + 1e-9
    ]
    raw = []
    for t in t_vals:
        for iy in range(-n_r, n_r + 1):
            u = iy * step
            for iz in range(-n_r, n_r + 1):
                v = iz * step
                r2 = u * u + v * v
                if r_inner_sq < r2 <= r_outer_sq:
                    raw.append((t, u, v))
    return _voxels_to_axis(raw, axis)


def _normalize3(vx, vy, vz):
    ln = math.sqrt(vx * vx + vy * vy + vz * vz)
    if ln < 1e-9:
        return (0.0, 0.0, 0.0)
    return (vx / ln, vy / ln, vz / ln)


def _hs_pipe_radii_mm():
    """Hs inner/outer pipe radii (mm): inner OD, outer ID, outer OD."""
    wt = HS_WALL_THICKNESS_MM
    r_io = HS_INNER_PIPE_OD_MM / 2.0
    r_oo = HS_OUTER_PIPE_OD_MM / 2.0
    r_oi = r_oo - wt
    return r_io, r_oi, r_oo


def _cu_pipe_radii_mm():
    """Copper shell outside Hs inner OD, capped before Hs outer pipe ID."""
    r_io, r_oi, _r_oo = _hs_pipe_radii_mm()
    gap_in = CU_CLEARANCE_FROM_HS_INNER_MM
    gap_out = CU_CLEARANCE_FROM_HS_OUTER_MM
    r_in = r_io + gap_in
    r_out = min(r_in + CU_PIPE_WALL_THICKNESS_MM, r_oi - gap_out)
    if r_out <= r_in:
        r_out = r_in + max(VOXEL_SIZE_MM, (r_oi - gap_out - r_in) * 0.5)
    return r_in, r_out, r_io, r_oi


def _cu_coil_radius_mm():
    """Midline of copper shell — coil winds just outside inner pipe OD."""
    r_in, r_out, _, _ = _cu_pipe_radii_mm()
    return 0.5 * (r_in + r_out)


def _tangent_around_axis(axis, x, y, z, sign):
    """Unit tangent for circulation around pipe axis (coil current direction)."""
    sg = 1.0 if sign >= 0 else -1.0
    if axis == "z":
        r = math.hypot(x, y)
        if r < 1e-6:
            return (0.0, 0.0, 0.0)
        return (sg * -y / r, sg * x / r, 0.0)
    if axis == "y":
        r = math.hypot(x, z)
        if r < 1e-6:
            return (0.0, 0.0, 0.0)
        return (sg * -z / r, 0.0, sg * x / r)
    r = math.hypot(y, z)
    if r < 1e-6:
        return (0.0, 0.0, 0.0)
    return (0.0, sg * -z / r, sg * y / r)


def _cu_coil_sample_points(axis, face_coord, length_mm, r_coil):
    """Sample points on one coil ring radius (outside Hs inner pipe OD)."""
    inward = -math.copysign(1.0, face_coord)
    face_outer = face_coord
    n_along = max(1, int(length_mm / CU_SITE_SPACING_MM))
    n_around = max(8, int(2.0 * math.pi * r_coil / CU_SITE_SPACING_MM))
    pts = []
    for ia in range(n_along):
        t = (ia + 0.5) / n_along
        axial = face_outer + inward * (length_mm * t)
        for ik in range(n_around):
            theta = 2.0 * math.pi * ik / n_around
            c, s = math.cos(theta), math.sin(theta)
            if axis == "z":
                pts.append((r_coil * c, r_coil * s, axial))
            elif axis == "y":
                pts.append((r_coil * c, axial, r_coil * s))
            else:
                pts.append((axial, r_coil * c, r_coil * s))
    return pts


def _translate_cu_pipe_voxels(axis: str, face_coord: float, length_mm: float, voxels: list) -> list:
    """Place +X annulus template on a cube face (same layout as Hs pipes)."""
    half_l = length_mm / 2.0
    inward = -math.copysign(1.0, face_coord)
    pipe_ctr = face_coord + inward * half_l
    inner_w = _voxels_to_axis(voxels, axis)
    if axis == "x":
        return _translate(inner_w, pipe_ctr, 0.0, 0.0)
    if axis == "y":
        return _translate(inner_w, 0.0, pipe_ctr, 0.0)
    return _translate(inner_w, 0.0, 0.0, pipe_ctr)


def _build_cu_face_voxels(axis, face_coord, coil_weight, hs_length_mm, extension_mm):
    """Copper pipe volume on the FEA lattice with current density J (A/mm²)."""
    if abs(coil_weight) < 1e-9:
        return []
    r_in, r_out, _, _ = _cu_pipe_radii_mm()
    if r_out <= r_in:
        return []

    sign = 1.0 if coil_weight >= 0 else -1.0
    j_scale = abs(float(coil_weight)) * FEA_CURRENT_NOM_A_MM2
    length = hs_length_mm + extension_mm
    pipe = _annulus_cylinder_voxels_x(length, r_out, r_in)
    world = _translate_cu_pipe_voxels(axis, face_coord, length, pipe)

    out = []
    for (x, y, z) in world:
        tx, ty, tz = _tangent_around_axis(axis, x, y, z, sign)
        if tx == ty == tz == 0.0:
            continue
        out.append((
            x, y, z,
            tx * j_scale, ty * j_scale, tz * j_scale,
            float(coil_weight),
        ))
    return out


def _build_cu_face_field(axis, face_coord, coil_weight, hs_length_mm,
                         extension_mm, outer_edge_mm, outer_height_mm, ou_round_mm):
    """FEA sites on coil path; direction fixed CCW, coil_weight is display/FEA scale only."""
    if abs(coil_weight) < 1e-6:
        return []
    r_in, r_out, r_io, r_oi = _cu_pipe_radii_mm()
    r_coil = _cu_coil_radius_mm()
    if r_coil < r_io + 1e-6:
        return []

    length = hs_length_mm + extension_mm
    hx = outer_edge_mm / 2.0
    hy = outer_height_mm / 2.0
    hz = outer_edge_mm / 2.0

    sites = []
    for (x, y, z) in _cu_coil_sample_points(axis, face_coord, length, r_coil):
        if not _inside_rounded_box(x, y, z, hx, hy, hz, ou_round_mm):
            continue
        # Must be outside inner Hs pipe OD and not in outer Hs pipe metal zone
        if axis == "z":
            r = math.hypot(x, y)
        elif axis == "y":
            r = math.hypot(x, z)
        else:
            r = math.hypot(y, z)
        if r < r_io + CU_CLEARANCE_FROM_HS_INNER_MM * 0.5:
            continue
        if r > r_oi - CU_CLEARANCE_FROM_HS_OUTER_MM * 0.5:
            continue
        tx, ty, tz = _tangent_around_axis(axis, x, y, z, 1.0)
        if tx == ty == tz == 0.0:
            continue
        sites.append((x, y, z, tx, ty, tz, float(coil_weight)))
    return sites


def _cv_coil_radius_mm():
    return CYLINDER_RADIUS_MM + CV_CLEARANCE_FROM_ROD_MM + CV_THICKNESS_MM * 0.5


def _edge_axis(p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dz = p2[2] - p1[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-6:
        return None
    return (dx / length, dy / length, dz / length), length


def _perp_basis(u):
    ux, uy, uz = u
    if abs(uz) < 0.9:
        rx, ry, rz = 0.0, 0.0, 1.0
    else:
        rx, ry, rz = 1.0, 0.0, 0.0
    vx = uy * rz - uz * ry
    vy = uz * rx - ux * rz
    vz = ux * ry - uy * rx
    vl = math.sqrt(vx * vx + vy * vy + vz * vz)
    if vl < 1e-9:
        return None
    vx, vy, vz = vx / vl, vy / vl, vz / vl
    wx = uy * vz - uz * vy
    wy = uz * vx - ux * vz
    wz = ux * vy - uy * vx
    wl = math.sqrt(wx * wx + wy * wy + wz * wz)
    if wl < 1e-9:
        return None
    return (vx, vy, vz), (wx / wl, wy / wl, wz / wl)


def _cv_tangent_ccw(u, px, py, pz, ax, ay, az, view_from_c1):
    """CCW around +u when viewed from corner c1; flip for coil at c2 end."""
    ux, uy, uz = u
    rx, ry, rz = px - ax, py - ay, pz - az
    dot = rx * ux + ry * uy + rz * uz
    rx -= dot * ux
    ry -= dot * uy
    rz -= dot * uz
    rl = math.sqrt(rx * rx + ry * ry + rz * rz)
    if rl < 1e-9:
        return (0.0, 0.0, 0.0)
    tx = uy * rz - uz * ry
    ty = uz * rx - ux * rz
    tz = ux * ry - uy * rx
    tl = math.sqrt(tx * tx + ty * ty + tz * tz)
    if tl < 1e-9:
        return (0.0, 0.0, 0.0)
    sgn = 1.0 if view_from_c1 else -1.0
    return (sgn * tx / tl, sgn * ty / tl, sgn * tz / tl)


def _sample_cv_coil_end(anchor, u, s_lo, s_hi, r_coil, amplitude, view_from_c1,
                        site_spacing=None):
    """Samples on one coil sleeve at an edge end (anchor = corner end)."""
    if abs(amplitude) < 1e-6:
        return []
    step = CV_SITE_SPACING_MM if site_spacing is None else site_spacing
    basis = _perp_basis(u)
    if basis is None:
        return []
    v, w = basis
    ux, uy, uz = u
    n_along = max(1, int((s_hi - s_lo) / step))
    n_around = max(8, int(2.0 * math.pi * r_coil / step))
    sign = 1.0 if view_from_c1 else -1.0
    sites = []
    for ia in range(n_along):
        s = s_lo + (ia + 0.5) / n_along * (s_hi - s_lo)
        ax = anchor[0] + sign * ux * s
        ay = anchor[1] + sign * uy * s
        az = anchor[2] + sign * uz * s
        for ik in range(n_around):
            th = 2.0 * math.pi * ik / n_around
            c, sn = math.cos(th), math.sin(th)
            px = ax + r_coil * (c * v[0] + sn * w[0])
            py = ay + r_coil * (c * v[1] + sn * w[1])
            pz = az + r_coil * (c * v[2] + sn * w[2])
            tx, ty, tz = _cv_tangent_ccw(u, px, py, pz, ax, ay, az, view_from_c1)
            if tx == ty == tz == 0.0:
                continue
            sites.append((px, py, pz, tx, ty, tz, float(amplitude)))
    return sites


def _iter_cube_edges(vertices, half_h):
    """Yield (c1, c2, p1_mm, p2_mm) for 12 cube skeleton edges."""
    for k in range(4):
        vx0, vy0 = vertices[k]
        vx1, vy1 = vertices[(k + 1) % 4]
        for z_sign in (+1, -1):
            cz = z_sign * half_h
            yield (
                _cube_corner(k, z_sign),
                _cube_corner((k + 1) % 4, z_sign),
                (vx0, vy0, cz),
                (vx1, vy1, cz),
            )
    for k in range(4):
        vx, vy = vertices[k]
        yield (
            _cube_corner(k, +1),
            _cube_corner(k, -1),
            (vx, vy, half_h),
            (vx, vy, -half_h),
        )


def _build_cv_edge_coils(vertices, half_h, weight_scale: float = 1.0):
    """24 coils: at each edge end, E{c1}{c2} near c1 and E{c2}{c1} near c2."""
    gap = CV_GAP_FROM_CORNER_MM
    ext = CV_EXTEND_MM

    def _display(w: float) -> float:
        return max(-1.0, min(1.0, float(w) * float(weight_scale)))

    pos_all: list = []
    dir_all: list = []
    amp_all: list = []
    objects: list = []
    coil_idx = 0

    for c1, c2, p1, p2 in _iter_cube_edges(vertices, half_h):
        axis = _edge_axis(p1, p2)
        if axis is None:
            continue
        u, length = axis
        if length < 2.0 * gap + ext + 0.5:
            continue

        ends = (
            (p1, True,  c1, c2, f"e{c1}{c2}"),
            (p2, False, c2, c1, f"e{c2}{c1}"),
        )
        for anchor, from_c1, near_c, far_c, label in ends:
            weight = _display(cv_coil_weight(near_c, label))
            if abs(weight) < 1e-6:
                continue
            coil_key = cv_coil_key(near_c, label)
            start = len(pos_all)
            chunk = _sample_cv_coil_end(
                anchor, u, gap, gap + ext, _cv_coil_radius_mm(),
                weight, from_c1,
            )
            for (x, y, z, tx, ty, tz, a) in chunk:
                pos_all.append((x, y, z))
                dir_all.append((tx, ty, tz))
                amp_all.append(a)
            count = len(pos_all) - start
            if count > 0:
                objects.append({
                    "id": f"cv{coil_idx}",
                    "label": label,
                    "edge": label,
                    "corners": [near_c, far_c],
                    "end_corner": near_c,
                    "coil_key": coil_key,
                    "coil_weight": round(weight, 4),
                    "start": start,
                    "count": count,
                    "amplitude": round(weight, 4),
                })
                coil_idx += 1

    return pos_all, dir_all, amp_all, objects


def _build_cv_coil_voxels(anchor, u, s_lo, s_hi, coil_weight, view_from_c1):
    """Cv sleeve volume on the FEA lattice (filled band, not a single sample ring)."""
    w = float(coil_weight)
    if abs(w) < 1e-9:
        return []
    step = VOXEL_SIZE_MM
    basis = _perp_basis(u)
    if basis is None:
        return []
    v, wv = basis
    ux, uy, uz = u
    sign_edge = 1.0 if view_from_c1 else -1.0
    j_scale = abs(w) * FEA_CURRENT_NOM_A_MM2
    j_sign = 1.0 if w >= 0 else -1.0
    r_in = CYLINDER_RADIUS_MM + CV_CLEARANCE_FROM_ROD_MM
    r_out = r_in + CV_THICKNESS_MM
    r_in_sq = r_in * r_in
    r_out_sq = r_out * r_out
    n_r = int(r_out / step) + 1

    out = []
    for s_mm in _lattice_centers_along_axis(s_lo, s_hi, step):
        ax = anchor[0] + sign_edge * ux * s_mm
        ay = anchor[1] + sign_edge * uy * s_mm
        az = anchor[2] + sign_edge * uz * s_mm
        for iy in range(-n_r, n_r + 1):
            oy = iy * step
            for iz in range(-n_r, n_r + 1):
                oz = iz * step
                r2 = oy * oy + oz * oz
                if r2 <= r_in_sq or r2 > r_out_sq:
                    continue
                px = ax + oy * v[0] + oz * wv[0]
                py = ay + oy * v[1] + oz * wv[1]
                pz = az + oy * v[2] + oz * wv[2]
                tx, ty, tz = _cv_tangent_ccw(u, px, py, pz, ax, ay, az, view_from_c1)
                tl = math.sqrt(tx * tx + ty * ty + tz * tz)
                if tl < 1e-9:
                    continue
                s = j_sign * j_scale / tl
                out.append((px, py, pz, tx * s, ty * s, tz * s, w))
    return out


def _build_cv_edge_coil_voxels(vertices, half_h, weight_scale: float = 1.0) -> list:
    """All Cv edge coils as (x, y, z, jx, jy, jz, coil_weight) for the FEA grid."""
    gap = CV_GAP_FROM_CORNER_MM
    ext = CV_EXTEND_MM
    out: list = []

    def _display(w: float) -> float:
        return max(-1.0, min(1.0, float(w) * float(weight_scale)))

    for c1, c2, p1, p2 in _iter_cube_edges(vertices, half_h):
        axis = _edge_axis(p1, p2)
        if axis is None:
            continue
        u, length = axis
        if length < 2.0 * gap + ext + 0.5:
            continue
        ends = (
            (p1, True,  c1, c2, f"e{c1}{c2}"),
            (p2, False, c2, c1, f"e{c2}{c1}"),
        )
        for anchor, from_c1, near_c, far_c, label in ends:
            weight = _display(cv_coil_weight(near_c, label))
            if abs(weight) < 1e-6:
                continue
            out.extend(_build_cv_coil_voxels(
                anchor, u, gap, gap + ext, weight, from_c1,
            ))
    return out


def _build_hs_face_voxels(axis, face_coord, length_mm, r_inner_od, r_outer_od,
                          wall_mm, washer_t_mm):
    """Coaxial pipes + back washer on one face (no Ou/Ho subtraction — plates only)."""
    r_io = r_inner_od / 2.0
    r_ii = r_io - wall_mm
    r_oo = r_outer_od / 2.0
    r_oi = r_oo - wall_mm          # outer pipe wall (not flush to inner OD)
    if r_ii <= 0 or r_oi <= r_io or r_oi >= r_oo:
        return []

    inner_pipe = _annulus_cylinder_voxels_x(length_mm, r_io, r_ii)
    outer_pipe = _annulus_cylinder_voxels_x(length_mm, r_oo, r_oi)
    # Washer in plane ⊥ axis at back; spans inner bore to outer pipe OD.
    washer_w = _annulus_disk_voxels(axis, r_oo, r_ii, washer_t_mm)

    inner_w = _voxels_to_axis(inner_pipe, axis)
    outer_w = _voxels_to_axis(outer_pipe, axis)

    half_l = length_mm / 2.0
    half_wt = washer_t_mm / 2.0
    inward = -math.copysign(1.0, face_coord)   # toward cube centre from outer face
    pipe_ctr = face_coord + inward * half_l
    washer_ctr = face_coord + inward * (length_mm + half_wt)
    out = []
    if axis == "x":
        for part in (inner_w, outer_w):
            out.extend(_translate(part, pipe_ctr, 0.0, 0.0))
        out.extend(_translate(washer_w, washer_ctr, 0.0, 0.0))
    elif axis == "y":
        for part in (inner_w, outer_w):
            out.extend(_translate(part, 0.0, pipe_ctr, 0.0))
        out.extend(_translate(washer_w, 0.0, washer_ctr, 0.0))
    else:  # z
        for part in (inner_w, outer_w):
            out.extend(_translate(part, 0.0, 0.0, pipe_ctr))
        out.extend(_translate(washer_w, 0.0, 0.0, washer_ctr))

    return out


def _inside_rounded_box(x, y, z, hx, hy, hz, r):
    """Axis-aligned rounded box centred at origin (matches Ou RoundedBoxGeometry)."""
    if r <= 0:
        return abs(x) <= hx and abs(y) <= hy and abs(z) <= hz
    ax = abs(x) - (hx - r)
    ay = abs(y) - (hy - r)
    az = abs(z) - (hz - r)
    if ax <= 0 and ay <= 0 and az <= 0:
        return True
    ax = max(ax, 0.0)
    ay = max(ay, 0.0)
    az = max(az, 0.0)
    return ax * ax + ay * ay + az * az <= r * r


def _inside_ho_union(x, y, z, ho_r, half_x, half_y, half_z):
    """True if inside any of the three orthogonal Ho subtraction cylinders."""
    r2 = ho_r * ho_r
    if y * y + z * z <= r2 and abs(x) <= half_x:
        return True
    if x * x + z * z <= r2 and abs(y) <= half_y:
        return True
    if x * x + y * y <= r2 and abs(z) <= half_z:
        return True
    return False


def _keep_plate_voxel(x, y, z, outer_edge_mm, outer_height_mm, ou_round_mm, hole_diameter_mm):
    """Plates only: inside Ou envelope and outside Ho holes."""
    hx = outer_edge_mm / 2.0
    hy = outer_height_mm / 2.0
    hz = outer_edge_mm / 2.0
    ho_r = hole_diameter_mm / 2.0
    if not _inside_rounded_box(x, y, z, hx, hy, hz, ou_round_mm):
        return False
    return not _inside_ho_union(x, y, z, ho_r, hx, hy, hz)


# ── Skeleton vs outer envelope ─────────────────────────────────────────────────

def _skeleton_dims(outer_edge_mm, outer_height_mm, inset_mm, sides, gap_mm):
    """Derive n-gon skeleton layout for cylinder rods from outer envelope + inset.

    outer_* : face-to-face outer box (mm).
    inset_mm : per-face inset toward centre; skeleton polygon edge = outer_edge - 2*inset.
    Returns vertices, half_height, ring_len, vert_len, gap_ring, gap_strut.
    """
    n = sides
    skel_e = outer_edge_mm - 2.0 * inset_mm
    skel_h = outer_height_mm - 2.0 * inset_mm
    half_h = skel_h / 2.0

    r = skel_e / (2.0 * math.sin(math.pi / n))
    ao = math.pi / n
    vertices = [
        (r * math.cos(2 * math.pi * k / n + ao),
         r * math.sin(2 * math.pi * k / n + ao))
        for k in range(n)
    ]

    ring_len = max(VOXEL_SIZE_MM, min(CYLINDER_LENGTH_MM, skel_e - 2 * gap_mm))
    vert_len = max(VOXEL_SIZE_MM, min(CYLINDER_LENGTH_MM, skel_h - 2 * gap_mm))
    gap_ring = (skel_e - ring_len) / 2.0
    gap_strut = (skel_h - vert_len) / 2.0

    return {
        "vertices": vertices,
        "half_h": half_h,
        "ring_len": ring_len,
        "vert_len": vert_len,
        "gap_ring": gap_ring,
        "gap_strut": gap_strut,
        "skel_e": skel_e,
        "skel_h": skel_h,
    }


# ── Scene builder ─────────────────────────────────────────────────────────────

_scene_cache = None
_last_fea_inputs = None


def invalidate_cache():
    global _scene_cache
    _scene_cache = None
    try:
        from scene_dipole import invalidate_cache as _inv_dip
        _inv_dip()
    except ImportError:
        pass


def build_bfield_lines(
    fea_strength_scale: float = 1.0,
    voxel_mm: float = FEA_BLINE_VOXEL_MM,
    pad_mm: float = FEA_BLINE_PAD_MM,
    mu_r: float = FEA_BLINE_MU_R,
):
    """Solve B on a coarse, air-padded grid and trace field-line polylines.

    Returns a dict ready to ship to the viewer:
      { "type": "bfield_lines", "lines": [[[x,y,z],...], ...] (scene units),
        "meta": {...} }
    Coordinates are in Three.js scene units (mm * MM_TO_SCENE), matching the
    rest of the voxel scene. Call build_voxel_scene(force=True, fea_strength_scale)
    first so _last_fea_inputs holds the scaled coil currents.
    """
    if _last_fea_inputs is None:
        build_voxel_scene(force=True, fea_strength_scale=fea_strength_scale)
    src = _last_fea_inputs
    if src is None:
        return {"type": "bfield_lines", "lines": [], "meta": {"error": "no FEA inputs"}}

    # Centre the B-line domain on the coil centroid so padding is equal on all sides.
    # For a symmetric frame the centroid ≈ origin; for an off-centre dipole this prevents
    # unequal Neumann image distances that squash one lobe of the dipole field.
    coil_voxels = src["coil_voxels"]
    if coil_voxels:
        n_cv = len(coil_voxels)
        cx = sum(v[0] for v in coil_voxels) / n_cv
        cy = sum(v[1] for v in coil_voxels) / n_cv
        cz = sum(v[2] for v in coil_voxels) / n_cv
        coil_center: tuple[float, float, float] = (cx, 0.0, cz)  # keep y=0 (full axial extent)
    else:
        coil_center = (0.0, 0.0, 0.0)

    field_grid = build_fea_grid(
        src["cyl_raw"], src["cap_raw"], src["plate_raw"], src["hs_raw"],
        coil_voxels=coil_voxels,
        outer_edge_mm=src["outer_edge_mm"],
        outer_height_mm=src["outer_height_mm"],
        voxel_size_mm=voxel_mm,
        pad_mm=pad_mm,
        steel_material_id=FEA_METAL_MATERIAL_ID,
        steel_mu_r=float(mu_r),
        coil_material_id=FEA_COIL_MATERIAL_ID,
        coil_mu_r=FEA_COIL_MU_R,
        center_mm=coil_center,
    )
    nx, ny, nz = field_grid["size"]
    print(
        f"[fea] B-line field grid {nx}x{ny}x{nz} "
        f"(voxel={voxel_mm}mm pad={pad_mm}mm steel_mu_r={mu_r:g} "
        f"center=({coil_center[0]:.1f},{coil_center[1]:.1f},{coil_center[2]:.1f})) solving..."
    )
    sol = solve_b_arrays(field_grid)
    traced = trace_field_lines(
        sol,
        max_lines=FEA_BLINE_MAX_LINES,
        step_mm=FEA_BLINE_STEP_MM,
        max_steps=FEA_BLINE_MAX_STEPS,
        seed_stride=FEA_BLINE_SEED_STRIDE,
        min_B_frac=FEA_BLINE_MIN_B_FRAC,
        stop_frac=FEA_BLINE_STOP_FRAC,
    )

    sc = MM_TO_SCENE
    # Each point: [x, y, z, b_norm]; b_norm in [0,1] for strength colouring.
    lines_scene = [
        [[round(x * sc, 3), round(y * sc, 3), round(z * sc, 3), round(b, 3)]
         for (x, y, z, b) in poly]
        for poly in traced["lines"]
    ]
    meta = dict(traced["meta"])
    meta["size"] = [nx, ny, nz]
    meta["voxel_mm"] = voxel_mm
    meta["pad_mm"] = pad_mm
    meta["mu_r"] = float(mu_r)
    print(
        f"[fea] B lines: {meta['n_lines']} traced from {meta['n_seeds']} seeds  "
        f"max|B|={meta.get('max_B_T', 0.0):.3e} T"
    )
    return {"type": "bfield_lines", "lines": lines_scene, "meta": meta}


def build_frame_scene(force=False, fea_strength_scale=1.0):
    """Build (or return cached) the full frame voxel scene dict.

    Coil colors/intensities come from coil_init.SCENE_COILS (not fea_config).
    fea_strength_scale multiplies every coil_init weight before J is filled on the
    grid (fea_start / Strength slider → server rebuilds scene with scaled weights).
    """
    global _scene_cache
    if _scene_cache is not None and not force and fea_strength_scale == 1.0:
        return _scene_cache

    n   = FRAME_SIDES
    E   = FRAME_EDGE_MM       # outer envelope (plates / Ou / frame_config)
    H   = FRAME_EDGE_MM
    gap = FRAME_GAP_MM
    ins = FRAME_INSET_MM

    sk = _skeleton_dims(E, H, ins, n, gap)
    vertices   = sk["vertices"]
    half_h     = sk["half_h"]
    ring_len   = sk["ring_len"]
    vert_len   = sk["vert_len"]
    gap_ring   = sk["gap_ring"]
    gap_strut  = sk["gap_strut"]

    cyl_split = max(0.0, float(CYLINDER_SPLIT_GAP_MM))
    if cyl_split > 0.0:
        if cyl_split >= ring_len or cyl_split >= vert_len:
            print(
                f"[fea] warning: CYLINDER_SPLIT_GAP_MM={cyl_split} "
                f">= rod length (ring={ring_len}, strut={vert_len}); clamping"
            )
        cyl_split = min(cyl_split, ring_len * 0.99, vert_len * 0.99)

    # Templates (along X axis; strut is re-mapped to Z axis below)
    ring_tpl       = _cylinder_voxels_x(ring_len, split_gap_mm=cyl_split)
    vert_tpl       = _cylinder_voxels_x(vert_len, split_gap_mm=cyl_split)
    cap_r          = CAP_DIAMETER_MM / 2.0
    cap_sphere_tpl = _sphere_voxels(cap_r)
    collar_r       = COLLAR_DIAMETER_MM / 2.0
    collar_len     = CAP_LENGTH_MM
    collar_off     = collar_len / 2.0   # stub centred on sphere: inner end at corner
    collar_ring_tpl  = (
        _cylinder_voxels_x(collar_len, collar_r) if collar_len > 0 else []
    )
    collar_strut_tpl = (
        _cylinder_voxels_x(collar_len, collar_r) if collar_len > 0 else []
    )

    # Map strut templates from X-axis to Z-axis: (x,y,z) -> (y,z,x)
    vert_z          = [(y, z, x) for (x, y, z) in vert_tpl]
    collar_strut_z  = [(y, z, x) for (x, y, z) in collar_strut_tpl]

    print(
        f"[fea] {n}-gon: {n*3} cyl + {n*2} caps  |  "
        f"outer={E:.1f}mm  skeleton_edge={sk['skel_e']:.1f}mm  "
        f"ring={ring_len:.1f}mm  strut={vert_len:.1f}mm  "
        f"cap_d={CAP_DIAMETER_MM:.1f}mm  cap_len={collar_len:.1f}mm  "
        f"collar_r={collar_r:.2f}mm"
        + (f"  cyl_split={cyl_split:.1f}mm" if cyl_split > 0 else "")
    )

    sc = MM_TO_SCENE

    cyl_raw:    list = []
    cap_raw:    list = []
    cyl_objects: list = []
    cap_objects:  list = []
    cyl_idx = 0

    # ── Cylinders (skeleton placement from outer E/H + FRAME_INSET_MM) ───────
    # ── Ring cylinders: 2 per edge (top + bottom), n edges ───────────────────
    for k in range(n):
        vx0, vy0 = vertices[k]
        vx1, vy1 = vertices[(k + 1) % n]
        mx     = (vx0 + vx1) / 2.0
        my     = (vy0 + vy1) / 2.0
        angle  = math.atan2(vy1 - vy0, vx1 - vx0)
        rotated = _rotate_z(ring_tpl, angle)
        for z_sign in (+1, -1):
            start = len(cyl_raw)
            cyl_raw.extend(_translate(rotated, mx, my, z_sign * half_h))
            cz = z_sign * half_h
            entry = {"id": f"cy{cyl_idx}", "label": f"Cy {cyl_idx}",
                     "start": start, "count": len(cyl_raw) - start}
            if n == 4:
                c1 = _cube_corner(k, z_sign)
                c2 = _cube_corner((k + 1) % 4, z_sign)
                entry["corners"] = [c1, c2]
                entry["ends"] = [
                    _scene_point(vx0, vy0, cz, sc),
                    _scene_point(vx1, vy1, cz, sc),
                ]
                entry["label"] = _cube_ring_edge_label(k, z_sign)
            cyl_objects.append(entry)
            cyl_idx += 1

    # ── Strut cylinders: 1 per vertex ─────────────────────────────────────────
    for k in range(n):
        vx, vy = vertices[k]
        start = len(cyl_raw)
        cyl_raw.extend(_translate(vert_z, vx, vy, 0.0))
        entry = {"id": f"cy{cyl_idx}", "label": f"Cy {cyl_idx}",
                 "start": start, "count": len(cyl_raw) - start}
        if n == 4:
            c1 = _cube_corner(k, +1)
            c2 = _cube_corner(k, -1)
            entry["corners"] = [c1, c2]
            entry["ends"] = [
                _scene_point(vx, vy, half_h, sc),
                _scene_point(vx, vy, -half_h, sc),
            ]
            entry["label"] = _cube_strut_edge_label(k)
        cyl_objects.append(entry)
        cyl_idx += 1

    # ── Caps + collars ─────────────────────────────────────────────────────────
    cap_idx = 0
    for k in range(n):
        vx, vy = vertices[k]
        vx_prev, vy_prev = vertices[(k - 1) % n]
        vx_next, vy_next = vertices[(k + 1) % n]
        for z_sign in (+1, -1):
            cz    = z_sign * half_h
            start = len(cap_raw)

            # Full sphere (unclipped) centred at the corner
            cap_raw.extend(_translate(cap_sphere_tpl, vx, vy, cz))

            # Ring collar toward previous vertex (from sphere centre)
            if collar_ring_tpl:
                a = math.atan2(vy_prev - vy, vx_prev - vx)
                cap_raw.extend(
                    _translate(_rotate_z(collar_ring_tpl, a),
                                vx + math.cos(a) * collar_off,
                                vy + math.sin(a) * collar_off,
                                cz))

            # Ring collar toward next vertex
            if collar_ring_tpl:
                a = math.atan2(vy_next - vy, vx_next - vx)
                cap_raw.extend(
                    _translate(_rotate_z(collar_ring_tpl, a),
                                vx + math.cos(a) * collar_off,
                                vy + math.sin(a) * collar_off,
                                cz))

            # Strut collar toward vertical rod (from sphere centre)
            if collar_strut_z:
                ccz = cz - z_sign * collar_off
                cap_raw.extend(_translate(collar_strut_z, vx, vy, ccz))

            cnum = _cube_corner(k, z_sign) if n == 4 else cap_idx
            cap_objects.append({
                "id": f"ca{cap_idx}",
                "label": f"c{cnum}" if n == 4 else f"ca{cap_idx}",
                "corner": cnum if n == 4 else None,
                "start": start,
                "count": len(cap_raw) - start,
            })
            cap_idx += 1

    # ── Plates (n=4 / cube only) ───────────────────────────────────────────────
    plate_raw:     list = []
    plate_objects: list = []

    corner_pos_mm: dict = {}
    fea_scale = float(fea_strength_scale)

    if n == 4:
        corner_pos_mm = _cube_corner_positions_mm(vertices, half_h)

    if n == 4:
        pe = PLATE_EDGE_INSET_MM
        h  = E / 2.0 - pe
        hz = H / 2.0 - pe
        ou_r = ins
        ho_d = HOLE_DIAMETER_MM

        if FEA_FACE_PLATES_ENABLED:
            t  = PLATE_THICKNESS_MM
            g  = PLATE_GAP_MM / 2.0
            d  = SPIN_WHEEL_OFFSET_MM
            # Plates on outer faces; Ou/Ho clip here only (Cy/Ca/Hs unclipped).

            def xfm0(u, v, w): return (u,     v,      hz - w)   # +Z top
            def xfm1(u, v, w): return (u,     v,     -hz + w)   # -Z bottom
            def xfm2(u, v, w): return (h - w, u,      v     )   # +X right
            def xfm3(u, v, w): return (-h+ w, u,      v     )   # -X left
            def xfm4(u, v, w): return (u,     h - w,  v     )   # +Y front
            def xfm5(u, v, w): return (u,    -h + w,  v     )   # -Y back

            face_defs = [
                (0, h,  h,  xfm0),
                (1, h,  h,  xfm1),
                (2, hz, h,  xfm2),
                (3, hz, h,  xfm3),
                (4, h,  hz, xfm4),
                (5, h,  hz, xfm5),
            ]

            quads = {
                'A': lambda hu, hv: (-hu,   d-g,   d+g,  hv),
                'B': lambda hu, hv: ( d+g,  hu,   -d+g,  hv),
                'C': lambda hu, hv: (-d+g,  hu,   -hv,  -d-g),
                'D': lambda hu, hv: (-hu,  -d-g,  -hv,   d-g),
            }

            for (fi, hu, hv, xfm) in face_defs:
                for qname, qbox_fn in quads.items():
                    u_lo, u_hi, v_lo, v_hi = qbox_fn(hu, hv)
                    if u_lo >= u_hi or v_lo >= v_hi:
                        continue
                    start = len(plate_raw)
                    for (u, v, w) in _box_voxels(u_lo, u_hi, v_lo, v_hi, t):
                        x, y, z = xfm(u, v, w)
                        if _keep_plate_voxel(x, y, z, E, H, ou_r, ho_d):
                            plate_raw.append((x, y, z))
                    count = len(plate_raw) - start
                    if count > 0:
                        face_str = _CUBE_FACE_CLOCKWISE[fi]
                        face_ids = [int(c) for c in face_str]
                        uc = (u_lo + u_hi) / 2.0
                        vc = (v_lo + v_hi) / 2.0
                        wc = t / 2.0
                        xc, yc, zc = xfm(uc, vc, wc)
                        anchor = _closest_corner(face_ids, corner_pos_mm, xc, yc, zc)
                        plate_objects.append({
                            "id": f"pl{fi}{qname}",
                            "label": f"f{face_str}",
                            "face": face_str,
                            "anchor_corner": anchor,
                            "start": start,
                            "count": count,
                        })

        # Hs: coaxial pipes + back washer at each face hole (axis ⊥ face)
        hs_raw:     list = []
        hs_objects: list = []
        wt = HS_WALL_THICKNESS_MM
        hs_faces = [
            ("z",  hz),
            ("z", -hz),
            ("x",  h),
            ("x", -h),
            ("y",  h),
            ("y", -h),
        ]
        for fi, (axis, face_c) in enumerate(hs_faces):
            face_key = _cube_face_label(fi)
            start = len(hs_raw)
            hs_raw.extend(_build_hs_face_voxels(
                axis, face_c,
                HS_LENGTH_MM,
                HS_INNER_PIPE_OD_MM, HS_OUTER_PIPE_OD_MM,
                wt, HS_WASHER_THICKNESS_MM,
            ))
            count = len(hs_raw) - start
            if count > 0:
                hs_objects.append({
                    "id": f"hs{fi}",
                    "label": face_key,
                    "face": _CUBE_FACE_CLOCKWISE[fi],
                    "start": start,
                    "count": count,
                })

        # Cu + Cv: coil voxels + J on FEA grid; arrow sites unchanged for display
        coil_grid_voxels: list = []
        cu_pos:     list = []
        cu_dir:     list = []
        cu_amp:     list = []
        cu_objects: list = []
        cu_faces = [
            ("z",  hz),
            ("z", -hz),
            ("x",  h),
            ("x", -h),
            ("y",  h),
            ("y", -h),
        ]
        for fi, (axis, face_c) in enumerate(cu_faces):
            face_str = _CUBE_FACE_CLOCKWISE[fi]
            weight = max(-1.0, min(1.0, float(cu_coil_weight(face_str)) * fea_scale))
            if abs(weight) < 1e-6:
                continue
            coil_grid_voxels.extend(_build_cu_face_voxels(
                axis, face_c, weight, HS_LENGTH_MM, CU_PIPE_EXTENSION_MM,
            ))
            face_key = _cube_face_label(fi)
            start = len(cu_pos)
            for (x, y, z, tx, ty, tz, a) in _build_cu_face_field(
                axis, face_c, weight,
                HS_LENGTH_MM, CU_PIPE_EXTENSION_MM,
                E, H, ou_r,
            ):
                cu_pos.append((x, y, z))
                cu_dir.append((tx, ty, tz))
                cu_amp.append(a)
            count = len(cu_pos) - start
            if count > 0:
                cu_objects.append({
                    "id": f"cu{fi}",
                    "label": face_key,
                    "face": face_str,
                    "coil_key": face_key,
                    "coil_weight": round(weight, 4),
                    "start": start,
                    "count": count,
                    "amplitude": round(weight, 4),
                })

        coil_grid_voxels.extend(_build_cv_edge_coil_voxels(
            vertices, half_h, weight_scale=fea_scale,
        ))

        # Cv: edge coils (2 per Cy edge; arrows in JS)
        cv_pos, cv_dir, cv_amp, cv_objects = _build_cv_edge_coils(
            vertices, half_h, weight_scale=fea_scale,
        )

    else:
        coil_grid_voxels = []
        hs_raw = []
        hs_objects = []
        cu_pos = []
        cu_dir = []
        cu_amp = []
        cu_objects = []
        cv_pos = []
        cv_dir = []
        cv_amp = []
        cv_objects = []

    fea_grid = None
    if n == 4:
        global _last_fea_inputs
        _last_fea_inputs = {
            "cyl_raw": cyl_raw,
            "cap_raw": cap_raw,
            "plate_raw": plate_raw,
            "hs_raw": hs_raw,
            "coil_voxels": coil_grid_voxels,
            "outer_edge_mm": E,
            "outer_height_mm": H,
        }
        fea_grid = build_fea_grid(
            cyl_raw, cap_raw, plate_raw, hs_raw,
            coil_voxels=coil_grid_voxels,
            outer_edge_mm=E,
            outer_height_mm=H,
            voxel_size_mm=VOXEL_SIZE_MM,
            pad_mm=FEA_GRID_PAD_MM,
            steel_material_id=FEA_METAL_MATERIAL_ID,
            steel_mu_r=FEA_METAL_MU_R,
            coil_material_id=FEA_COIL_MATERIAL_ID,
            coil_mu_r=FEA_COIL_MU_R,
        )
        mg = fea_grid["metal"]
        cells = fea_grid["cells"]
        print(
            f"[fea] FEA grid {fea_grid['size'][0]}×{fea_grid['size'][1]}×{fea_grid['size'][2]}  "
            f"steel={cells['steel_count']:,}  coil+J={cells['coil_count']:,}  "
            f"(grid samples {len(coil_grid_voxels):,})  "
            f"raw_struct={mg['sources']['raw_total']:,}  skipped_oob={cells['skipped_oob']:,}"
        )
        if FEA_SOLVE_ENABLED:
            t0 = time.perf_counter()
            bfield = solve_magnetostatic(fea_grid)
            fea_grid["B_field"] = {
                "max_T": bfield["meta"]["max_B_T"],
                "mean_T": bfield["meta"]["mean_B_T"],
                "solve_meta": bfield["meta"],
            }
            print(
                f"[fea] B solve {time.perf_counter() - t0:.2f}s  "
                f"max|B|={bfield['meta']['max_B_T']:.6e} T"
            )

    total = len(cyl_raw) + len(cap_raw) + len(plate_raw) + len(hs_raw)
    print(
        f"[fea] total voxels: {total:,}  "
        f"({len(cyl_raw):,} cyl + {len(cap_raw):,} cap + {len(plate_raw):,} pl "
        f"+ {len(hs_raw):,} hs)  |  Cu sites: {len(cu_pos):,}  "
        f"Cv sites: {len(cv_pos):,}"
    )

    sc = MM_TO_SCENE

    scene = {
        "type":       "voxel_scene",
        "scene_id":   "frame",
        "voxel_size": round(VOXEL_SIZE_MM * sc, 4),
        "frame_config": frame_config_dict(
            edge_mm=E,
            height_mm=H,
            inset_mm=ins,
            corner_pos_mm=corner_pos_mm,
            coil_weights=export_coil_table(),
            sc=sc,
            hole_diameter_mm=HOLE_DIAMETER_MM,
            ho_color=HO_COLOR,
        ),
        "cylinders": {
            "color":     list(CYLINDER_COLOR),
            "objects":   cyl_objects,
            "positions": to_scene_mm(cyl_raw, sc),
        },
        "caps": {
            "color":     list(CAP_COLOR),
            "objects":   cap_objects,
            "positions": to_scene_mm(cap_raw, sc),
        },
    }
    if plate_raw:
        scene["plates"] = {
            "color":     list(PLATE_COLOR),
            "objects":   plate_objects,
            "positions": to_scene_mm(plate_raw, sc),
        }
    if hs_raw:
        scene["hs"] = {
            "color":     list(HS_COLOR),
            "objects":   hs_objects,
            "positions": to_scene_mm(hs_raw, sc),
        }
    if cu_pos or cv_pos:
        scene["coil"] = {
            "weights": export_coil_table(),
            "color_positive": list(COIL_ARROW_COLOR_POSITIVE),
            "color_negative": list(COIL_ARROW_COLOR_NEGATIVE),
            "groups": {
                "cv_corner": "c1..c8 (3 coils per corner)",
                "cv_edge": "e12.. optional override",
                "cu_face": "f1234..f3276",
            },
        }
    if cu_pos:
        scene["cu"] = {
            "objects":          cu_objects,
            "color_positive":   list(COIL_ARROW_COLOR_POSITIVE),
            "color_negative":   list(COIL_ARROW_COLOR_NEGATIVE),
            "sites": {
                "positions":   to_scene_mm(cu_pos, sc),
                "directions":  [[round(a, 4), round(b, 4), round(c, 4)]
                                 for (a, b, c) in cu_dir],
                "amplitudes":  [round(a, 4) for a in cu_amp],
            },
        }
    if cv_pos:
        scene["cv"] = {
            "objects":        cv_objects,
            "color_positive": list(COIL_ARROW_COLOR_POSITIVE),
            "color_negative": list(COIL_ARROW_COLOR_NEGATIVE),
            "sites": {
                "positions":   to_scene_mm(cv_pos, sc),
                "directions":  [[round(a, 4), round(b, 4), round(c, 4)]
                                 for (a, b, c) in cv_dir],
                "amplitudes":  [round(a, 4) for a in cv_amp],
            },
        }

    grid_payload = fea_grid_payload(fea_grid, sc) if fea_grid else None
    if grid_payload:
        scene["fea_grid"] = grid_payload

    scene_json = json.dumps(scene, separators=(',', ':'))
    n_cyl = len(cyl_raw)
    n_cap = len(cap_raw)
    n_pl  = len(plate_raw)
    n_hs  = len(hs_raw)
    n_cu  = len(cu_pos)
    n_cv  = len(cv_pos)
    print(
        f"[fea] scene JSON ready: {len(scene_json):,} bytes  "
        f"({n_cyl:,} cyl + {n_cap:,} cap + {n_pl:,} pl + {n_hs:,} hs + "
        f"{n_cu:,} cu + {n_cv:,} cv sites)"
    )

    if fea_strength_scale == 1.0:
        _scene_cache = scene
    return scene


def build_voxel_scene(force=False, fea_strength_scale=1.0):
    """Build the active experiment scene (see scene_registry / fea_config.FEA_SCENE_ID)."""
    from scene_registry import build_scene
    return build_scene(force=force, fea_strength_scale=fea_strength_scale)
