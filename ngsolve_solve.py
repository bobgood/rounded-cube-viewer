"""ngsolve_solve.py — Nonlinear magnetostatic solve for the "ngmesh" scene.

Solves the magnetic vector-potential A-formulation with H(curl) (Nédélec edge)
elements on the Netgen mesh from scene_ngmesh:

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
from scene_ngmesh import build_geometry
from fea_blines import trace_field_lines

_MU0 = 4.0e-7 * pi


def _solve_A(mesh, params, mu_r_steel: float, current_scale: float,
             saturate: bool = True):
    """Solve curl(nu curl A)=J on the metres mesh. Returns (B_cf, meta).

    saturate=True : nonlinear B–H reluctivity in the steel, Newton + current
                    ramping (physically correct, slower).
    saturate=False: linear solve at constant nu = 1/(mu0 mu_init) in the steel
                    (one direct factorization; much faster, no saturation).
    """
    from ngsolve import (
        HCurl, GridFunction, BilinearForm, LinearForm,
        curl, dx, CoefficientFunction, y, z, sqrt, Parameter,
    )

    c = params["center"]
    nu_air = 1.0 / _MU0
    nu_init = 1.0 / (_MU0 * max(float(mu_r_steel), 1.0))   # unsaturated steel
    b_knee2 = float(NG_IRON_B_KNEE_T) ** 2

    # Azimuthal current about +X at (·, c, c): phi_hat = x_hat × r_hat = (0,-rz,ry).
    # Positive → B toward +X (corner c1), per the e14 convention. Coords in metres.
    ry = y - c
    rz = z - c
    rmag = sqrt(ry * ry + rz * rz)
    jdir = CoefficientFunction((0, -rz, ry)) / rmag
    j_target = float(current_scale) * float(NG_COIL_CURRENT_A_MM2) * 1.0e6  # A/mm²→A/m²

    fes = HCurl(mesh, order=int(NG_SOLVE_ORDER), dirichlet="outer")
    u, v = fes.TnT()
    gfu = GridFunction(fes)
    gfu.vec[:] = 0.0

    if not saturate:
        # ── Linear: constant unsaturated permeability, single direct solve ──
        nu_lin = mesh.MaterialCF({"steel": nu_init}, default=nu_air)
        Jcf = mesh.MaterialCF({"coil": j_target * jdir},
                              default=CoefficientFunction((0, 0, 0)))
        a = BilinearForm(fes)
        a += nu_lin * curl(u) * curl(v) * dx
        a += 1e-6 * nu_lin * u * v * dx          # regularize gradient null space
        f = LinearForm(fes)
        f += Jcf * v * dx
        t1 = time.perf_counter()
        a.Assemble()
        f.Assemble()
        gfu.vec.data = a.mat.Inverse(fes.FreeDofs(), inverse="sparsecholesky") * f.vec
        t_solve = time.perf_counter() - t1
        meta = {"ndof": int(fes.ndof), "saturated": False,
                "solve_s": round(t_solve, 2)}
        return curl(gfu), meta

    # ── Nonlinear: B–H saturation via Newton + current ramping ──────────────
    from ngsolve.solvers import Newton

    def nu_iron(b2):
        # smooth reluctivity sigmoid in |B|^2: nu_init (soft) → nu_air (saturated).
        # explicit squaring, not **, to avoid pow's log(0) -> NaN at B=0.
        r = b2 / b_knee2
        return nu_air - (nu_air - nu_init) / (1.0 + r * r)

    cur = Parameter(0.0)
    Jcf = mesh.MaterialCF({"coil": cur * jdir}, default=CoefficientFunction((0, 0, 0)))
    Bu = curl(u)
    nu_cf = mesh.MaterialCF({"steel": nu_iron(Bu * Bu)}, default=nu_air)

    # Residual (semilinear) form, written in the trial proxy u so Newton can
    # linearize it around the current iterate.
    a = BilinearForm(fes)
    a += nu_cf * Bu * curl(v) * dx
    a += 1e-6 * nu_air * u * v * dx          # regularize gradient null space
    a += -Jcf * v * dx

    n_ramp = max(int(NG_SOLVE_RAMP_STEPS), 1)
    t1 = time.perf_counter()
    for k in range(1, n_ramp + 1):
        cur.Set(j_target * k / n_ramp)
        Newton(
            a, gfu, freedofs=fes.FreeDofs(),
            maxit=int(NG_SOLVE_NEWTON_MAXIT), maxerr=float(NG_SOLVE_NEWTON_TOL),
            inverse="sparsecholesky", dampfactor=1.0, printing=False,
        )
    t_solve = time.perf_counter() - t1

    meta = {"ndof": int(fes.ndof), "saturated": True, "ramp_steps": n_ramp,
            "solve_s": round(t_solve, 2)}
    return curl(gfu), meta


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


def solve_ng_bfield(*, mu_r: float = 1.0, fea_strength_scale: float = 1.0,
                    saturate: bool = True) -> dict:
    """Full NGSolve solve → traced field lines as a "bfield_lines" payload.

    saturate=True models B–H saturation (nonlinear Newton); False does a fast
    linear solve at the unsaturated permeability mu_r.
    """
    from ngsolve import Mesh

    t0 = time.perf_counter()
    ngmesh, params = build_geometry(length_scale=1.0e-3)   # metres → B in Tesla
    mesh = Mesh(ngmesh)
    t_mesh = time.perf_counter() - t0

    length_scale = params["length_scale"]
    half_extent_mm = params["half_extent"] / length_scale

    mode = "Newton+saturation" if saturate else "linear"
    print(
        f"[ng_solve] mesh ready ({t_mesh:.2f}s)  mu_init={mu_r:g}  "
        f"current_scale={fea_strength_scale:g}  {mode} (order={NG_SOLVE_ORDER})..."
    )
    B_cf, solve_meta = _solve_A(mesh, params, mu_r, fea_strength_scale,
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
        f"[ng_solve] done  ndof={solve_meta['ndof']:,}  solve={solve_meta['solve_s']}s  "
        f"({mode_note})  lines={meta['n_lines']}/{meta['n_seeds']} "
        f"seeds  max|B|={meta.get('max_B_T', 0.0):.3e} T"
    )
    return {"type": "bfield_lines", "lines": lines_scene, "meta": meta}
