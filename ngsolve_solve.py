"""ngsolve_solve.py — Nonlinear magnetostatic solve for the dipole scenes.

Solves the magnetic vector-potential A-formulation with H(curl) (Nédélec edge)
elements on the Netgen mesh from any dipole scene (1dipole / 12dipoles_ng) via
the shared ng_dipoles builder; J is summed over every coil region:

    curl( nu(|B|) curl A ) = J

  - nu(|B|): nonlinear reluctivity in the steel rod (B–H saturation for typical
             iron, see ng_config.NG_IRON_B_KNEE_T); 1/mu0 in coil and air.
             nu(0) = 1/(mu0 * mu_init) where mu_init is the "Steel μ" slider.
  - J:       azimuthal coil current = NG_COIL_CURRENT_A_MM2 * strength_scale.
             Direction follows the cube-edge convention — positive on e{c1}{c2}
             drives B toward the FIRST corner. For this scene (edge e14) → +X.
  - Far field: tangential A = 0 on the outer air-box boundary ("outer").

The mesh is built in METRES (length_scale 1e-3) so B = curl(A) comes out in real
Tesla and the saturation knee is physically meaningful.

The nonlinear system is solved by Newton iteration with current ramping (load
stepping): the source is raised in NG_SOLVE_RAMP_STEPS increments, each warm-
started from the previous, with a direct sparse-Cholesky inner solve (no
iterative convergence risk). A tiny mass term regularizes the curl-curl
gradient null space.

B is then sampled onto a regular lattice (reported in mm) and streamlined with
the existing fea_blines tracer, shipping as the same "bfield_lines" payload the
viewer already renders.
"""

from __future__ import annotations

import time
from math import pi

import numpy as np

from cube_config import MM_TO_SCENE
from ng_config import (
    NG_COIL_CURRENT_A_MM2,
    NG_IRON_B_KNEE_T,
    NG_SOLVE_ORDER,
    NG_SOLVE_RAMP_STEPS,
    NG_SOLVE_NEWTON_MAXIT,
    NG_SOLVE_NEWTON_TOL,
    NG_FIELD_SAMPLE_MM,
)
from fea_config import (
    FEA_BLINE_MAX_LINES,
    FEA_BLINE_STEP_MM,
    FEA_BLINE_MAX_STEPS,
    FEA_BLINE_SEED_STRIDE,
    FEA_BLINE_MIN_B_FRAC,
    FEA_BLINE_STOP_FRAC,
)
from fea_blines import trace_field_lines

_MU0 = 4.0e-7 * pi


def _coil_jdir(ax, c):
    """Unit azimuthal current direction around axis `ax` through center `c`.

    j_hat = (a × r_hat); since a ⟂ r_hat and |a|=1, |a × r| = |r| = rmag, so
    dividing the cross product by rmag yields a unit azimuthal field. Matches the
    single-dipole formula when a = +X, c = (·, c, c).
    """
    from ngsolve import x, y, z, CoefficientFunction, sqrt
    px, py, pz = x - c[0], y - c[1], z - c[2]
    adp = ax[0] * px + ax[1] * py + ax[2] * pz
    rx, ry, rz = px - adp * ax[0], py - adp * ax[1], pz - adp * ax[2]
    rmag = sqrt(rx * rx + ry * ry + rz * rz)
    tx = ax[1] * rz - ax[2] * ry
    ty = ax[2] * rx - ax[0] * rz
    tz = ax[0] * ry - ax[1] * rx
    return CoefficientFunction((tx, ty, tz)) / rmag


