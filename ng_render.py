"""ng_render.py — Shared scene JSON assembly (cube outline + viewer payload)."""

from __future__ import annotations

from cube_config import OU_COLOR, MM_TO_SCENE


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
