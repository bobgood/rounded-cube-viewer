"""ng_config.py — Single source of geometry & mesh constants for NGSolve scenes.

THIS FILE CONTAINS ALL VALUES USED FOR BUILDING ANY GEOMETRY OR MESH FOR THIS
AND FUTURE SCENES THAT USE NGSolve. Keep it minimal: if it's a number someone
might want to tweak when shaping a body, placing it, sizing the air region, or
controlling mesh density, it belongs here — not buried in a scene module.
All distances in mm. Restart the server after editing.

Coordinate frame
-----------------
The cube envelope is FRAME_EDGE_MM (from cube_config) centred on the origin, so
each face sits at +/- FRAME_EDGE_MM/2. Rod axes run parallel to the +X cube
edge; centrelines are offset inward from that corner edge (see per-scene below).
"""

from __future__ import annotations

from cube_config import FRAME_EDGE_MM, FRAME_INSET_MM


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ SHARED — cube frame                                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# The inset cube "skeleton" rods/dipoles are placed on. Corners sit at
# +/- NG_CUBE_HALF_MM on each axis. For the 32 mm cube with 5 mm inset this is
# 11 mm, matching the original 1-dipole centreline placement.
NG_CUBE_HALF_MM = FRAME_EDGE_MM / 2.0 - FRAME_INSET_MM   # half-edge of the skeleton
NG_CUBE_EDGE_MM = 2.0 * NG_CUBE_HALF_MM                  # full skeleton edge length

# Active experiment (dropdown / server message)
NG_SCENE_ID = "1dipole"   # "1dipole" | "12dipoles_ng" | "30coils_ng" | "potcore_ng"


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ SHARED — air, mesh, solver, B-line tracing (all NGSolve scenes)            ║
# ╚══════════════════════════════════════════════════════════════════════════╝
NG_AIR_PADDING_MM = 22.0        # air box padding beyond cube envelope (mm)
NG_MESH_MAXH_MM = 4.0           # global/far-air max element size (mm)
NG_MESH_MAXH_DEVICE_MM = 1.5    # device surface refinement; None = use global

# ── Extended grid (UI checkbox) ──────────────────────────────────────────────
# A much larger air box for capturing the far field needed by the (later) two-
# body force/motion model. The cube edge is FRAME_EDGE_MM (~32 mm); this padding
# pushes the box out to ≈200 mm overall (~3 cube-edges of clearance from centre),
# which comfortably contains the force-relevant near field even after the
# Strength slider is turned well up (B ∝ I, so the meaningful radius grows only
# ~∝ I^(1/3)). Paired with a coarser far-air element size so the mesh stays
# tractable (fine device detail is preserved by NG_MESH_MAXH_DEVICE_MM).
NG_AIR_PADDING_EXTENDED_MM = 84.0   # → box ≈ 200 mm (vs 76 mm normal)
NG_MESH_MAXH_EXTENDED_MM = 8.0      # coarser far-air elements when extended
NG_EXTENDED_GRID = False            # runtime toggle (server sets from the checkbox)


def air_padding_mm() -> float:
    """Active air-box padding (mm): extended when the grid checkbox is on."""
    return NG_AIR_PADDING_EXTENDED_MM if NG_EXTENDED_GRID else NG_AIR_PADDING_MM


def mesh_maxh_mm() -> float:
    """Active far-air max element size (mm): coarser when the grid is extended."""
    return NG_MESH_MAXH_EXTENDED_MM if NG_EXTENDED_GRID else NG_MESH_MAXH_MM
NG_COIL_CURRENT_A_MM2 = 120.0   # |J| base density per unit coil weight (A/mm²)
NG_COIL_RESISTIVITY_OHM_M = 1.72e-8   # copper @20°C; ohmic-loss estimate assumes
                                      # the coil annulus is solid conductor (fill=1)
NG_STEEL_DENSITY_G_CM3 = 7.87   # iron/steel density for the mass readout (g/cm³)
NG_COPPER_DENSITY_G_CM3 = 8.96  # copper density for the mass readout (g/cm³)
NG_IRON_B_KNEE_T = 1.8          # iron saturation knee (Tesla)
NG_SOLVE_ORDER = 1
NG_SOLVE_RAMP_STEPS = 2
NG_SOLVE_NEWTON_MAXIT = 6
NG_SOLVE_NEWTON_TOL = 1e-4
NG_FIELD_SAMPLE_MM = 2.0
NG_BLINE_MAX_LINES = 140
NG_BLINE_STEP_MM = 1.0
NG_BLINE_MAX_STEPS = 900
NG_BLINE_SEED_STRIDE = 2
NG_BLINE_MIN_B_FRAC = 0.04
NG_BLINE_STOP_FRAC = 0.004
NG_MU_R_MAX = 5000.0            # top of the UI log Steel μ slider


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ SCENE: "1dipole" — single steel rod + coaxial solenoid coil in air         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ── Metal rod (the ferromagnetic core) ───────────────────────────────────────
NG_ROD_RADIUS_MM = 3.5      # outer radius of the steel rod (mm)
NG_ROD_LENGTH_MM = 22.0     # length of the rod along its axis (mm)