def _solve_A_multi(mesh, dipoles, mu_r_steel: float, current_scale: float,
                   saturate: bool = False):
    """Solve curl(nu curl A)=J for many coils (each its own material region).

    `dipoles` is the list of per-dipole param dicts from ng_dipoles (must carry
    coil_mat / center / axis / weight, in the SAME metres units as the mesh).
    All rods share material "steel" (isotropic nu(|B|), same everywhere); each
    coil i lives in material "coil{i}" so J can be set per-region with its own
    axis and signed weight.
    """
    from ngsolve import (
        HCurl, GridFunction, BilinearForm, LinearForm,
        curl, dx, CoefficientFunction, Parameter,
    )

    nu_air = 1.0 / _MU0
    nu_init = 1.0 / (_MU0 * max(float(mu_r_steel), 1.0))
    b_knee2 = float(NG_IRON_B_KNEE_T) ** 2
    j_unit = float(current_scale) * float(NG_COIL_CURRENT_A_MM2) * 1.0e6

    # Per-coil current density CF (full target), keyed by coil material name.
    j_map = {}
    for dp in dipoles:
        w = float(dp.get("weight", 0.0))
        if abs(w) < 1e-12 or not dp.get("has_coil", True):
            continue
        j_map[dp["coil_mat"]] = (w * j_unit) * _coil_jdir(dp["axis"], dp["center"])
    zero = CoefficientFunction((0, 0, 0))

    fes = HCurl(mesh, order=int(NG_SOLVE_ORDER), dirichlet="outer")
    u, v = fes.TnT()
    gfu = GridFunction(fes)
    gfu.vec[:] = 0.0

    if not saturate:
        nu_lin = mesh.MaterialCF({"steel": nu_init}, default=nu_air)
        Jcf = mesh.MaterialCF(j_map, default=zero) if j_map else zero
        a = BilinearForm(fes)
        a += nu_lin * curl(u) * curl(v) * dx
        a += 1e-6 * nu_lin * u * v * dx
        f = LinearForm(fes)
        f += Jcf * v * dx
        t1 = time.perf_counter()
        a.Assemble()
        f.Assemble()
        gfu.vec.data = a.mat.Inverse(fes.FreeDofs(), inverse="sparsecholesky") * f.vec
        t_solve = time.perf_counter() - t1
        return curl(gfu), {"ndof": int(fes.ndof), "saturated": False,
                           "n_coils": len(j_map), "solve_s": round(t_solve, 2)}

    from ngsolve.solvers import Newton

    def nu_iron(b2):
        r = b2 / b_knee2
        return nu_air - (nu_air - nu_init) / (1.0 + r * r)

    cur = Parameter(0.0)   # unitless ramp 0 → 1
    Jbase = mesh.MaterialCF(j_map, default=zero) if j_map else zero
    Bu = curl(u)
    nu_cf = mesh.MaterialCF({"steel": nu_iron(Bu * Bu)}, default=nu_air)

    a = BilinearForm(fes)
    a += nu_cf * Bu * curl(v) * dx
    a += 1e-6 * nu_air * u * v * dx
    a += -(cur * Jbase) * v * dx

    n_ramp = max(int(NG_SOLVE_RAMP_STEPS), 1)
    t1 = time.perf_counter()
    for k in range(1, n_ramp + 1):
        cur.Set(k / n_ramp)
        Newton(
            a, gfu, freedofs=fes.FreeDofs(),
            maxit=int(NG_SOLVE_NEWTON_MAXIT), maxerr=float(NG_SOLVE_NEWTON_TOL),
            inverse="sparsecholesky", dampfactor=1.0, printing=False,
        )
    t_solve = time.perf_counter() - t1
    return curl(gfu), {"ndof": int(fes.ndof), "saturated": True, "ramp_steps": n_ramp,
                       "n_coils": len(j_map), "solve_s": round(t_solve, 2)}


def _sample_B(mesh, B_cf, half_extent_mm: float, step_mm: float, length_scale: float):
    """Sample B onto a regular interior lattice. Returns a solve_b_arrays-like dict.

    Grid coordinates are defined/reported in mm but the mesh is in metres, so
    evaluation points are scaled by length_scale. B values stay in Tesla.
    """
    h = float(half_extent_mm)
    step = float(step_mm)
    s = float(length_scale)
    coords = np.arange(-h + step, h - step / 2.0, step)
    n = len(coords)

    X, Y, Z = np.meshgrid(coords, coords, coords, indexing="ij")
    pts = mesh(X.ravel() * s, Y.ravel() * s, Z.ravel() * s)
    vals = np.asarray(B_cf(pts), dtype=np.float64).reshape(n, n, n, 3)
    vals = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)

    Bx = np.ascontiguousarray(vals[..., 0])
    By = np.ascontiguousarray(vals[..., 1])
    Bz = np.ascontiguousarray(vals[..., 2])
    B_mag = np.sqrt(Bx * Bx + By * By + Bz * Bz)
    return {
        "Bx": Bx, "By": By, "Bz": Bz, "B_mag": B_mag,
        "origin_mm": [float(coords[0]), float(coords[0]), float(coords[0])],
        "spacing_mm": step,
        "size": [n, n, n],
    }


