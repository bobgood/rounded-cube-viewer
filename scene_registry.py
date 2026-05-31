"""scene_registry.py — NGSolve experiment scenes inside the shared cube envelope."""

from __future__ import annotations

import ng_config

SCENE_IDS = ("1dipole", "12dipoles_ng", "30coils_ng", "potcore_ng")
SCENE_LABELS = {
    "1dipole":      "1 dipole",
    "12dipoles_ng": "12 dipoles",
    "30coils_ng":   "30 coils",
    "potcore_ng":   "1 pot core",
}


def list_scenes() -> list[tuple[str, str]]:
    return [(sid, SCENE_LABELS.get(sid, sid)) for sid in SCENE_IDS]


def get_scene_id() -> str:
    sid = (ng_config.NG_SCENE_ID or "1dipole").strip().lower()
    return sid if sid in SCENE_IDS else "1dipole"


def invalidate_all_caches():
    from scene_ngmesh import invalidate_cache as inv_ngmesh
    from scene_ng12dipoles import invalidate_cache as inv_ng12dipoles
    from ng_frame import invalidate_cache as inv_ng30
    from scene_potcore import invalidate_cache as inv_potcore

    inv_ngmesh()
    inv_ng12dipoles()
    inv_ng30()
    inv_potcore()


def build_scene(force: bool = False, strength_scale: float = 1.0) -> dict:
    """Build the active NGSolve scene (fea_mesh payload)."""
    sid = get_scene_id()
    if sid == "1dipole":
        from scene_ngmesh import build_ngmesh_scene
        return build_ngmesh_scene(force=force, fea_strength_scale=strength_scale)
    if sid == "12dipoles_ng":
        from scene_ng12dipoles import build_scene as build_ng12
        return build_ng12(force=force, fea_strength_scale=strength_scale)
    if sid == "potcore_ng":
        from scene_potcore import build_scene as build_potcore
        return build_potcore(force=force, fea_strength_scale=strength_scale)
    from ng_frame import build_scene as build_ng30
    return build_ng30(force=force, fea_strength_scale=strength_scale)
