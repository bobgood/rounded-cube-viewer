"""coil_init.py — Initial coil weights for FEA (separate from fea_config geometry).

Each value is in [-1, 1]. It controls arrow color and intensity only, not direction.
When FEA runs, site currents are multiplied by these weights.

Cv (24 edge coils) — default grouping by corner: all three coils at corner N use cN.
Optional per-coil override: lowercase directed edge id, e.g. e12 for coil E12.

Cu (6 face coils) — keys f + clockwise face id, e.g. f1234 for the +Z face.
"""

from __future__ import annotations

# Edit this table only; geometry stays in fea_config.py
COIL: dict[str, float] = {
    # ── Corner groups (3 Cv coils each, 24 total) ─────────────────────────────
    "c1": -0.5,
    "c2":  0.3,
    "c3":  1.0,
    "c4": -0.85,
    "c5":  1.0,
    "c6": -0.3,
    "c7":  0.5,
    "c8": 0.0,
    # Optional per-coil overrides (directed edge label, lowercase):
    # "e12": 0.3,
    # "e21": -0.2,

    # ── Face coils (Cu) ───────────────────────────────────────────────────────
    "f1234":  0.0,   # +Z
    "f5678": -1.0,   # -Z
    "f1265":  0.85,  # +X
    "f3487": -0.85,  # -X
    "f1485":  1.0,   # +Y
    "f3276": -1.0,   # -Y
}


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


def coil_weight(key: str, default: float = 1.0) -> float:
    """Look up a coil weight; keys are case-insensitive."""
    if key in COIL:
        return _clamp(COIL[key])
    k = key.lower()
    if k in COIL:
        return _clamp(COIL[k])
    return _clamp(default)


def cv_coil_key(end_corner: int, edge_label: str) -> str:
    """Lookup key used for this Cv coil (e12 override or corner group cN)."""
    if edge_label:
        ek = edge_label.lower()
        if not ek.startswith("e"):
            ek = f"e{ek}"
        if ek in COIL:
            return ek
    return f"c{int(end_corner)}"


def cv_coil_weight(end_corner: int, edge_label: str) -> float:
    """Cv coil at edge end: optional e12 override, else corner group cN."""
    return coil_weight(cv_coil_key(end_corner, edge_label))


def cu_coil_weight(face_clockwise: str) -> float:
    """Cu coil on face with corners listed clockwise (e.g. 1234)."""
    fs = face_clockwise.strip().lower()
    key = fs if fs.startswith("f") else f"f{fs}"
    return coil_weight(key)


def export_coil_table() -> dict[str, float]:
    """Copy of COIL for embedding in the voxel scene JSON."""
    return {k: round(_clamp(v), 4) for k, v in COIL.items()}
