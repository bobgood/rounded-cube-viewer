"""fea_config.py — Scene geometry, FEA solver, and appearance (not the cube envelope).

Cube size / scale: cube_config.py.  Active experiment: FEA_SCENE_ID below.
"""

import math

from cube_config import (
    FRAME_EDGE_MM,
    FRAME_SIDES,
    FRAME_INSET_MM,
    MM_TO_SCENE,
    OU_COLOR,
    HOLE_DIAMETER_MM,
    HO_COLOR,
)

# ── Active experiment (dropdown / server message) ─────────────────────────────
FEA_SCENE_ID = "1dipole"   # "1dipole" | "12dipoles_ng" | "frame" | "dipole" | "12dipoles"

# ── Dipole experiment (rod on one edge + single solenoid coil) ────────────────
# All distances in mm; restart server after editing.
DIPOLE_EDGE_ID            = "e12"   # which cube edge to place the rod on
DIPOLE_ROD_RADIUS_MM      = 3.5     # metal rod outer radius (mm)
DIPOLE_ROD_END_GAP_MM     = 0.0     # clearance cut from each end of the rod (0 = full edge)
DIPOLE_COIL_CLEARANCE_MM  = 0.5     # radial gap from rod OD to coil inner face (mm)
DIPOLE_COIL_THICKNESS_MM  = 1.2     # radial coil sleeve thickness (mm)

# ── Voxel grid ──────────────────────────────────────────────────────────────
VOXEL_SIZE_MM = 0.5          # spacing between voxel centres (mm)

# ── Metal colour ─────────────────────────────────────────────────────────────
# All structural metal (cylinders, caps, collars) shares this colour.
METAL_COLOR = (1.0, 1.0, 1.0)   # pure white; change to e.g. (0.8, 0.82, 0.85) for steel

CYLINDER_COLOR = METAL_COLOR
CAP_COLOR      = METAL_COLOR

# ── Individual cylinder geometry ────────────────────────────────────────────
CYLINDER_LENGTH_MM   = 14.0  # usable length of each rod (mm); centred on edge
CYLINDER_DIAMETER_MM =  7.0  # outer diameter (mm)
CYLINDER_RADIUS_MM   = CYLINDER_DIAMETER_MM / 2.0
# Full cross-section air gap at rod centre (mm). 0 = off. Large values create pole faces.
CYLINDER_SPLIT_GAP_MM = 0.0

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

# Minimum gap at each end of a cylinder rod along its axis (mm).
FRAME_GAP_MM     = 2.0

# ── Cap + collar geometry (after FRAME_INSET_MM) ─────────────────────────────
# Sphere and collar diameter = 2 × recess (no CAP_EXTRA; 7 mm rods sit inside).
CAP_DIAMETER_MM    = 2.0 * FRAME_INSET_MM   # = 10.0 mm with inset 5
COLLAR_DIAMETER_MM = CAP_DIAMETER_MM
# Collar stubs: cylinders from sphere centre toward each rod (3 per corner).
CAP_LENGTH_MM      =  5.0   # length of each stub along its axis (mm)

# ── Face plates ─────────────────────────────────────────────────────────────
# False = omit spin-wheel plates (viewer + FEA steel). Restart server after change.
FEA_FACE_PLATES_ENABLED = False

# Each face of the frame has 4 quadrant panels (A/B/C/D).
# SPIN_WHEEL_OFFSET_MM shifts the dividing lines so each plate is
# 1 mm wider in one axis and 1 mm shorter in the other, creating a
# pinwheel/spin-wheel gap pattern.
PLATE_THICKNESS_MM   = 1.0   # plate depth (mm), flush with outer face
PLATE_GAP_MM         = 5.0   # gap between adjacent plates on the same face (mm)
SPIN_WHEEL_OFFSET_MM = 1.0   # pinwheel offset (mm); 0 = perfectly square plates
PLATE_EDGE_INSET_MM  = 0.0   # additional inset from face edge (0 = full face)
PLATE_COLOR          = METAL_COLOR

# ── Hs: coaxial hole pipes + back washer (one assembly per holed face) ───────
# Each pipe has wall thickness WT; outer pipe ID = HS_OUTER_OD - 2*WT (gap to inner).
HS_INNER_PIPE_OD_MM  =  10.0   # outer diameter of inner pipe (mm)
HS_OUTER_PIPE_OD_MM  = 14.5   # outer diameter of outer pipe (mm)
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
# ── Coil arrows (Cu + Cv share the same palette in JS) ───────────────────────
# Sign picks hue; |weight| from coil_init.py sets intensity (not grey).
COIL_ARROW_COLOR_POSITIVE     = (1.00, 0.72, 0.12)   # warm amber, +current
COIL_ARROW_COLOR_NEGATIVE     = (0.35, 0.88, 1.00)   # cyan, −current
CU_COLOR_POSITIVE             = COIL_ARROW_COLOR_POSITIVE
CU_COLOR_NEGATIVE             = COIL_ARROW_COLOR_NEGATIVE

