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
# ║ SCENE: "ngmesh" — single steel rod + coaxial solenoid coil in air          ║
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

# ── Coil current (magnetostatic source) ──────────────────────────────────────
# Fixed coil current density magnitude (A/mm^2). The direction follows the cube
# edge convention: positive current on edge e{c1}{c2} circulates so B points
# toward the FIRST-named corner (e14 here → B toward corner 1, i.e. +X). This
# single-coil scene sits on edge e14; a future 12-coil scene will set a signed
# weight per edge (J["e12"]=1.0, ...) and reuse the same convention.
# This is an effective ampere-turn density (N*I/area) for a multi-turn winding,
# not a single bare conductor, so the large value is physical. The "Strength"
# slider (fea_strength_scale) multiplies it; at this base the rod sits near the
# saturation knee, so the slider sweeps from soft-iron to fully saturated.
NG_COIL_EDGE = "e14"
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
# ║ FUTURE SCENES — add new scene constants below                              ║
# ║ Keep each scene's geometry/mesh knobs in their own labelled block here so  ║
# ║ this file stays the one place to tweak anything NGSolve builds.            ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# (none yet)
