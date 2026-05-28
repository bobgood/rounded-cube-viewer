"""fea_model.py — Voxel frame geometry for the FEA viewer.

Generates a regular n-gon prism frame:
  - 3n cylinder rods
  - 2n corner caps  — full sphere + 3 unclipped collar stubs per corner
  - 6 plate faces   — 4 spin-wheel quadrant panels per face (n=4 only)

All frame elements are inset from the bounding box by FRAME_INSET_MM so that
the cap spheres protrude slightly past each face for a ball-joint look.

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
}
Each "objects" list: [{"id":"cy0","label":"Cy 0","start":0,"count":N}, ...]
Plate ids use the format  F{face}{quad}  e.g. "F0A", "F3C".
"""

import json
import math

from fea_config import (
    VOXEL_SIZE_MM,
    CYLINDER_LENGTH_MM,
    CYLINDER_RADIUS_MM,
    CYLINDER_COLOR,
    CAP_DIAMETER_MM,
    CAP_COLOR,
    COLLAR_DIAMETER_MM,
    FRAME_SIDES,
    FRAME_EDGE_MM,
    FRAME_HEIGHT_MM,
    FRAME_GAP_MM,
    FRAME_INSET_MM,
    PLATE_THICKNESS_MM,
    PLATE_GAP_MM,
    SPIN_WHEEL_OFFSET_MM,
    PLATE_EDGE_INSET_MM,
    PLATE_COLOR,
    OU_ROUNDING_MM,
    OU_COLOR,
    HOLE_DIAMETER_MM,
    HO_COLOR,
    MM_TO_SCENE,
)


# ── Primitive voxel generators ───────────────────────────────────────────────

def _cylinder_voxels_x(length_mm, radius_mm=None, step=VOXEL_SIZE_MM):
    """Solid cylinder along the +X axis, centred at origin."""
    if radius_mm is None:
        radius_mm = CYLINDER_RADIUS_MM
    half_l = length_mm / 2.0
    r_sq   = radius_mm ** 2
    n_l    = int(half_l    / step)
    n_r    = int(radius_mm / step)
    voxels = []
    for ix in range(-n_l, n_l + 1):
        x = ix * step
        if abs(x) > half_l:
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


def _box_voxels(u_lo, u_hi, v_lo, v_hi, thickness, step=VOXEL_SIZE_MM):
    """Rectangular slab in UV-space; W axis runs from 0 (outer) to thickness (inward)."""
    if u_lo >= u_hi or v_lo >= v_hi or thickness <= 0:
        return []
    nu = max(1, int((u_hi - u_lo) / step))
    nv = max(1, int((v_hi - v_lo) / step))
    nt = max(1, int(thickness     / step))
    voxels = []
    for iu in range(nu):
        u = u_lo + (iu + 0.5) * (u_hi - u_lo) / nu
        for iv in range(nv):
            v = v_lo + (iv + 0.5) * (v_hi - v_lo) / nv
            for it in range(nt):
                w = (it + 0.5) * thickness / nt
                voxels.append((u, v, w))
    return voxels


def _rotate_z(voxels, angle):
    c, s = math.cos(angle), math.sin(angle)
    return [(c * x - s * y, s * x + c * y, z) for (x, y, z) in voxels]


def _translate(voxels, dx, dy, dz):
    return [(x + dx, y + dy, z + dz) for (x, y, z) in voxels]


# ── Scene builder ─────────────────────────────────────────────────────────────

_scene_cache = None


def invalidate_cache():
    global _scene_cache
    _scene_cache = None


