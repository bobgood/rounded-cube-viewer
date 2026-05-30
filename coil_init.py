"""coil_init.py — Coil weights per experiment scene (keys: c1–c8, e12, f1234, …).

Each value in [-1, 1]. Sign sets J direction; magnitude scales |J| and arrow intensity.
Edit the table for the active scene (see fea_config.FEA_SCENE_ID).
"""

from __future__ import annotations

SCENE_COILS: dict[str, dict[str, float]] = {
    "frame": {
        "c1":  1.0,
        "c2":  1.0,
        "c3":  1.0,
        "c4":  1.0,
        "c5": -1.0,
        "c6": -1.0,
        "c7": -1.0,
        "c8": -1.0,
        "f1234": 0.0,
        "f5678": 0.0,
        "f1265": 0.0,
        "f3487": 0.0,
        "f1485": 0.0,
        "f3276": 0.0,
    },
    "dipole": {
        "e12": 1.0,
    },
    "12dipoles": {
        # All 12 cube edges. Positive → B toward first-named corner.
        # Top ring
        "e12": 0.0,  "e23": 0.0,  "e34": 0.0,  "e41": 0.0,
        # Bottom ring
        "e56": 0.0,  "e67": 0.0,  "e78": 0.0,  "e85": 0.0,
        # Vertical struts
        "e15": 1.0,  "e26": 1.0,  "e37": 1.0,  "e48": 1.0,
    },
}


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


def _active_table() -> dict[str, float]:
    from fea_config import FEA_SCENE_ID
    sid = (FEA_SCENE_ID or "frame").strip().lower()
    return SCENE_COILS.get(sid, SCENE_COILS["frame"])


def coil_weight(key: str, default: float = 1.0) -> float:
    table = _active_table()
    if key in table:
        return _clamp(table[key])
    k = key.lower()
    if k in table:
        return _clamp(table[k])
    return _clamp(default)


def edge_coil_weight(edge_label: str) -> float:
    ek = edge_label.strip().lower()
    if not ek.startswith("e"):
        ek = f"e{ek}"
    return coil_weight(ek)


def cv_coil_key(end_corner: int, edge_label: str) -> str:
    if edge_label:
        ek = edge_label.lower()
        if not ek.startswith("e"):
            ek = f"e{ek}"
        if ek in _active_table():
            return ek
    return f"c{int(end_corner)}"


def cv_coil_weight(end_corner: int, edge_label: str) -> float:
    return coil_weight(cv_coil_key(end_corner, edge_label))


def cu_coil_weight(face_clockwise: str) -> float:
    fs = face_clockwise.strip().lower()
    key = fs if fs.startswith("f") else f"f{fs}"
    return coil_weight(key)


def export_coil_table() -> dict[str, float]:
    return {k: round(_clamp(v), 4) for k, v in _active_table().items()}