# ── Coil (solenoid sleeve around the rod) ────────────────────────────────────
NG_COIL_INNER_RADIUS_MM = 4.0   # inner radius of the coil tube (mm)
NG_COIL_OUTER_RADIUS_MM = 5.2   # outer radius of the coil tube (mm)
NG_COIL_LENGTH_MM = 22.0        # coil length along the axis (mm)

# ── Placement relative to the cube envelope ──────────────────────────────────
NG_CENTERLINE_OFFSET_FROM_EDGE_MM = 5.0

# ── Coil current weights ─────────────────────────────────────────────────────
# Key = edge label e{c1}{c2}: positive → B toward the FIRST-named corner.
NG_COIL_CURRENTS: dict = {"e14": 1.0}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ SCENE: "12dipoles" — a steel rod + coil on each of the 12 cube edges        ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Twelve dipoles, one centred on each edge of the (inset) cube skeleton. Each
# rod is shorter than its edge and centred on the edge midpoint. All bodies use
# the same cross-section; only placement/orientation and coil current differ.
#
# Cube-corner frame
# --------------------------------------------------------
# The 8 skeleton corners sit at +/- NG_CUBE_HALF_MM on each axis, where
# NG_CUBE_HALF_MM = FRAME_EDGE_MM/2 - FRAME_INSET_MM (= 11 mm for the 32 mm cube
# with 5 mm inset). Corner numbering c1..c8; see ng_dipoles.cube_corner_positions().

# ── Rod + coil cross-section (shared by all 12 dipoles) ──────────────────────
NG12_ROD_RADIUS_MM      = 3.5   # steel rod outer radius (mm)
NG12_COIL_CLEARANCE_MM  = 0.5   # radial gap rod OD → coil ID (mm)
NG12_COIL_THICKNESS_MM  = 1.2   # radial coil sleeve thickness (mm)
# Coil inner/outer radius are derived from the above:
#   inner = rod_radius + clearance ; outer = inner + thickness.

# ── Axial sizing (each rod/coil is centred on its edge midpoint) ─────────────
# The inset skeleton edge is NG_CUBE_EDGE_MM long (= 2*NG_CUBE_HALF_MM = 22 mm).
# Rod/coil are shorter than the edge so neighbouring dipoles don't touch at the
# corners; remaining length is split as an equal gap at each end.
NG12_ROD_LENGTH_MM   = 11.0   # rod length along its edge (mm), centred
NG12_COIL_LENGTH_MM  = 11.0   # coil length along its edge (mm), centred

# ── Per-edge coil current weights (signed; same convention as NG_COIL_CURRENTS) ─
# Key = edge label e{a}{b}; +weight → B toward the first-named corner a. The
# Strength slider scales all of these; NG_COIL_CURRENT_A_MM2 is the per-unit base
# density. All 12 rods are always built; weights only set which coils are driven.
#
# Named CONFIGS (UI "config" dropdown). Each is a sparse {edge: weight} override
# on a 0.0 baseline — only listed edges are driven. We later run every config to
# generate a solver/field file per excitation pattern. Edit / add freely.
NG12_EDGES = (
    "e12", "e23", "e34", "e41",     # top ring (+Z)
    "e56", "e67", "e78", "e85",     # bottom ring (−Z)
    "e15", "e26", "e37", "e48",     # vertical struts
)
NG12_CONFIGS: dict = {
    # face:   all 4 vertical struts, same polarity → top face (+Z) N, bottom (−Z) S.
    "face":   {"e15": 1.0, "e26": 1.0, "e37": 1.0, "e48": 1.0},
    # edge:   two adjacent vertical struts → a dipole localised to one vertical edge.
    "edge":   {"e15": 1.0, "e26": 1.0},
    # twist1: two adjacent struts driven in OPPOSITE directions (up/down) → a
    #         localised shear/twist between corners 1 and 2.
    "twist1": {"e15": 1.0, "e26": -1.0},
    # twist2: all four struts, 2 up / 2 down (adjacent pairs) → a full-cube twist
    #         (corners 1,2 up; 3,4 down).
    "twist2": {"e15": 1.0, "e26": 1.0, "e37": -1.0, "e48": -1.0},
    # corner: the three edges meeting at corner 1, all north toward corner 1.
    "corner": {"e12": 1.0, "e41": -1.0, "e15": 1.0},
    # dipole: a single coil → the weakest, most localised dipole.
    "dipole": {"e15": 1.0},
}
NG12_CONFIG_ACTIVE = "face"   # runtime selection (server sets from the dropdown)


