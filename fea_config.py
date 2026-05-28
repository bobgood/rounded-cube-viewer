"""fea_config.py — FEA model constants.

Edit these values to change geometry, appearance, and frame shape without
touching any other file.
"""

# ── Voxel grid ──────────────────────────────────────────────────────────────
VOXEL_SIZE_MM = 0.5          # spacing between voxel centres (mm)

# ── Metal colour ─────────────────────────────────────────────────────────────
# All structural metal (cylinders, caps, collars) shares this colour.
METAL_COLOR = (1.0, 1.0, 1.0)   # pure white; change to e.g. (0.8, 0.82, 0.85) for steel

CYLINDER_COLOR = METAL_COLOR
CAP_COLOR      = METAL_COLOR

# ── Individual cylinder geometry ────────────────────────────────────────────
CYLINDER_LENGTH_MM   = 20.0  # usable length of each rod (mm); centred on edge
CYLINDER_DIAMETER_MM =  7.0  # outer diameter (mm)
CYLINDER_RADIUS_MM   = CYLINDER_DIAMETER_MM / 2.0

# ── Cap + collar geometry ────────────────────────────────────────────────────
# Cap sphere and collar share the same radius = cylinder radius + CAP_EXTRA_MM.
# All frame elements are inset from the bounding box by half that radius so the
# sphere protrudes by exactly FRAME_INSET_MM past each outer face.
CAP_EXTRA_MM       = 2.0     # extra radius beyond the cylinder (mm)
_CAP_R             = CYLINDER_RADIUS_MM + CAP_EXTRA_MM   # = 5.5 mm
CAP_DIAMETER_MM    = _CAP_R * 2          # = 11.0 mm  (sphere diameter)
COLLAR_DIAMETER_MM = _CAP_R * 2          # = 11.0 mm  (collar diameter, same as sphere)
FRAME_INSET_MM     = _CAP_R / 2          # = 2.75 mm  (elements moved inward from face)

# ── Frame (n-gon prism of cylinders) ────────────────────────────────────────
# 3n cylinders  +  2n corner caps (each with 3 collar stubs).
#
#   FRAME_SIDES = 4  ->  cube frame   (12 cylinders, 8 caps)
#   FRAME_SIDES = 6  ->  hex prism    (18 cylinders, 12 caps)
#   FRAME_SIDES = 8  ->  oct prism    (24 cylinders, 16 caps)

FRAME_SIDES      = 4      # number of polygon sides
FRAME_EDGE_MM    = 32.0   # polygon edge length for top/bottom ring (mm)
FRAME_HEIGHT_MM  = 32.0   # prism height / vertical strut length (mm)

# Minimum gap at each end of a cylinder along its axis (mm).
# Also determines collar length: collar_len = (edge_len - cyl_len) / 2 + ext.
FRAME_GAP_MM     = 2.0

# ── Ou: rounded bounding-box outline ────────────────────────────────────────
# Displayed as a translucent solid + edge lines — purely visual, no voxels.
OU_ROUNDING_MM   =  3.0               # corner rounding radius (mm)
OU_COLOR         = (0.35, 0.65, 1.0)  # light blue

# ── Ho: 3 orthogonal crossing cylinders (hole/subtractor) ───────────────────
# Each cylinder runs the full span of the frame on its axis.
HOLE_DIAMETER_MM = 16.0               # cylinder diameter (mm)
HO_COLOR         = (1.0, 0.50, 0.25)  # warm orange

# ── Face plates ─────────────────────────────────────────────────────────────
# Each face of the frame has 4 quadrant panels (A/B/C/D).
# SPIN_WHEEL_OFFSET_MM shifts the dividing lines so each plate is
# 1 mm wider in one axis and 1 mm shorter in the other, creating a
# pinwheel/spin-wheel gap pattern.
PLATE_THICKNESS_MM   = 1.0   # plate depth (mm), flush with outer face
PLATE_GAP_MM         = 1.0   # gap between adjacent plates on the same face (mm)
SPIN_WHEEL_OFFSET_MM = 1.0   # pinwheel offset (mm); 0 = perfectly square plates
PLATE_EDGE_INSET_MM  = 0.0   # additional inset from face edge (0 = full face)
PLATE_COLOR          = METAL_COLOR

# ── Scene scale ─────────────────────────────────────────────────────────────
MM_TO_SCENE = 0.1   # 1 mm -> 0.1 Three.js scene units  (32 mm frame = 3.2 units)
