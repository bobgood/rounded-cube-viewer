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

# ── Frame (n-gon prism of cylinders) ────────────────────────────────────────
# 3n cylinders  +  2n corner caps (each with 3 collar stubs).
#
#   FRAME_SIDES = 4  ->  cube frame   (12 cylinders, 8 caps)
#   FRAME_SIDES = 6  ->  hex prism    (18 cylinders, 12 caps)
#   FRAME_SIDES = 8  ->  oct prism    (24 cylinders, 16 caps)
#
# FRAME_EDGE_MM = outer envelope (face-to-face, mm).
# Ou, plates, and frame_config use these directly.
# Cylinder rods are placed on a skeleton inset inward by FRAME_INSET_MM per face.
# Plates are clipped to Ou and subtract Ho; caps still use skeleton placement.

FRAME_SIDES      = 4      # number of polygon sides
FRAME_EDGE_MM    = 32.0   # outer envelope width/depth (mm), face to face
FRAME_INSET_MM   =  5.0   # recess / skeleton inset from outer face (mm)

# Minimum gap at each end of a cylinder rod along its axis (mm).
FRAME_GAP_MM     = 2.0

# ── Cap + collar geometry (after FRAME_INSET_MM) ─────────────────────────────
# Sphere and collar diameter = 2 × recess (no CAP_EXTRA; 7 mm rods sit inside).
CAP_DIAMETER_MM    = 2.0 * FRAME_INSET_MM   # = 10.0 mm with inset 5
COLLAR_DIAMETER_MM = CAP_DIAMETER_MM
# Collar stubs: cylinders from sphere centre toward each rod (3 per corner).
CAP_LENGTH_MM      =  4.0   # length of each stub along its axis (mm)

# ── Ou: rounded bounding-box outline ────────────────────────────────────────
# Corner fillet = FRAME_INSET_MM (same as recess / cap radius). Colour only here.
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

# ── Hs: coaxial hole pipes + back washer (one assembly per holed face) ───────
# Each pipe has wall thickness WT; outer pipe ID = HS_OUTER_OD - 2*WT (gap to inner).
HS_INNER_PIPE_OD_MM  =  10.0   # outer diameter of inner pipe (mm)
HS_OUTER_PIPE_OD_MM  = 15.0   # outer diameter of outer pipe (mm)
HS_WALL_THICKNESS_MM =  1.0   # radial wall thickness per pipe (mm)
HS_LENGTH_MM         =  6.0   # pipe length inward from outer face (mm)
HS_WASHER_THICKNESS_MM = 1.0  # back washer depth along face normal (mm)
HS_COLOR             = METAL_COLOR

# ── Cu: FEA current field in fixed copper pipe (not Hs metal; arrows in JS) ─
# Coil sits outside Hs inner pipe OD, in the gap before Hs outer pipe ID (not in outer bore).
CU_CLEARANCE_FROM_HS_INNER_MM = 0.5   # gap outside Hs inner pipe OD (mm)
CU_CLEARANCE_FROM_HS_OUTER_MM = 0.5   # gap inside Hs outer pipe ID (mm)
CU_PIPE_WALL_THICKNESS_MM     = 1.0   # copper shell thickness (mm)
CU_PIPE_EXTENSION_MM          = 0.5   # extra length inward beyond Hs inner pipe (mm)
CU_SITE_SPACING_MM            = 1.0   # FEA sample spacing inside copper volume (mm)
CU_COLOR_POSITIVE             = (1.00, 0.72, 0.12)   # JS arrow: +current (bright on dark bg)
CU_COLOR_NEGATIVE             = (0.35, 0.88, 1.00)   # JS arrow: −current
# Signed face amplitude (+Z,-Z,+X,-X,+Y,-Y): scales |I| and circulation sign.
CU_FACE_AMPLITUDE             = (1.0, -1.0, 0.85, -0.85, 1.0, -1.0)

# ── Scene scale ─────────────────────────────────────────────────────────────
MM_TO_SCENE = 0.1   # 1 mm -> 0.1 Three.js scene units  (32 mm frame = 3.2 units)