def ng12_currents() -> dict:
    """Full 12-edge weight dict for the active config (0.0 for undriven edges)."""
    base = {e: 0.0 for e in NG12_EDGES}
    base.update(NG12_CONFIGS.get(NG12_CONFIG_ACTIVE, NG12_CONFIGS["face"]))
    return base


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ SCENE: "30coils" — full frame (split edge coils + corner caps + face        ║
# ║         horseshoes).                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Steel skeleton = 12 edge rods + 8 corner caps (sphere + 3 collar stubs) + a
# nested-pipe "horseshoe" on each of the 6 faces (inner pipe + outer pipe joined
# by a back washer). 30 coils = 24 split edge coils (two per edge, E{a}{b} near
# corner a and E{b}{a} near corner b, with a gap at the edge midpoint) + 6 face
# coils (one in each horseshoe annulus). Corners on the inset skeleton sit at
# +/- NG_CUBE_HALF_MM; faces at +/- FRAME_EDGE_MM/2.

# ── Edge rods (Cy): one steel cylinder centred on each edge midpoint ─────────
NG30_ROD_RADIUS_MM = 3.5     # rod outer radius (= CYLINDER_DIAMETER/2)
NG30_ROD_LENGTH_MM = 14.0    # rod length along the edge (centred; leaves ends bare)

# ── Corner caps (Ca): sphere at each corner + 3 collar stubs toward its edges ─
NG30_CAP_RADIUS_MM    = 5.0  # corner sphere radius (= CAP_DIAMETER/2 = inset)
NG30_COLLAR_RADIUS_MM = 5.0  # collar stub radius (= COLLAR_DIAMETER/2)
NG30_COLLAR_LENGTH_MM = 5.0  # collar stub length along its edge, inner end at corner

# ── Edge coils (Cv): annular sleeve, two per edge ────────────────────────────
NG30_CV_GAP_FROM_CORNER_MM    = 5.5   # bare rod length from the corner before the coil
NG30_CV_EXTEND_MM             = 5.5   # coil length along the edge
NG30_CV_THICKNESS_MM          = 1.2   # radial coil band thickness
NG30_CV_CLEARANCE_FROM_ROD_MM = 0.25  # radial gap from rod OD to coil ID

# ── Face horseshoe (Hs): two coaxial steel pipes + a back washer, per face ───
# Both pipes share the face-normal axis and run inward HS_LENGTH from the outer
# face; the washer bridges them behind (deeper inward).
NG30_HS_INNER_PIPE_OD_MM   = 10.0   # inner pipe outer diameter
NG30_HS_OUTER_PIPE_OD_MM   = 14.5   # outer pipe outer diameter
NG30_HS_WALL_THICKNESS_MM  = 1.0    # radial wall thickness of each pipe
NG30_HS_LENGTH_MM          = 6.0    # pipe length inward from the outer face
NG30_HS_WASHER_THICKNESS_MM = 1.0   # back washer depth along the face normal

# ── Face coils (Cu): annular sleeve in the gap between the two Hs pipes ───────
NG30_CU_CLEARANCE_FROM_HS_INNER_MM = 0.5   # radial gap outside the inner pipe OD
NG30_CU_CLEARANCE_FROM_HS_OUTER_MM = 0.5   # radial gap inside the outer pipe ID
NG30_CU_WALL_THICKNESS_MM          = 1.0   # coil band radial thickness (capped to fit)
NG30_CU_EXTENSION_MM               = 0.5   # extra coil length inward beyond the pipes

# ── Coil current weights (corner-keyed for edges, face-keyed for faces) ──────
# Edge coil near corner X takes its weight from key "c{X}" unless an explicit
# directed-edge key (e.g. "e14") is present. Face coil takes its weight from the
# clockwise face key (f1234 …). This reproduces the "common pole at each corner"
# wiring: the 3 edge coils meeting at a corner share that corner's sign, so the
# corner acts as one magnetic pole. Default: top corners +1, bottom −1, faces 0.
NG30_COIL_CURRENTS: dict = {
    "c1": 1.0, "c2": 1.0, "c3": 1.0, "c4": 1.0,
    "c5": -1.0, "c6": -1.0, "c7": -1.0, "c8": -1.0,
    "f1234": 0.0, "f5678": 0.0, "f1265": 0.0,
    "f3487": 0.0, "f1485": 0.0, "f3276": 0.0,
}

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ SCENE: "potcore" — a single nested-pipe pot-core (cup-core) assembly.       ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# One face assembly lifted out of the 30-coils frame: two coaxial steel pipes
# (NG30_HS_*) joined by a back washer, with one coil (NG30_CU_*) in the annulus.
# It reuses all NG30_HS_*/NG30_CU_* dimensions above; only the placement (which
# face) and drive current are scene-specific.
NGPC_FACE_KEY = "f1234"   # which cube face the pot core sits on (outward +Z)
NGPC_NORMAL   = (0.0, 0.0, 1.0)   # outward face normal for NGPC_FACE_KEY
NGPC_CURRENT  = 1.0       # coil current weight (×strength); sign sets polarity