def _run_scene_solve(build_geometry, *, tag: str, mu_r: float,
                     fea_strength_scale: float, saturate: bool) -> dict:
    """Shared solve pipeline for any dipole scene.

    `build_geometry(length_scale)` must return (ngmesh, dipoles, meta) in the
    ng_dipoles format (dipoles = per-coil param dicts; meta has half_extent +
    length_scale). Meshes in metres so B = curl(A) is in real Tesla, solves the
    curl-curl A-formulation (linear or Newton+ramp), samples B and traces lines.
    """
    from ngsolve import Mesh

    t0 = time.perf_counter()
    ngmesh, dipoles, meta_g = build_geometry(length_scale=1.0e-3)   # metres → Tesla
    mesh = Mesh(ngmesh)
    t_mesh = time.perf_counter() - t0

    length_scale = meta_g["length_scale"]
    half_extent_mm = meta_g["half_extent"] / length_scale
    n_active = sum(1 for dp in dipoles
                   if abs(float(dp.get("weight", 0.0))) > 1e-12 and dp.get("has_coil", True))
    mode = "Newton+saturation" if saturate else "linear"
    print(
        f"[ng_solve:{tag}] mesh ready ({t_mesh:.2f}s)  coils_active={n_active}  "
        f"mu_init={mu_r:g}  current_scale={fea_strength_scale:g}  "
        f"{mode} (order={NG_SOLVE_ORDER})..."
    )

    B_cf, solve_meta = _solve_A_multi(mesh, dipoles, mu_r, fea_strength_scale,
                                      saturate=saturate)
    sol = _sample_B(mesh, B_cf, half_extent_mm, NG_FIELD_SAMPLE_MM, length_scale)

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
    lines_scene = [
        [[round(px * sc, 3), round(py * sc, 3), round(pz * sc, 3), round(b, 3)]
         for (px, py, pz, b) in poly]
        for poly in traced["lines"]
    ]
    meta = dict(traced["meta"])
    meta.update(solve_meta)
    meta["size"] = sol["size"]
    meta["sample_mm"] = NG_FIELD_SAMPLE_MM
    meta["mu_r"] = float(mu_r)
    meta["b_knee_T"] = float(NG_IRON_B_KNEE_T)
    meta["solver"] = "ngsolve-hcurl-nl" if saturate else "ngsolve-hcurl-lin"
    mode_note = (f"saturated, {solve_meta['ramp_steps']} ramp steps"
                 if solve_meta.get("saturated") else "linear")
    print(
        f"[ng_solve:{tag}] done  ndof={solve_meta['ndof']:,}  "
        f"coils={solve_meta.get('n_coils')}  solve={solve_meta['solve_s']}s  "
        f"({mode_note})  lines={meta['n_lines']}/{meta['n_seeds']} "
        f"seeds  max|B|={meta.get('max_B_T', 0.0):.3e} T"
    )
    return {"type": "bfield_lines", "lines": lines_scene, "meta": meta}


def solve_ng_bfield(*, mu_r: float = 1.0, fea_strength_scale: float = 1.0,
                    saturate: bool = True) -> dict:
    """Solve the single-dipole ("1dipole") scene → "bfield_lines" payload."""
    from scene_ngmesh import build_geometry
    return _run_scene_solve(build_geometry, tag="1dipole", mu_r=mu_r,
                            fea_strength_scale=fea_strength_scale, saturate=saturate)


def solve_ng12_bfield(*, mu_r: float = 1.0, fea_strength_scale: float = 1.0,
                      saturate: bool = False) -> dict:
    """Solve the 12-dipole scene (many coils) → "bfield_lines" payload."""
    from scene_ng12dipoles import build_geometry
    return _run_scene_solve(build_geometry, tag="12dipole", mu_r=mu_r,
                            fea_strength_scale=fea_strength_scale, saturate=saturate)
