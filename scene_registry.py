"""scene_registry.py — Experiment scenes inside the shared cube envelope."""

from __future__ import annotations

SCENE_IDS = ("1dipole", "12dipoles_ng", "frame", "dipole", "12dipoles")
SCENE_LABELS = {
    "1dipole":      "1 dipole",
    "12dipoles_ng": "12 dipoles",
    "frame":        "30 coils experiment",
    "dipole":       "Dipole (voxel)",
    "12dipoles":    "12 dipoles (voxel)",
}


def list_scenes() -> list[tuple[str, str]]:
    return [(sid, SCENE_LABELS.get(sid, sid)) for sid in SCENE_IDS]


def get_scene_id() -> str:
    import fea_config
    sid = (fea_config.FEA_SCENE_ID or "frame").strip().lower()
    return sid if sid in SCENE_IDS else "frame"


def invalidate_all_caches():
    from fea_model import invalidate_cache as inv_frame
    from scene_dipole import invalidate_cache as inv_dipole
    from scene_12dipoles import invalidate_cache as inv_12dipoles
    from scene_ngmesh import invalidate_cache as inv_ngmesh
    from scene_ng12dipoles import invalidate_cache as inv_ng12dipoles

    inv_frame()
    inv_dipole()
    inv_12dipoles()
    inv_ngmesh()
    inv_ng12dipoles()


def build_scene(force: bool = False, fea_strength_scale: float = 1.0) -> dict:
    """Build the active experiment scene (voxel_scene dict)."""
    sid = get_scene_id()
    if sid == "1dipole":
        from scene_ngmesh import build_ngmesh_scene
        return build_ngmesh_scene(force=force, fea_strength_scale=fea_strength_scale)
    if sid == "12dipoles_ng":
        from scene_ng12dipoles import build_scene as build_ng12
        return build_ng12(force=force, fea_strength_scale=fea_strength_scale)
    if sid == "dipole":
        from scene_dipole import build_dipole_scene
        return build_dipole_scene(force=force, fea_strength_scale=fea_strength_scale)
    if sid == "12dipoles":
        from scene_12dipoles import build_12dipoles_scene
        return build_12dipoles_scene(force=force, fea_strength_scale=fea_strength_scale)
    from fea_model import build_frame_scene
    return build_frame_scene(force=force, fea_strength_scale=fea_strength_scale)


# Back-compat alias used by server / tests
build_voxel_scene = build_scene
