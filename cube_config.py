"""cube_config.py — Shared cube envelope only (all experiments use this outline).

Scene-specific geometry lives in ng_config.py and scene modules.
"""

# ── Cube envelope (always a cube) ─────────────────────────────────────────────
FRAME_SIDES   = 4
FRAME_EDGE_MM = 32.0   # outer face-to-face width/depth and height (mm)
FRAME_INSET_MM = 5.0   # corner fillet / skeleton inset from outer face (mm)

# ── Viewer scale ──────────────────────────────────────────────────────────────
MM_TO_SCENE = 0.1   # 1 mm -> Three.js units (32 mm frame = 3.2 units)

# ── Outline debug (Ou / Ho); rendering only ───────────────────────────────────
OU_COLOR         = (0.35, 0.65, 1.0)
HOLE_DIAMETER_MM = 16.0
HO_COLOR         = (1.0, 0.50, 0.25)
