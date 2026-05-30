"""fea_solve.py — Magnetostatic B-field solve on the FEA voxel grid.

Set FEA_RUN_SOLVE_TESTS = True in fea_config.py to run inline unit tests after each solve.
"""

from __future__ import annotations

import time

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import LinearOperator, cg, factorized

from fea_config import (
    FEA_RUN_SOLVE_TESTS,
    FEA_SOLVE_CG_LOG_EVERY,
    FEA_SOLVE_CG_MAXITER,
    FEA_SOLVE_CG_MAXITER_COUPLED,
    FEA_SOLVE_CG_RTOL,
    FEA_SOLVE_CG_RTOL_COUPLED,
    FEA_SOLVE_FORMULATION,
    FEA_SOLVE_METHOD,
    FEA_SOLVE_PIN_AT_ORIGIN,
    FEA_SOLVE_STORE_FULL_B,
    FEA_SOLVE_UNIFORM_MU_R,
    MU0,
)


def _log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


# ── Grid rasterization ─────────────────────────────────────────────────────────


def _pos_to_ijk(x_mm: float, y_mm: float, z_mm: float, origin_mm, h: float) -> tuple[int, int, int]:
    ox, oy, oz = origin_mm
    return (
        int(round(x_mm / h)) - int(round(ox / h)),
        int(round(y_mm / h)) - int(round(oy / h)),
        int(round(z_mm / h)) - int(round(oz / h)),
    )


def grid_arrays(fea_grid: dict) -> dict:
    """Rasterize fea_grid sparse lists into full nx×ny×nz μ_r and J (A/mm²)."""
    h = float(fea_grid["spacing_mm"])
    nx, ny, nz = (int(fea_grid["size"][0]), int(fea_grid["size"][1]), int(fea_grid["size"][2]))
    origin = fea_grid["origin_mm"]

    mu_r = np.ones((nx, ny, nz), dtype=np.float64)
    Jx = np.zeros((nx, ny, nz), dtype=np.float64)
    Jy = np.zeros((nx, ny, nz), dtype=np.float64)
    Jz = np.zeros((nx, ny, nz), dtype=np.float64)

    steel_mu = float(fea_grid["cells"]["steel"]["mu_r"])
    coil_mu = float(fea_grid["cells"]["coil"]["mu_r"])

    for (x, y, z) in fea_grid["metal"]["positions_mm"]:
        i, j, k = _pos_to_ijk(x, y, z, origin, h)
        if 0 <= i < nx and 0 <= j < ny and 0 <= k < nz:
            mu_r[i, j, k] = steel_mu

    coil = fea_grid["cells"]["coil"]
    for idx, (x, y, z) in enumerate(coil["positions_mm"]):
        i, j, k = _pos_to_ijk(x, y, z, origin, h)
        if 0 <= i < nx and 0 <= j < ny and 0 <= k < nz:
            mu_r[i, j, k] = coil_mu
            jx, jy, jz = coil["J_mm"][idx]
            Jx[i, j, k] = jx
            Jy[i, j, k] = jy
            Jz[i, j, k] = jz

    nu = 1.0 / (MU0 * mu_r)
    return {
        "h": h,
        "nx": nx,
        "ny": ny,
        "nz": nz,
        "origin_mm": origin,
        "mu_r": mu_r,
        "nu": nu,
        "Jx": Jx,
        "Jy": Jy,
        "Jz": Jz,
        "steel_mu_r": steel_mu,
        "coil_mu_r": coil_mu,
    }


def _face_nu_array(nu_a: np.ndarray, nu_b: np.ndarray) -> np.ndarray:
    denom = nu_a + nu_b
    with np.errstate(divide="ignore", invalid="ignore"):
        nf = np.where(denom > 0, 2.0 * nu_a * nu_b / denom, 0.0)
    return nf