def build_voxel_scene(force=False):
    """Build (or return cached) the complete voxel scene dict."""
    global _scene_cache
    if _scene_cache is not None and not force:
        return _scene_cache

    n   = FRAME_SIDES
    E   = FRAME_EDGE_MM       # bounding-box edge (plates / Ou use this)
    H   = FRAME_HEIGHT_MM     # bounding-box height
    gap = FRAME_GAP_MM

    # ── Inset: frame elements moved inward from the bounding-box faces ────────
    ins    = FRAME_INSET_MM
    E_e    = E - 2 * ins        # effective edge for element placement
    H_e    = H - 2 * ins        # effective height for element placement
    half_h = H_e / 2.0

    R  = E_e / (2.0 * math.sin(math.pi / n))
    ao = math.pi / n
    vertices = [
        (R * math.cos(2 * math.pi * k / n + ao),
         R * math.sin(2 * math.pi * k / n + ao))
        for k in range(n)
    ]

    ring_len  = max(VOXEL_SIZE_MM, min(CYLINDER_LENGTH_MM, E_e - 2 * gap))
    vert_len  = max(VOXEL_SIZE_MM, min(CYLINDER_LENGTH_MM, H_e - 2 * gap))
    gap_ring  = (E_e - ring_len) / 2.0
    gap_strut = (H_e - vert_len) / 2.0

    # Templates (along X axis; strut is re-mapped to Z axis below)
    ring_tpl       = _cylinder_voxels_x(ring_len)
    vert_tpl       = _cylinder_voxels_x(vert_len)
    cap_r          = CAP_DIAMETER_MM / 2.0
    cap_sphere_tpl = _sphere_voxels(cap_r)
    collar_r       = COLLAR_DIAMETER_MM / 2.0
    collar_ext     = VOXEL_SIZE_MM      # extra extension past sphere centre
    collar_ring_tpl  = _cylinder_voxels_x(gap_ring  + collar_ext, collar_r) if gap_ring  > 0 else []
    collar_strut_tpl = _cylinder_voxels_x(gap_strut + collar_ext, collar_r) if gap_strut > 0 else []

    # Map strut templates from X-axis to Z-axis: (x,y,z) -> (y,z,x)
    vert_z          = [(y, z, x) for (x, y, z) in vert_tpl]
    collar_strut_z  = [(y, z, x) for (x, y, z) in collar_strut_tpl]

    print(
        f"[fea] {n}-gon: {n*3} cyl + {n*2} caps  |  "
        f"ring={ring_len:.1f}mm  strut={vert_len:.1f}mm  "
        f"cap_r={cap_r:.1f}mm  collar_r={collar_r:.2f}mm"
    )

    cyl_raw:    list = []
    cap_raw:    list = []
    cyl_objects: list = []
    cap_objects:  list = []
    cyl_idx = 0

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
            cyl_objects.append({"id": f"cy{cyl_idx}", "label": f"Cy {cyl_idx}",
                                 "start": start, "count": len(cyl_raw) - start})
            cyl_idx += 1

    # ── Strut cylinders: 1 per vertex ─────────────────────────────────────────
    for k in range(n):
        vx, vy = vertices[k]
        start = len(cyl_raw)
        cyl_raw.extend(_translate(vert_z, vx, vy, 0.0))
        cyl_objects.append({"id": f"cy{cyl_idx}", "label": f"Cy {cyl_idx}",
                             "start": start, "count": len(cyl_raw) - start})
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

            # Ring collar toward previous vertex
            if collar_ring_tpl:
                a = math.atan2(vy_prev - vy, vx_prev - vx)
                half_len = (gap_ring + collar_ext) / 2.0
                cap_raw.extend(
                    _translate(_rotate_z(collar_ring_tpl, a),
                                vx + math.cos(a) * half_len,
                                vy + math.sin(a) * half_len,
                                cz))

            # Ring collar toward next vertex
            if collar_ring_tpl:
                a = math.atan2(vy_next - vy, vx_next - vx)
                half_len = (gap_ring + collar_ext) / 2.0
                cap_raw.extend(
                    _translate(_rotate_z(collar_ring_tpl, a),
                                vx + math.cos(a) * half_len,
                                vy + math.sin(a) * half_len,
                                cz))

            # Strut collar (Z direction, toward cylinder end)
            if collar_strut_z:
                ccz = cz - z_sign * (gap_strut + collar_ext) / 2.0
                cap_raw.extend(_translate(collar_strut_z, vx, vy, ccz))

            cap_objects.append({"id": f"ca{cap_idx}", "label": f"Ca {cap_idx}",
                                 "start": start, "count": len(cap_raw) - start})
            cap_idx += 1

    # ── Plates (n=4 / cube only) ───────────────────────────────────────────────
    plate_raw:     list = []
    plate_objects: list = []

    if n == 4:
        t  = PLATE_THICKNESS_MM
        g  = PLATE_GAP_MM / 2.0
        d  = SPIN_WHEEL_OFFSET_MM
        pe = PLATE_EDGE_INSET_MM
        # Plates sit on the ORIGINAL bounding-box faces (E x H), not the inset frame.
        h  = E / 2.0 - pe
        hz = H / 2.0 - pe

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
                    plate_raw.append(xfm(u, v, w))
                count = len(plate_raw) - start
                if count > 0:
                    label = f"F{fi}{qname}"
                    plate_objects.append({"id": label, "label": label,
                                          "start": start, "count": count})

    total = len(cyl_raw) + len(cap_raw) + len(plate_raw)
    print(
        f"[fea] total voxels: {total:,}  "
        f"({len(cyl_raw):,} cyl + {len(cap_raw):,} cap + {len(plate_raw):,} plates)"
    )

    # ── Convert mm -> scene units ─────────────────────────────────────────────
    sc = MM_TO_SCENE

    def to_scene(raw):
        return [[round(x * sc, 3), round(y * sc, 3), round(z * sc, 3)]
                for (x, y, z) in raw]

    scene = {
        "type":       "voxel_scene",
        "voxel_size": round(VOXEL_SIZE_MM * sc, 4),
        "frame_config": {
            "edge_mm":          E,
            "height_mm":        H,
            "ou_rounding_mm":   OU_ROUNDING_MM,
            "ou_color":         list(OU_COLOR),
            "hole_diameter_mm": HOLE_DIAMETER_MM,
            "ho_color":         list(HO_COLOR),
            "mm_to_scene":      sc,
        },
        "cylinders": {
            "color":     list(CYLINDER_COLOR),
            "objects":   cyl_objects,
            "positions": to_scene(cyl_raw),
        },
        "caps": {
            "color":     list(CAP_COLOR),
            "objects":   cap_objects,
            "positions": to_scene(cap_raw),
        },
    }
    if plate_raw:
        scene["plates"] = {
            "color":     list(PLATE_COLOR),
            "objects":   plate_objects,
            "positions": to_scene(plate_raw),
        }

    scene_json = json.dumps(scene, separators=(',', ':'))
    n_cyl = len(cyl_raw)
    n_cap = len(cap_raw)
    n_pl  = len(plate_raw)
    print(
        f"[fea] scene JSON ready: {len(scene_json):,} bytes  "
        f"({n_cyl:,} cyl + {n_cap:,} cap + {n_pl:,} plate voxels)"
    )

    _scene_cache = scene
    return scene
