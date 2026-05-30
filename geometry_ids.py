"""geometry_ids.py — Named cube topology (corners, edges, faces).

Corner ids c1–c8, directed edges e12 / e21, faces f1234 (clockwise corner ids).
Used by coil_init keys and scene builders.
"""

from __future__ import annotations

# +Z face viewed from outside: corners 1,2,3,4 at skeleton vertices k0,k3,k2,k1.
# Bottom face: 5–8 at the same k indices.

CORNER_BY_K_TOP = (1, 4, 3, 2)

FACE_CLOCKWISE = (
    "1234",  # +Z
    "5678",  # -Z
    "1265",  # +X
    "3487",  # -X
    "1485",  # +Y
    "3276",  # -Y
)

FACE_CORNER_IDS = tuple(tuple(int(c) for c in f) for f in FACE_CLOCKWISE)


def corner_id(k: int, z_sign: int) -> int:
    c = CORNER_BY_K_TOP[k % 4]
    return c if z_sign > 0 else c + 4


def ring_edge_label(k: int, z_sign: int) -> str:
    c1 = corner_id(k, z_sign)
    c2 = corner_id((k + 1) % 4, z_sign)
    return f"e{c1}{c2}"


def strut_edge_label(k: int) -> str:
    return f"e{corner_id(k, +1)}{corner_id(k, -1)}"


def face_label(face_index: int) -> str:
    return "f" + FACE_CLOCKWISE[face_index]


def normalize_edge_key(label: str) -> str:
    s = label.strip().lower()
    if not s.startswith("e"):
        s = f"e{s}"
    return s


def normalize_face_key(label: str) -> str:
    s = label.strip().lower()
    return s if s.startswith("f") else f"f{s}"