# ── Cv: edge coils (2 per skeleton edge, 24 total on cube) ───────────────────
# Sleeve around each Cy rod end; gap is inset from corner along the edge.
CV_GAP_FROM_CORNER_MM     = 5.5   # space from corner before coil starts (mm)
CV_EXTEND_MM              = 5.5   # coil length along edge from gap (mm)
CV_THICKNESS_MM           = 1.2   # radial thickness of coil band (mm)
CV_CLEARANCE_FROM_ROD_MM  = 0.25  # gap outside Cy rod OD (mm)
CV_SITE_SPACING_MM        = 1.0   # FEA sample spacing (mm)
CV_COLOR_POSITIVE         = COIL_ARROW_COLOR_POSITIVE
CV_COLOR_NEGATIVE         = COIL_ARROW_COLOR_NEGATIVE
CV_DEFAULT_AMPLITUDE      = 1.0    # unused: weights come from coil_init.py

# ── FEA voxel grid (world space) ─────────────────────────────────────────────
FEA_GRID_PAD_MM           = 0.5
FEA_METAL_MATERIAL_ID     = 1     # structural steel (Cy/Ca/Pl/Hs)
FEA_METAL_MU_R            = 5000.0
FEA_COIL_MATERIAL_ID      = 2     # Cu + Cv on grid (conductors); mu_r like air
FEA_COIL_MU_R             = 1.0
FEA_CURRENT_NOM_A_MM2     = 1.0   # |J| = |coil_weight| × this (A/mm²); sign from weight
# Legacy aliases
FEA_COPPER_MATERIAL_ID    = FEA_COIL_MATERIAL_ID
FEA_COPPER_MU_R           = FEA_COIL_MU_R
FEA_GRID_DEBUG_COLOR      = (0.35, 0.85, 0.45)   # Gm steel debug view

# ── Magnetostatic solve (fea_solve.py) ───────────────────────────────────────
MU0                     = 4.0e-7 * math.pi   # H/m
FEA_SOLVE_ENABLED       = False              # auto-solve at scene build (False: solve on button)
FEA_SOLVE_STORE_FULL_B  = False              # keep full B in solve result (slow .tolist())
FEA_SOLVE_METHOD        = "cg"               # "cg" (fast, low-mem) or "direct" (LU; slow at 69^3)
FEA_SOLVE_CG_RTOL       = 1e-6
FEA_SOLVE_CG_MAXITER    = 5_000
# Coupled 3N system is stiffer; slightly looser rtol keeps runtime practical.
FEA_SOLVE_CG_RTOL_COUPLED    = 1e-5
FEA_SOLVE_CG_MAXITER_COUPLED = 12_000
FEA_SOLVE_CG_LOG_EVERY  = 100                # print CG progress every N iterations (0 = off)
FEA_RUN_SOLVE_TESTS     = False              # inline unit tests after each solve
# Pin vector-potential gauge: True = cell nearest world origin (symmetric device);
# False = legacy corner DOF 0 (breaks x/y/z symmetry).
FEA_SOLVE_PIN_AT_ORIGIN = True
# If set (e.g. 1.0), the solver uses uniform mu_r everywhere and ignores steel on the
# grid. Required for trustworthy B with the current decoupled Ax/Ay/Az formulation;
# use mu_r=1 for force (J x B) until a coupled magnetostatic solver exists.
FEA_SOLVE_UNIFORM_MU_R  = None             # None = use grid steel_mu_r from the caller
# "coupled" = curl(nu curl A) = mu0 J (one 3N system; valid with spatial mu_r).
# "decoupled" = three div(nu grad A_alpha) solves (fast, mu=1 only).
FEA_SOLVE_FORMULATION   = "decoupled"

# ── B-field line view (fea_blines.py) ────────────────────────────────────────
# Field lines need AIR around the design to loop through, so the line view uses a
# SEPARATE coarser + padded grid (the 0.5 mm structural grid has almost no margin).
# Extent ≈ design(32mm) + 2*pad; cells ≈ extent / voxel.  Keep this coarse for speed.
FEA_BLINE_VOXEL_MM      = 2.0    # field-view lattice spacing (coarser = faster solve)
FEA_BLINE_PAD_MM        = 40.0   # air margin around design on every side (mm)
FEA_BLINE_MAX_LINES     = 140    # cap on number of streamlines traced
FEA_BLINE_STEP_MM       = 1.0    # integration step along each line (mm)
FEA_BLINE_MAX_STEPS     = 900    # max integration steps per direction per seed
FEA_BLINE_SEED_STRIDE   = 2      # seed every Nth field-grid cell (uniform spatial spread)
FEA_BLINE_MIN_B_FRAC    = 0.04   # seed only where |B| > frac * max|B|
FEA_BLINE_STOP_FRAC     = 0.004  # keep tracing until |B| < frac * max|B| (lower = longer loops)
# Steel permeability used ONLY for the B-line field grid (separate from the structural
# FEA_METAL_MU_R). The decoupled-A solver is exact only at mu_r = 1; high mu_r introduces
# a spurious asymmetry, so default to vacuum (clean, symmetric coil field). The UI log
# slider overrides this per solve so you can dial steel channeling back in.
FEA_BLINE_MU_R          = 1.0
FEA_BLINE_MU_R_MAX      = 5000.0  # top of the UI log slider
