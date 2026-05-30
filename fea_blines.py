"""fea_blines.py — Trace magnetic field lines (streamlines of B) on the voxel grid.

Given B = (Bx, By, Bz) sampled on a regular lattice (origin_mm, spacing h), we:
  1. Seed on a uniform spatial sub-lattice wherever |B| clears a floor (symmetric
     coverage — no bias toward whichever pole happens to be hottest).
  2. Integrate dx/ds = B/|B| (RK2) forward and backward from each seed.
  3. Continue into much weaker field (stop_floor) so lines arc pole-to-pole, and
     stop at the domain edge, where |B| < stop_floor, or after max steps.

Each emitted point is (x, y, z, b_norm) where b_norm = |B| / max|B| in [0, 1] for
strength-based colouring. Output is in millimetres; the caller scales to scene units.
This is a "rough" visualization aid, not a precise flux computation.
"""

from __future__ import annotations

import numpy as np


def _sample_B(p, Bx, By, Bz, origin, h, nx, ny, nz):
    """Trilinear-interpolate B at world point p (mm). Returns (vec3, ok)."""
    gx = (p[0] - origin[0]) / h
    gy = (p[1] - origin[1]) / h
    gz = (p[2] - origin[2]) / h
    i0 = int(np.floor(gx)); j0 = int(np.floor(gy)); k0 = int(np.floor(gz))
    if i0 < 0 or j0 < 0 or k0 < 0 or i0 >= nx - 1 or j0 >= ny - 1 or k0 >= nz - 1:
        return None, False
    fx = gx - i0; fy = gy - j0; fz = gz - k0
    i1, j1, k1 = i0 + 1, j0 + 1, k0 + 1
    out = np.empty(3)
    for ci, comp in enumerate((Bx, By, Bz)):
        c000 = comp[i0, j0, k0]; c100 = comp[i1, j0, k0]
        c010 = comp[i0, j1, k0]; c110 = comp[i1, j1, k0]
        c001 = comp[i0, j0, k1]; c101 = comp[i1, j0, k1]
        c011 = comp[i0, j1, k1]; c111 = comp[i1, j1, k1]
        c00 = c000 * (1 - fx) + c100 * fx
        c10 = c010 * (1 - fx) + c110 * fx
        c01 = c001 * (1 - fx) + c101 * fx
        c11 = c011 * (1 - fx) + c111 * fx
        c0 = c00 * (1 - fy) + c10 * fy
        c1 = c01 * (1 - fy) + c11 * fy
        out[ci] = c0 * (1 - fz) + c1 * fz
    return out, True


def _trace_one(seed, sign, Bx, By, Bz, origin, h, nx, ny, nz, step, max_steps, stop_floor):
    """Integrate a half-line from seed along +B (sign=+1) or -B (sign=-1).

    Returns a list of (x, y, z, |B|) points (excluding the seed itself).
    """
    pts = []
    p = np.array(seed, dtype=np.float64)
    for _ in range(max_steps):
        b, ok = _sample_B(p, Bx, By, Bz, origin, h, nx, ny, nz)
        if not ok:
            break
        mag = float(np.linalg.norm(b))
        if mag < stop_floor:
            break
        d = (b / mag) * sign
        pmid = p + d * (step * 0.5)
        bm, okm = _sample_B(pmid, Bx, By, Bz, origin, h, nx, ny, nz)
        mmag = mag
        if okm:
            mm = float(np.linalg.norm(bm))
            if mm >= stop_floor:
                d = (bm / mm) * sign
                mmag = mm
        p = p + d * step
        pts.append((float(p[0]), float(p[1]), float(p[2]), mmag))
    return pts


def trace_field_lines(
    sol: dict,
    *,
    max_lines: int = 140,
    step_mm: float = 1.0,
    max_steps: int = 900,
    seed_stride: int = 2,
    min_B_frac: float = 0.04,
    stop_frac: float = 0.004,
) -> dict:
    """Trace streamlines from a solve_b_arrays() result. Returns lines (mm) + meta.

    Seeds: uniform spatial sub-lattice (every ``seed_stride`` cells) where
    |B| > ``min_B_frac`` * max|B|.  Lines continue until |B| < ``stop_frac`` * max|B|.
    """
    Bx, By, Bz = sol["Bx"], sol["By"], sol["Bz"]
    B_mag = sol["B_mag"]
    origin = np.asarray(sol["origin_mm"], dtype=np.float64)
    h = float(sol["spacing_mm"])
    nx, ny, nz = (int(s) for s in sol["size"])

    max_B = float(B_mag.max())
    if max_B <= 0.0:
        return {"lines": [], "meta": {"max_B_T": 0.0, "n_lines": 0, "n_seeds": 0}}

    seed_floor = min_B_frac * max_B
    stop_floor = max(stop_frac * max_B, 1e-12)

    # Uniform spatial sub-lattice (symmetric coverage), gated by the seed floor.
    s = max(1, int(seed_stride))
    ii, jj, kk = np.meshgrid(
        np.arange(1, nx - 1, s),
        np.arange(1, ny - 1, s),
        np.arange(1, nz - 1, s),
        indexing="ij",
    )
    ci = ii.ravel(); cj = jj.ravel(); ck = kk.ravel()
    keep = B_mag[ci, cj, ck] > seed_floor
    ci, cj, ck = ci[keep], cj[keep], ck[keep]
    n_seeds = int(ci.size)

    # Even spatial spread to max_lines (deterministic; no random clustering).
    if n_seeds > max_lines:
        pick = np.linspace(0, n_seeds - 1, max_lines).astype(int)
        ci, cj, ck = ci[pick], cj[pick], ck[pick]

    inv_max = 1.0 / max_B
    lines = []
    for a, b_, c_ in zip(ci, cj, ck):
        seed = origin + np.array([a, b_, c_], dtype=np.float64) * h
        seed_mag = float(B_mag[a, b_, c_])
        fwd = _trace_one(seed, +1.0, Bx, By, Bz, origin, h, nx, ny, nz,
                         step_mm, max_steps, stop_floor)
        bwd = _trace_one(seed, -1.0, Bx, By, Bz, origin, h, nx, ny, nz,
                         step_mm, max_steps, stop_floor)
        poly = (
            list(reversed(bwd))
            + [(float(seed[0]), float(seed[1]), float(seed[2]), seed_mag)]
            + fwd
        )
        if len(poly) >= 4:
            lines.append([(x, y, z, min(1.0, m * inv_max)) for (x, y, z, m) in poly])

    return {
        "lines": lines,
        "meta": {
            "max_B_T": max_B,
            "n_lines": len(lines),
            "n_seeds": n_seeds,
            "seed_floor_T": seed_floor,
            "stop_floor_T": stop_floor,
        },
    }
