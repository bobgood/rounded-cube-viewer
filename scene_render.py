"""scene_render.py — Shared voxel_scene JSON assembly (cube outline + viewer payload)."""

from __future__ import annotations

from cube_config import OU_COLOR, MM_TO_SCENE
from fea_config import FEA_GRID_DEBUG_COLOR


def to_scene_mm(raw: list, sc=None) -> list:
    scale = MM_TO_SCENE if sc is None else sc
    return [[round(x * scale, 3), round(y * scale, 3), round(z * scale, 3)]
            for (x, y, z) in raw]


def scene_point_mm(x_mm: float, y_mm: float, z_mm: float, sc: float) -> list:
    return [round(x_mm * sc, 3), round(y_mm * sc, 3), round(z_mm * sc, 3)]


def frame_config_dict(
    *,
    edge_mm: float,
    height_mm: float,
    inset_mm: float,
    corner_pos_mm: dict,
    coil_weights: dict,
    sc=None,
    hole_diameter_mm=None,
    ho_color=None,
) -> dict:
    scale = MM_TO_SCENE if sc is None else sc
    cfg = {
        "edge_mm": edge_mm,
        "height_mm": height_mm,
        "ou_rounding_mm": inset_mm,
        "ou_color": list(OU_COLOR),
        "mm_to_scene": scale,
        "coil_weights": coil_weights,
        "cube_corners": {
            str(c): scene_point_mm(x, y, z, scale)
            for c, (x, y, z) in corner_pos_mm.items()
        },
    }
    if hole_diameter_mm is not None:
        cfg["hole_diameter_mm"] = hole_diameter_mm
    if ho_color is not None:
        cfg["ho_color"] = list(ho_color)
    return cfg


def fea_grid_payload(fea_grid: dict, sc: float) -> dict | None:
    if not fea_grid:
        return None
    mg = fea_grid["metal"]
    coil_cells = fea_grid["cells"]["coil"]
    if mg["cell_count"] <= 0 and fea_grid["cells"]["coil_count"] <= 0:
        return None
    payload = {
        "origin_mm": fea_grid["origin_mm"],
        "spacing_mm": fea_grid["spacing_mm"],
        "size": fea_grid["size"],
        "color": list(FEA_GRID_DEBUG_COLOR),
        "metal": {
            "material_id": mg["material_id"],
            "mu_r": mg["mu_r"],
            "cell_count": mg["cell_count"],
            "positions": to_scene_mm(mg["positions_mm"], sc),
            "sources": mg["sources"],
        },
        "cells": {
            "steel_count": fea_grid["cells"]["steel_count"],
            "coil_count": fea_grid["cells"]["coil_count"],
            "steel": fea_grid["cells"]["steel"],
            "coil": {
                "material_id": coil_cells["material_id"],
                "mu_r": coil_cells["mu_r"],
                "positions": to_scene_mm(coil_cells["positions_mm"], sc),
                "J": coil_cells["J_mm"],
                "weight": coil_cells["weight"],
            },
        },
    }
    if fea_grid.get("B_field"):
        payload["B_field"] = fea_grid["B_field"]
    return payload
