/**
 * Global configuration — edit values here to tune behaviour.
 * All distances in scene units (~metres), forces in Newtons, angles in rad/s.
 */
export const CONFIG = {

  // ── Geometry ───────────────────────────────────────────────────────────────
  CUBE_SIZE:     1.6,   // side length of each cube module
  CUBE_RADIUS:   0.22,  // corner rounding radius
  CUBE_SEGMENTS:6,     // subdivision segments for rounding

  // ── Magnetic physics ───────────────────────────────────────────────────────
  /** Pairs further apart than this are skipped entirely (1/r⁴ → negligible). */
  DIPOLE_CUTOFF_DIST:  2.5,

  /** Minimum allowed separation — clamps r to avoid 1/r⁴ singularity. */
  DIPOLE_MIN_DIST:     0.25,

  /** Peak magnetic moment per coil at full power (A·m² equiv, dimensionless here). */
  MOMENT_SCALE:        0.5,

  /** Relative permeability constant — overall strength knob. */
  MU_OVER_4PI:         0.4,

  /** Hard force cap per dipole-pair interaction — prevents single-step blow-up. */
  MAX_FORCE_PER_PAIR:  2.0,

  // ── Rigid-body dynamics ────────────────────────────────────────────────────
  CUBE_MASS:           1.0,    // kg (dimensionless but consistent)

  /** Per-frame velocity multiplier — models air resistance / eddy-current drag. */
  LINEAR_DAMPING:      0.985,

  /** Per-frame angular-velocity multiplier. */
  ANGULAR_DAMPING:     0.980,

  /** Random initial spin magnitude applied at spawn (rad/s).  Set 0 to disable. */
  INITIAL_ANGULAR_SPEED: 0.8,

  /** Modules beyond this radius from origin are pulled back by a spring. */
  WORLD_BOUND:         5.0,
  BOUND_STIFFNESS:     3.0,   // N/m spring constant

  // ── Coil animation ─────────────────────────────────────────────────────────
  COIL_SPEED_MIN: 0.004,   // slowest drift rate toward new target
  COIL_SPEED_MAX: 0.016,   // fastest drift rate

};
