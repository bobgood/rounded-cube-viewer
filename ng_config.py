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
# ║ SHARED — cube frame (self-contained; no fea_* dependency)                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# The inset cube "skeleton" rods/dipoles are placed on. Corners sit at
# +/- NG_CUBE_HALF_MM on each axis. For the 32 mm cube with 5 mm inset this is
# 11 mm, matching the original 1-dipole centreline placement.
NG_CUBE_HALF_MM = FRAME_EDGE_MM / 2.0 - FRAME_INSET_MM   # half-edge of the skeleton
NG_CUBE_EDGE_MM = 2.0 * NG_CUBE_HALF_MM                  # full skeleton edge length


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ SHARED — mesh density (applies to every NGSolve scene)                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Smaller maxh = denser mesh = more triangles/tets = slower but more accurate.
# Strategy: keep the far air COARSE (global) and refine only the device, where
# the field (and later, saturation) concentrates. Meshing the whole air box at
# device resolution is what makes builds slow, so don't.
NG_MESH_MAXH_MM = 4.0           # global/far-air max element size (mm), incl. air box
# Finer element size on device surfaces (rod + coil); None = use global.
NG_MESH_MAXH_DEVICE_MM = 1.5


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ SCENE: "1dipole" — single steel rod + coaxial solenoid coil in air         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ── Metal rod (the ferromagnetic core) ───────────────────────────────────────
NG_ROD_RADIUS_MM = 3.5      # outer radius of the steel rod (mm)
NG_ROD_LENGTH_MM = 22.0     # length of the rod along its axis (mm)

# ── Coil (solenoid sleeve around the rod) ────────────────────────────────────
# Hollow tube defined by inner and outer radius. Inner must clear the rod
# (NG_COIL_INNER_RADIUS_MM > NG_ROD_RADIUS_MM); the gap is the winding clearance.
NG_COIL_INNER_RADIUS_MM = 4.0   # inner radius of the coil tube (mm)
NG_COIL_OUTER_RADIUS_MM = 5.2   # outer radius of the coil tube (mm)
NG_COIL_LENGTH_MM = 22.0        # coil length along the axis (mm)

# ── Placement relative to the cube envelope ──────────────────────────────────
# Perpendicular distance from the cube's corner edge inward to the rod
# centreline, applied along BOTH axes normal to the rod (y and z). With the
# 32 mm cube, 5 mm puts the centreline at (·, 11, 11) — the original placement.
NG_CENTERLINE_OFFSET_FROM_EDGE_MM = 5.0

# ── Air region (the box the field loops through) ─────────────────────────────
# The air box = cube envelope expanded by this distance beyond every face in
# +/- x, y and z. Larger = more accurate open-boundary field (lines loop
# naturally) but more elements. ~1 device size is a sensible start.
# Active size: 22 mm padding → a 76 mm air cube around the 32 mm envelope.
NG_AIR_PADDING_MM = 22.0

# ── Coil current weights (one entry per coil, same convention as coil_init.py) ──
# Key = edge label e{c1}{c2}: positive → B toward the FIRST-named corner.
# Sign controls current direction (and therefore field polarity).
# |value| is a relative weight; the solver multiplies by NG_COIL_CURRENT_A_MM2.
# Set an edge to 0.0 to disable that coil entirely (no arrows, no J).
# The Strength slider (fea_strength_scale) is a further global multiplier.
# Example: {"e14": 1.0} drives the single coil on edge e14 in the +direction.
# A future 12-coil scene would list all 12 edges: {"e12": 1.0, "e15": -1.0, ...}
NG_COIL_CURRENTS: dict = {"e14": 1.0}

# Base current density (A/mm²) for each unit-weight coil turn.
# This is an effective ampere-turn density for a multi-turn winding — large
# by design so the rod sits near the saturation knee at Strength=1.
NG_COIL_CURRENT_A_MM2 = 120.0

# ── Iron B–H saturation (nonlinear magnetostatics) ───────────────────────────
# Reluctivity nu(|B|) for "typical iron", as a smooth sigmoid in |B|^2:
#     nu(0)   = 1/(mu0 * mu_init)   → unsaturated, high permeability
#     nu(inf) = 1/mu0              → saturated, behaves like air (mu_r → 1)
# mu_init (the unsaturated relative permeability) comes from the "Steel μ"
# slider at solve time; the knee below is the fixed material property.
# B_KNEE is where permeability collapses; ~1.8–2.1 T is typical for iron/steel.
NG_IRON_B_KNEE_T = 1.8      # saturation knee field (Tesla)
# The solver meshes in metres (length_scale 1e-3) so curl(A) is in real Tesla
# and this knee is physically meaningful — do not change that scaling lightly.

# ── Solve (nonlinear magnetostatic, H(curl) edge elements) ───────────────────
NG_SOLVE_ORDER = 1          # H(curl) polynomial order (1 = lowest-order Nédélec)
# Newton iteration: the target current is reached by ramping (load-stepping) in
# NG_SOLVE_RAMP_STEPS increments, each warm-started from the previous, so full
# Newton steps stay in the convergence basin even deep into saturation.
NG_SOLVE_RAMP_STEPS = 2
NG_SOLVE_NEWTON_MAXIT = 6   # max Newton iters per ramp step
# Residual tolerance. The direct curl-curl solve floors near ~1e-4 (round-off at
# this conditioning); the FIELD is fully settled well before then, so this is set
# at the floor to report "converged" cleanly rather than warn at every solve.
NG_SOLVE_NEWTON_TOL = 1e-4
# Field-line sampling grid (B is sampled onto this lattice, then streamlined via
# the existing fea_blines tracer). Coarser = faster.
NG_FIELD_SAMPLE_MM = 2.0


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ SCENE: "12dipoles" — a steel rod + coil on each of the 12 cube edges        ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Twelve dipoles, one centred on each edge of the (inset) cube skeleton. Each
# rod is shorter than its edge and centred on the edge midpoint. All bodies use
# the same cross-section; only placement/orientation and coil current differ.
#
# Cube-corner frame (self-contained — no fea_* dependency)
# --------------------------------------------------------
# The 8 skeleton corners sit at +/- NG_CUBE_HALF_MM on each axis, where
# NG_CUBE_HALF_MM = FRAME_EDGE_MM/2 - FRAME_INSET_MM (= 11 mm for the 32 mm cube
# with 5 mm inset). Corner numbering matches geometry_ids (c1..c8); see
# ng_dipoles.cube_corner_positions(). Edge e{a}{b} runs from corner a to b and
# its coil's +current drives B toward the FIRST-named corner a.

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
# Key = edge label e{a}{b}; +weight → B toward the first-named corner a.
# 0.0 disables that coil's arrows/current (the rod is still drawn). The Strength
# slider scales all of these; NG_COIL_CURRENT_A_MM2 is the per-unit base density.
# Default mirrors the old voxel 12-dipole demo: the four vertical struts driven.
NG12_COIL_CURRENTS: dict = {
    # Top ring (+Z):    e12  e23  e34  e41
    "e12": 0.0, "e23": 0.0, "e34": 0.0, "e41": 0.0,
    # Bottom ring (−Z): e56  e67  e78  e85
    "e56": 0.0, "e67": 0.0, "e78": 0.0, "e85": 0.0,
    # Vertical struts:  e15  e26  e37  e48
    "e15": 1.0, "e26": 1.0, "e37": 1.0, "e48": 1.0,
}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ SCENE: "30coils" — full frame (split edge coils + corner caps + face        ║
# ║         horseshoes). Ported from the old voxel "frame"/"30 coils" scene.    ║
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