def _axis_links(nu: np.ndarray, axis: int, inv_h2: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """COO entries for +axis neighbors: (row, col, coeff)."""
    nx, ny, nz = nu.shape
    slc_a = [slice(None)] * 3
    slc_b = [slice(None)] * 3
    slc_a[axis] = slice(None, -1)
    slc_b[axis] = slice(1, None)
    nu_a = nu[tuple(slc_a)]
    nu_b = nu[tuple(slc_b)]
    nf = _face_nu_array(nu_a, nu_b) * inv_h2

    shape_a = nu_a.shape
    ii = np.arange(shape_a[0])[:, None, None]
    jj = np.arange(shape_a[1])[None, :, None]
    kk = np.arange(shape_a[2])[None, None, :]
    if axis == 0:
        p = (ii + nx * (jj + ny * kk)).ravel()
        q = ((ii + 1) + nx * (jj + ny * kk)).ravel()
    elif axis == 1:
        p = (ii + nx * (jj + ny * kk)).ravel()
        q = (ii + nx * ((jj + 1) + ny * kk)).ravel()
    else:
        p = (ii + nx * (jj + ny * kk)).ravel()
        q = (ii + nx * (jj + ny * (kk + 1))).ravel()
    nf = nf.ravel()
    return p, q, nf


def _pid(i: int, j: int, k: int, nx: int, ny: int, nz: int, comp: int) -> int:
    """Flat index for stacked unknown [Ax, Ay, Az] (comp 0,1,2)."""
    n = nx * ny * nz
    return (i + nx * (j + ny * k)) + comp * n


def assemble_coupled_curl_nu_curl(nu: np.ndarray, h: float) -> sparse.csr_matrix:
    """3N x 3N stencil for curl(nu curl A) on a Cartesian grid (Neumann exterior).

    Interior: (curl curl A)_x = d_yy Ax + d_zz Ax - d_xy Ay + d_xz Az (and cyclic y,z).
    nu is evaluated at the cell centre; natural (zero-flux) boundaries via mirror ghosts.
    """
    nx, ny, nz = nu.shape
    n = nx * ny * nz
    n3 = 3 * n
    inv_h2 = 1.0 / (h * h)
    inv_4h2 = 0.25 * inv_h2

    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []

    def add(r: int, c: int, v: float) -> None:
        rows.append(r)
        cols.append(c)
        data.append(v)

    def second_deriv(fi: int, fj: int, fk: int, axis: int, comp: int, row: int, nu_c: float) -> None:
        """Add nu * d_axis_axis f at (fi,fj,fk) to row (Neumann at boundaries)."""
        if axis == 0:
            i, j, k = fi, fj, fk
            if i == 0:
                add(row, _pid(i, j, k, nx, ny, nz, comp), -2.0 * nu_c * inv_h2)
                add(row, _pid(i + 1, j, k, nx, ny, nz, comp), 2.0 * nu_c * inv_h2)
            elif i == nx - 1:
                add(row, _pid(i - 1, j, k, nx, ny, nz, comp), 2.0 * nu_c * inv_h2)
                add(row, _pid(i, j, k, nx, ny, nz, comp), -2.0 * nu_c * inv_h2)
            else:
                add(row, _pid(i - 1, j, k, nx, ny, nz, comp), nu_c * inv_h2)
                add(row, _pid(i, j, k, nx, ny, nz, comp), -2.0 * nu_c * inv_h2)
                add(row, _pid(i + 1, j, k, nx, ny, nz, comp), nu_c * inv_h2)
        elif axis == 1:
            i, j, k = fi, fj, fk
            if j == 0:
                add(row, _pid(i, j, k, nx, ny, nz, comp), -2.0 * nu_c * inv_h2)
                add(row, _pid(i, j + 1, k, nx, ny, nz, comp), 2.0 * nu_c * inv_h2)
            elif j == ny - 1:
                add(row, _pid(i, j - 1, k, nx, ny, nz, comp), 2.0 * nu_c * inv_h2)
                add(row, _pid(i, j, k, nx, ny, nz, comp), -2.0 * nu_c * inv_h2)
            else:
                add(row, _pid(i, j - 1, k, nx, ny, nz, comp), nu_c * inv_h2)
                add(row, _pid(i, j, k, nx, ny, nz, comp), -2.0 * nu_c * inv_h2)
                add(row, _pid(i, j + 1, k, nx, ny, nz, comp), nu_c * inv_h2)
        else:
            i, j, k = fi, fj, fk
            if k == 0:
                add(row, _pid(i, j, k, nx, ny, nz, comp), -2.0 * nu_c * inv_h2)
                add(row, _pid(i, j, k + 1, nx, ny, nz, comp), 2.0 * nu_c * inv_h2)
            elif k == nz - 1:
                add(row, _pid(i, j, k - 1, nx, ny, nz, comp), 2.0 * nu_c * inv_h2)
                add(row, _pid(i, j, k, nx, ny, nz, comp), -2.0 * nu_c * inv_h2)
            else:
                add(row, _pid(i, j, k - 1, nx, ny, nz, comp), nu_c * inv_h2)
                add(row, _pid(i, j, k, nx, ny, nz, comp), -2.0 * nu_c * inv_h2)
                add(row, _pid(i, j, k + 1, nx, ny, nz, comp), nu_c * inv_h2)

    def cross_xy(i: int, j: int, k: int, row: int, nu_c: float, sign: float, tgt: int) -> None:
        """sign * nu * d_xy A_tgt (needs i,j interior in x,y)."""
        if i <= 0 or i >= nx - 1 or j <= 0 or j >= ny - 1:
            return
        c = sign * nu_c * inv_4h2
        add(row, _pid(i + 1, j + 1, k, nx, ny, nz, tgt), -c)
        add(row, _pid(i - 1, j + 1, k, nx, ny, nz, tgt), c)
        add(row, _pid(i + 1, j - 1, k, nx, ny, nz, tgt), c)
        add(row, _pid(i - 1, j - 1, k, nx, ny, nz, tgt), -c)

    def cross_xz(i: int, j: int, k: int, row: int, nu_c: float, sign: float, tgt: int) -> None:
        if i <= 0 or i >= nx - 1 or k <= 0 or k >= nz - 1:
            return
        c = sign * nu_c * inv_4h2
        add(row, _pid(i + 1, j, k + 1, nx, ny, nz, tgt), -c)
        add(row, _pid(i - 1, j, k + 1, nx, ny, nz, tgt), c)
        add(row, _pid(i + 1, j, k - 1, nx, ny, nz, tgt), c)
        add(row, _pid(i - 1, j, k - 1, nx, ny, nz, tgt), -c)

    def cross_yz(i: int, j: int, k: int, row: int, nu_c: float, sign: float, tgt: int) -> None:
        if j <= 0 or j >= ny - 1 or k <= 0 or k >= nz - 1:
            return
        c = sign * nu_c * inv_4h2
        add(row, _pid(i, j + 1, k + 1, nx, ny, nz, tgt), -c)
        add(row, _pid(i, j - 1, k + 1, nx, ny, nz, tgt), c)
        add(row, _pid(i, j + 1, k - 1, nx, ny, nz, tgt), c)
        add(row, _pid(i, j - 1, k - 1, nx, ny, nz, tgt), -c)

    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                nu_c = float(nu[i, j, k])
                rx = _pid(i, j, k, nx, ny, nz, 0)
                ry = _pid(i, j, k, nx, ny, nz, 1)
                rz = _pid(i, j, k, nx, ny, nz, 2)

                # (curl curl A)_x = d_yy Ax + d_zz Ax - d_xy Ay + d_xz Az
                second_deriv(i, j, k, 1, 0, rx, nu_c)
                second_deriv(i, j, k, 2, 0, rx, nu_c)
                cross_xy(i, j, k, rx, nu_c, -1.0, 1)
                cross_xz(i, j, k, rx, nu_c, +1.0, 2)

                # (curl curl A)_y = d_xx Ay + d_zz Ay - d_xy Ax - d_yz Az
                second_deriv(i, j, k, 0, 1, ry, nu_c)
                second_deriv(i, j, k, 2, 1, ry, nu_c)
                cross_xy(i, j, k, ry, nu_c, -1.0, 0)
                cross_yz(i, j, k, ry, nu_c, -1.0, 2)

                # (curl curl A)_z = d_xx Az + d_yy Az - d_xz Ax - d_yz Ay
                second_deriv(i, j, k, 0, 2, rz, nu_c)
                second_deriv(i, j, k, 1, 2, rz, nu_c)
                cross_xz(i, j, k, rz, nu_c, -1.0, 0)
                cross_yz(i, j, k, rz, nu_c, -1.0, 1)

    return sparse.coo_matrix((data, (rows, cols)), shape=(n3, n3)).tocsr()


def assemble_div_nu_grad(nu: np.ndarray, h: float) -> sparse.csr_matrix:
    """Sparse 7-point stencil for ∇·(ν ∇·) with Neumann exterior faces (vectorized)."""
    nx, ny, nz = nu.shape
    n = nx * ny * nz
    inv_h2 = 1.0 / (h * h)

    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    data: list[np.ndarray] = []
    for axis in range(3):
        p, q, nf = _axis_links(nu, axis, inv_h2)
        rows.extend([p, q])
        cols.extend([q, p])
        data.extend([nf, nf])

    off = sparse.coo_matrix(
        (np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, n),
    ).tocsr()
    diag = -np.asarray(off.sum(axis=1)).ravel()
    return off + sparse.diags(diag, format="csr")


def _rhs_from_j(J_comp: np.ndarray) -> np.ndarray:
    """Volume RHS: -mu0 * Jα (J in A/mm^2 -> A/m^2)."""
    return -(MU0 * (J_comp * 1e6).reshape(-1))


def _pin_dof(nx: int, ny: int, nz: int, origin_mm, h: float, at_origin: bool) -> int:
    """Flat index pinned to A=0 (removes Neumann null space). Prefer origin for symmetry."""
    if not at_origin:
        return 0
    ox, oy, oz = (float(origin_mm[0]), float(origin_mm[1]), float(origin_mm[2]))
    ii = np.arange(nx, dtype=np.float64)
    jj = np.arange(ny, dtype=np.float64)
    kk = np.arange(nz, dtype=np.float64)
    x = ox + ii[:, None, None] * h
    y = oy + jj[None, :, None] * h
    z = oz + kk[None, None, :] * h
    d2 = x * x + y * y + z * z
    fi, fj, fk = np.unravel_index(int(np.argmin(d2)), (nx, ny, nz))
    return int(fi + nx * (fj + ny * fk))


def _pin_operator(A: sparse.csr_matrix, pin: int) -> sparse.csr_matrix:
    """Make the singular Neumann operator non-singular by fixing one DOF (Dirichlet ref)."""
    A = A.tolil()
    A.rows[pin] = [pin]
    A.data[pin] = [1.0]
    return A.tocsr()


def _prep_rhs(J_comp: np.ndarray, pin: int) -> np.ndarray:
    """Build RHS, enforce Neumann compatibility (zero mean), and apply the pinned value."""
    rhs = _rhs_from_j(J_comp)
    rhs = rhs - rhs.mean()
    rhs[pin] = 0.0
    return rhs


def _b_left_right_ratio(B_mag: np.ndarray, origin_mm, h: float, nx: int) -> float:
    """Sum |B| for x<0 vs x>0 (diagnostic; 1.0 = symmetric)."""
    ox = float(origin_mm[0])
    ix0 = int(round(-ox / h))
    ix0 = max(1, min(nx - 1, ix0))
    left = float(B_mag[:ix0].sum())
    right = float(B_mag[ix0:].sum())
    return left / max(right, 1e-30)


def _apply_uniform_mu(arrays: dict, mu_r: float) -> np.ndarray:
    """Return nu array with uniform reluctivity (decoupled solver valid only this way)."""
    nu = np.full_like(arrays["mu_r"], 1.0 / (MU0 * float(mu_r)))
    return nu


def _curl_A(Ax: np.ndarray, Ay: np.ndarray, Az: np.ndarray, h: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dAz = np.gradient(Az, h, axis=(0, 1, 2))
    dAy = np.gradient(Ay, h, axis=(0, 1, 2))
    dAx = np.gradient(Ax, h, axis=(0, 1, 2))
    Bx = dAz[1] - dAy[2]
    By = dAx[2] - dAz[0]
    Bz = dAy[0] - dAx[1]
    return Bx, By, Bz


def _prep_rhs_coupled(Jx: np.ndarray, Jy: np.ndarray, Jz: np.ndarray, pin: int) -> np.ndarray:
    rhs = np.concatenate([_rhs_from_j(Jx), _rhs_from_j(Jy), _rhs_from_j(Jz)])
    rhs = rhs - rhs.mean()
    rhs[pin] = 0.0
    return rhs


def solve_coupled(
    nu: np.ndarray,
    Jx: np.ndarray,
    Jy: np.ndarray,
    Jz: np.ndarray,
    h: float,
    *,
    pin: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Solve curl(nu curl A) = mu0 J as one 3N coupled system."""
    nx, ny, nz = nu.shape
    n = nx * ny * nz
    pin3 = int(pin)  # pin Ax component at origin cell
    method = (FEA_SOLVE_METHOD or "cg").lower()

    _log("[fea_solve] building coupled curl(nu curl A) stencil...")
    t0 = time.perf_counter()
    A_raw = assemble_coupled_curl_nu_curl(nu, h)
    A_op = _pin_operator(A_raw, pin3)
    t_asm = time.perf_counter() - t0
    _log(f"[fea_solve] assembled coupled {A_op.shape[0]:,} DOFs, {A_op.nnz:,} nnz in {t_asm:.1f}s")

    rhs = _prep_rhs_coupled(Jx, Jy, Jz, pin3)
    meta: dict = {
        "formulation": "coupled",
        "method": method,
        "assemble_s": t_asm,
        "nnz_stencil": int(A_op.nnz),
        "pin_dof": pin3,
    }

    if method == "direct":
        _log("[fea_solve] coupled direct LU...")
        t1 = time.perf_counter()
        sol = factorized(A_op.tocsc())(rhs)
        meta["solve_s"] = time.perf_counter() - t1
        meta["cg_iters"] = 0
    else:
        sol, cmeta = _solve_cg(
            A_op,
            rhs,
            "coupled",
            rtol=FEA_SOLVE_CG_RTOL_COUPLED,
            maxiter=FEA_SOLVE_CG_MAXITER_COUPLED,
        )
        meta.update(cmeta)

    u = sol.reshape(3, nx, ny, nz)
    return u[0], u[1], u[2], meta


def _solve_cg(
    A: sparse.csr_matrix,
    rhs: np.ndarray,
    axis: str,
    *,
    rtol: float | None = None,
    maxiter: int | None = None,
) -> tuple[np.ndarray, dict]:
    log_every = int(FEA_SOLVE_CG_LOG_EVERY)
    rtol = FEA_SOLVE_CG_RTOL if rtol is None else rtol
    maxiter = int(FEA_SOLVE_CG_MAXITER if maxiter is None else maxiter)
    diag = A.diagonal()
    inv_diag = np.where(np.abs(diag) > 0, 1.0 / diag, 1.0)
    precond = LinearOperator(A.shape, matvec=lambda x: inv_diag * x)

    state = {"iter": 0, "t0": time.perf_counter()}

    def callback(_xk) -> None:
        state["iter"] += 1
        if log_every > 0 and (state["iter"] == 1 or state["iter"] % log_every == 0):
            elapsed = time.perf_counter() - state["t0"]
            _log(f"[fea_solve]   CG {axis}: iter {state['iter']:,}  ({elapsed:.1f}s)")

    _log(f"[fea_solve]   CG {axis}: starting (rtol={rtol}, maxiter={maxiter:,})")
    t0 = time.perf_counter()
    sol, info = cg(
        A,
        rhs,
        rtol=rtol,
        atol=0.0,
        maxiter=maxiter,
        M=precond,
        callback=callback,
    )
    elapsed = time.perf_counter() - t0
    if info != 0:
        _log(f"[fea_solve]   CG {axis}: info={info} (0=converged) after {elapsed:.1f}s")
    else:
        _log(f"[fea_solve]   CG {axis}: converged in {state['iter']:,} iters, {elapsed:.1f}s")
    return sol, {"axis": axis, "solve_s": elapsed, "cg_iters": state["iter"], "cg_info": int(info)}


def solve_components(
    nu: np.ndarray,
    Jx: np.ndarray,
    Jy: np.ndarray,
    Jz: np.ndarray,
    h: float,
    *,
    pin: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Solve for Ax, Ay, Az and return solver metadata."""
    nx, ny, nz = nu.shape
    method = (FEA_SOLVE_METHOD or "cg").lower()

    _log("[fea_solve] building sparse stencil (vectorized)...")
    t0 = time.perf_counter()
    A_raw = assemble_div_nu_grad(nu, h)
    A_op = _pin_operator(A_raw, pin)
    t_asm = time.perf_counter() - t0
    _log(f"[fea_solve] assembled {A_op.nnz:,} nnz in {t_asm:.1f}s (pinned DOF {pin})")

    meta: dict = {
        "formulation": "decoupled",
        "method": method,
        "assemble_s": t_asm,
        "nnz_stencil": int(A_op.nnz),
        "pin_dof": int(pin),
        "components": [],
    }

    outs = []
    if method == "direct":
        _log("[fea_solve] direct LU factorization (slow/memory-heavy on large grids)...")
        t1 = time.perf_counter()
        solve_fn = factorized(A_op.tocsc())
        meta["factorize_s"] = time.perf_counter() - t1
        _log(f"[fea_solve] factorized in {meta['factorize_s']:.1f}s")
        for name, Jc in (("x", Jx), ("y", Jy), ("z", Jz)):
            t1 = time.perf_counter()
            sol = solve_fn(_prep_rhs(Jc, pin))
            meta["components"].append({"axis": name, "solve_s": time.perf_counter() - t1})
            outs.append(sol.reshape(nx, ny, nz))
    else:
        for name, Jc in (("x", Jx), ("y", Jy), ("z", Jz)):
            sol, comp_meta = _solve_cg(A_op, _prep_rhs(Jc, pin), name)
            meta["components"].append(comp_meta)
            outs.append(sol.reshape(nx, ny, nz))

    return outs[0], outs[1], outs[2], meta


def solve_b_arrays(fea_grid: dict) -> dict:
    """Solve and return B as numpy arrays (no list serialization).

    Returns dict with Bx, By, Bz, B_mag (each nx×ny×nz float64), plus
    origin_mm, spacing_mm, size, arrays (rasterized μ/J), and meta.
    """
    arrays = grid_arrays(fea_grid)
    nx, ny, nz = arrays["nx"], arrays["ny"], arrays["nz"]
    h = arrays["h"]
    origin = fea_grid["origin_mm"]
    n = nx * ny * nz
    pin = _pin_dof(nx, ny, nz, origin, h, FEA_SOLVE_PIN_AT_ORIGIN)

    nu = arrays["nu"]
    uniform_mu = FEA_SOLVE_UNIFORM_MU_R
    if uniform_mu is not None:
        nu = _apply_uniform_mu(arrays, float(uniform_mu))
        _log(f"[fea_solve] uniform mu_r={float(uniform_mu):g} (spatial steel mu ignored)")
    formulation = (FEA_SOLVE_FORMULATION or "coupled").lower()
    if formulation == "decoupled" and float(arrays["steel_mu_r"]) > 1.5 and uniform_mu is None:
        _log(
            "[fea_solve] warning: decoupled solve with spatial steel mu_r is not valid; "
            "set FEA_SOLVE_FORMULATION='coupled' or mu=1"
        )

    _log(
        f"[fea_solve] grid {nx}x{ny}x{nz} ({n:,} cells), "
        f"formulation={formulation}, method={FEA_SOLVE_METHOD}"
    )

    if formulation == "coupled":
        Ax, Ay, Az, meta = solve_coupled(
            nu, arrays["Jx"], arrays["Jy"], arrays["Jz"], h, pin=pin,
        )
    else:
        Ax, Ay, Az, meta = solve_components(
            nu, arrays["Jx"], arrays["Jy"], arrays["Jz"], h, pin=pin,
        )

    _log("[fea_solve] computing B = curl(A)...")
    Bx, By, Bz = _curl_A(Ax, Ay, Az, h)
    B_mag = np.sqrt(Bx * Bx + By * By + Bz * Bz)
    meta["max_B_T"] = float(B_mag.max())
    meta["mean_B_T"] = float(B_mag.mean())
    meta["uniform_mu_r"] = None if uniform_mu is None else float(uniform_mu)
    meta["steel_mu_r_grid"] = float(arrays["steel_mu_r"])
    lr = _b_left_right_ratio(B_mag, origin, h, nx)
    meta["b_lr_ratio"] = lr
    _log(f"[fea_solve] done  max|B|={meta['max_B_T']:.6e} T  L/R|B|={lr:.3f}")
    if lr > 1.15 or lr < 1.0 / 1.15:
        _log("[fea_solve] warning: |B| not left/right symmetric (see b_lr_ratio in meta)")

    return {
        "origin_mm": list(fea_grid["origin_mm"]),
        "spacing_mm": h,
        "size": [nx, ny, nz],
        "Bx": Bx,
        "By": By,
        "Bz": Bz,
        "B_mag": B_mag,
        "arrays": arrays,
        "meta": meta,
    }


def solve_magnetostatic(fea_grid: dict, *, store_full_b: bool | None = None) -> dict:
    """Solve for B on the full voxel lattice; input is ``build_fea_grid()`` output."""
    store_b = FEA_SOLVE_STORE_FULL_B if store_full_b is None else store_full_b
    sol = solve_b_arrays(fea_grid)
    Bx, By, Bz, B_mag = sol["Bx"], sol["By"], sol["Bz"], sol["B_mag"]

    result: dict = {
        "origin_mm": sol["origin_mm"],
        "spacing_mm": sol["spacing_mm"],
        "size": sol["size"],
        "meta": sol["meta"],
    }
    if store_b:
        _log("[fea_solve] exporting full B arrays to lists...")
        result["B_mm"] = {
            "Bx": Bx.reshape(-1).tolist(),
            "By": By.reshape(-1).tolist(),
            "Bz": Bz.reshape(-1).tolist(),
            "magnitude": B_mag.reshape(-1).tolist(),
        }

    if FEA_RUN_SOLVE_TESTS:
        _run_inline_unit_tests(fea_grid, sol["arrays"], Bx, By, Bz, B_mag, result)

    return result


def _run_inline_unit_tests(
    fea_grid: dict,
    arrays: dict,
    Bx: np.ndarray,
    By: np.ndarray,
    Bz: np.ndarray,
    B_mag: np.ndarray,
    result: dict,
) -> None:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    nx, ny, nz = arrays["nx"], arrays["ny"], arrays["nz"]
    n = nx * ny * nz

    check(n > 0, "grid has zero cells")
    check(Bx.size == n, "Bx length matches grid")
    check(np.all(np.isfinite(B_mag)), "B magnitude is finite")
    check(float(B_mag.max()) == result["meta"]["max_B_T"], "max_B consistent")

    steel_count = int(np.sum(arrays["mu_r"] >= arrays["steel_mu_r"] * 0.9))
    coil_mask = (np.abs(arrays["Jx"]) + np.abs(arrays["Jy"]) + np.abs(arrays["Jz"])) > 0
    coil_count = int(np.sum(coil_mask))
    metal_cells = fea_grid["metal"]["cell_count"]
    check(
        steel_count + coil_count >= metal_cells * 0.9,
        f"raster steel+coil {steel_count}+{coil_count} vs metal+coil cells",
    )
    check(
        coil_count >= fea_grid["cells"]["coil_count"] * 0.95,
        f"coil raster count {coil_count} vs {fea_grid['cells']['coil_count']}",
    )

    zero_grid = _zero_current_copy(fea_grid)
    zarr = grid_arrays(zero_grid)
    zpin = _pin_dof(zarr["nx"], zarr["ny"], zarr["nz"], fea_grid["origin_mm"], zarr["h"],
                    FEA_SOLVE_PIN_AT_ORIGIN)
    zAx, zAy, zAz, _ = solve_components(
        zarr["nu"], zarr["Jx"], zarr["Jy"], zarr["Jz"], zarr["h"], pin=zpin,
    )
    zBx, zBy, zBz = _curl_A(zAx, zAy, zAz, zarr["h"])
    zmax = float(np.sqrt(zBx * zBx + zBy * zBy + zBz * zBz).max())
    check(zmax < 1e-9, f"zero J should give ~0 B, got max {zmax}")
    check(float(B_mag.max()) > 1e-14, "nonzero B expected when coils carry J")

    if failures:
        raise AssertionError("fea_solve inline tests failed:\n  - " + "\n  - ".join(failures))
    _log(f"[fea_solve] inline tests OK ({coil_count} coil cells)")


def _zero_current_copy(fea_grid: dict) -> dict:
    import copy

    g = copy.deepcopy(fea_grid)
    for j in g["cells"]["coil"]["J_mm"]:
        j[0] = j[1] = j[2] = 0.0
    return g


if __name__ == "__main__":
    from fea_model import build_voxel_scene, invalidate_cache

    invalidate_cache()
    build_voxel_scene(force=True)
