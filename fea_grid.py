"""fea_grid.py — World-space FEA voxel grid.

Steel (Cy+Ca+Pl+Hs) and copper pipe volumes share one lattice (k * h mm).
Gm debug shows steel only; fea_grid.cells carries material + J for the solver.
"""

from __future__ import annotations

import math
from typing import Iterable


def _lattice_index(x_mm: float, y_mm: float, z_mm: float, h: float) -> tuple[int, int, int]:
    return (
        int(round(x_mm / h)),
        int(round(y_mm / h)),
        int(round(z_mm / h)),
    )


def _lattice_centre_mm(ix: int, iy: int, iz: int, h: float) -> tuple[float, float, float]:
    return (ix * h, iy * h, iz * h)


def _grid_bounds(
    keys: Iterable[tuple[int, int, int]],
    outer_edge_mm: float,
    outer_height_mm: float,
    h: float,
    pad_mm: float,
    center_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[int, int, int, int, int, int, int, int, int]:
    cx, cy, cz = float(center_mm[0]), float(center_mm[1]), float(center_mm[2])
    pad_cells = max(1, int(math.ceil(float(pad_mm) / h)))
    hx = outer_edge_mm / 2.0 + pad_mm
    hy = outer_height_mm / 2.0 + pad_mm
    hz = outer_edge_mm / 2.0 + pad_mm
    env_ix0 = int(math.floor((cx - hx) / h)) - pad_cells
    env_ix1 = int(math.ceil((cx + hx) / h)) + pad_cells
    env_iy0 = int(math.floor((cy - hy) / h)) - pad_cells
    env_iy1 = int(math.ceil((cy + hy) / h)) + pad_cells
    env_iz0 = int(math.floor((cz - hz) / h)) - pad_cells
    env_iz1 = int(math.ceil((cz + hz) / h)) + pad_cells

    key_list = list(keys)
    if not key_list:
        return env_ix0, env_ix1, env_iy0, env_iy1, env_iz0, env_iz1, pad_cells, 0, 0

    occ_ix0 = min(ix for ix, _, _ in key_list)
    occ_ix1 = max(ix for ix, _, _ in key_list)
    occ_iy0 = min(iy for _, iy, _ in key_list)
    occ_iy1 = max(iy for _, iy, _ in key_list)
    occ_iz0 = min(iz for _, _, iz in key_list)
    occ_iz1 = max(iz for _, _, iz in key_list)

    ix0 = min(env_ix0, occ_ix0 - pad_cells)
    ix1 = max(env_ix1, occ_ix1 + pad_cells)
    iy0 = min(env_iy0, occ_iy0 - pad_cells)
    iy1 = max(env_iy1, occ_iy1 + pad_cells)
    iz0 = min(env_iz0, occ_iz0 - pad_cells)
    iz1 = max(env_iz1, occ_iz1 + pad_cells)
    nx = ix1 - ix0 + 1
    ny = iy1 - iy0 + 1
    nz = iz1 - iz0 + 1
    return ix0, iy0, iz0, nx, ny, nz, pad_cells, ix1, iy1


def build_fea_grid(
    cyl_raw: list,
    cap_raw: list,
    plate_raw: list,
    hs_raw: list,
    coil_voxels: list,
    outer_edge_mm: float,
    outer_height_mm: float,
    voxel_size_mm: float,
    pad_mm: float = 0.5,
    steel_material_id: int = 1,
    steel_mu_r: float = 5000.0,
    coil_material_id: int = 2,
    coil_mu_r: float = 1.0,
    copper_voxels: list | None = None,
    center_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict:
    """Build lattice grid: steel union + coil cells (Cu pipe + Cv sleeves) with J.

    coil_voxels: (x, y, z, jx, jy, jz, coil_weight) per cell; weight is the
    coil_init value (× fea_strength_scale when scene is rebuilt for FEA).
    Coil overwrites steel on the same lattice index.
    """
    if copper_voxels is not None and not coil_voxels:
        coil_voxels = copper_voxels
    h = float(voxel_size_mm)
    sources = {
        "cyl": len(cyl_raw),
        "cap": len(cap_raw),
        "pl": len(plate_raw),
        "hs": len(hs_raw),
    }
    sources["raw_total"] = sum(sources.values())

    steel: set[tuple[int, int, int]] = set()

    def _add_steel(raw: list) -> None:
        for (x, y, z) in raw:
            steel.add(_lattice_index(x, y, z, h))

    _add_steel(cyl_raw)
    _add_steel(cap_raw)
    _add_steel(plate_raw)
    _add_steel(hs_raw)

    # Accumulate J vectors from all fine-grid voxels that map to the same coarse
    # lattice cell, then average.  A plain overwrite (last-wins) breaks azimuthal
    # symmetry when many fine voxels at different angles collapse into one coarse cell
    # (most visible at the 2 mm B-line grid resolution).
    coil_j_acc: dict[tuple[int, int, int], list] = {}  # key -> [jx, jy, jz, cw, count]
    for entry in coil_voxels:
        if len(entry) >= 7:
            x, y, z, jx, jy, jz, cw = entry[:7]
        else:
            x, y, z, jx, jy, jz = entry[:6]
            cw = 1.0
        key = _lattice_index(x, y, z, h)
        if key in coil_j_acc:
            acc = coil_j_acc[key]
            acc[0] += float(jx)
            acc[1] += float(jy)
            acc[2] += float(jz)
            acc[3] += float(cw)
            acc[4] += 1
        else:
            coil_j_acc[key] = [float(jx), float(jy), float(jz), float(cw), 1]

    coil_j: dict[tuple[int, int, int], tuple[float, float, float, float]] = {
        key: (acc[0] / acc[4], acc[1] / acc[4], acc[2] / acc[4], acc[3] / acc[4])
        for key, acc in coil_j_acc.items()
    }

    all_keys = steel | set(coil_j.keys())
    if not all_keys:
        return _empty_grid(h, sources, steel_material_id, steel_mu_r,
                           coil_material_id, coil_mu_r)

    ix0, iy0, iz0, nx, ny, nz, _, _, _ = _grid_bounds(
        all_keys, outer_edge_mm, outer_height_mm, h, pad_mm, center_mm=center_mm,
    )

    skipped = 0
    steel_cells: list[tuple[int, int, int]] = []
    coil_cells: list[tuple[int, int, int]] = []

    for key in sorted(all_keys):
        ix, iy, iz = key
        li, lj, lk = ix - ix0, iy - iy0, iz - iz0
        if li < 0 or lj < 0 or lk < 0 or li >= nx or lj >= ny or lk >= nz:
            skipped += 1
            continue
        if key in coil_j:
            coil_cells.append(key)
        elif key in steel:
            steel_cells.append(key)

    steel_positions = [_lattice_centre_mm(*k, h) for k in steel_cells]
    coil_positions = [_lattice_centre_mm(*k, h) for k in coil_cells]
    coil_J = [[round(coil_j[k][0], 6), round(coil_j[k][1], 6), round(coil_j[k][2], 6)]
              for k in coil_cells]
    coil_weight = [round(coil_j[k][3], 6) for k in coil_cells]

    return {
        "origin_mm": [round(ix0 * h, 4), round(iy0 * h, 4), round(iz0 * h, 4)],
        "spacing_mm": round(h, 4),
        "size": [nx, ny, nz],
        "metal": {
            "material_id": int(steel_material_id),
            "mu_r": float(steel_mu_r),
            "cell_count": len(steel_cells),
            "positions_mm": steel_positions,
            "flat_index": [
                (ix - ix0) + nx * ((iy - iy0) + ny * (iz - iz0))
                for (ix, iy, iz) in steel_cells
            ],
            "sources": {**sources, "union": len(steel_cells), "skipped_oob": skipped},
        },
        "cells": {
            "steel_count": len(steel_cells),
            "coil_count": len(coil_cells),
            "steel": {
                "material_id": int(steel_material_id),
                "mu_r": float(steel_mu_r),
            },
            "coil": {
                "material_id": int(coil_material_id),
                "mu_r": float(coil_mu_r),
                "positions_mm": coil_positions,
                "J_mm": coil_J,
                "weight": coil_weight,
                "flat_index": [
                    (ix - ix0) + nx * ((iy - iy0) + ny * (iz - iz0))
                    for (ix, iy, iz) in coil_cells
                ],
            },
            "skipped_oob": skipped,
        },
    }


def _empty_grid(h, sources, steel_id, steel_mu, coil_id, coil_mu):
    return {
        "origin_mm": [0.0, 0.0, 0.0],
        "spacing_mm": round(h, 4),
        "size": [0, 0, 0],
        "metal": {
            "material_id": int(steel_id),
            "mu_r": float(steel_mu),
            "cell_count": 0,
            "positions_mm": [],
            "flat_index": [],
            "sources": {**sources, "union": 0, "skipped_oob": 0},
        },
        "cells": {
            "steel_count": 0,
            "coil_count": 0,
            "steel": {"material_id": int(steel_id), "mu_r": float(steel_mu)},
            "coil": {
                "material_id": int(coil_id),
                "mu_r": float(coil_mu),
                "positions_mm": [],
                "J_mm": [],
                "weight": [],
                "flat_index": [],
            },
            "skipped_oob": 0,
        },
    }


def build_metal_grid(
    cyl_raw: list,
    cap_raw: list,
    plate_raw: list,
    hs_raw: list,
    outer_edge_mm: float,
    outer_height_mm: float,
    voxel_size_mm: float,
    pad_mm: float = 0.5,
    material_id: int = 1,
    mu_r: float = 5000.0,
) -> dict:
    """Steel-only subset (legacy / tests). Prefer build_fea_grid."""
    grid = build_fea_grid(
        cyl_raw, cap_raw, plate_raw, hs_raw,
        coil_voxels=[],
        outer_edge_mm=outer_edge_mm,
        outer_height_mm=outer_height_mm,
        voxel_size_mm=voxel_size_mm,
        pad_mm=pad_mm,
        steel_material_id=material_id,
        steel_mu_r=mu_r,
    )
    return {
        "origin_mm": grid["origin_mm"],
        "spacing_mm": grid["spacing_mm"],
        "size": grid["size"],
        "metal": grid["metal"],
    }
