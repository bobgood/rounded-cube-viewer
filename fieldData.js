// fieldData.js — client-side store for the per-config vector-B field grids
// streamed from the Python server (one cube, solved in its canonical pose).
//
// Each field is a dense Bx/By/Bz lattice in TESLA, sampled on a regular grid in
// MILLIMETRES. The viewer works in scene units (MM_TO_SCENE), so the sampler
// takes a LOCAL scene-space point (cube-centred, canonical orientation) and
// returns the interpolated B vector in Tesla. Force/visualisation code rotates
// that into world space.

export const MM_TO_SCENE = 0.1;   // mirror of cube_config.py

export class FieldStore {
  constructor() {
    this.fields = new Map();   // config name → { n, originMm[3], spacingMm, bMax, bx, by, bz }
  }

  has(cfg) { return this.fields.has(cfg); }

  set(cfg, field) { this.fields.set(cfg, field); }

  /**
   * Trilinearly sample B (Tesla) at a LOCAL scene-space point (cube centred,
   * canonical orientation). Writes into `out` {x,y,z}. Returns false (and zeros
   * `out`) when the point lies outside the sampled grid.
   */
  sample(cfg, lx, ly, lz, out) {
    const f = this.fields.get(cfg);
    if (!f) { out.x = out.y = out.z = 0; return false; }

    const n = f.n;
    const inv = 1 / f.spacingMm;
    // scene → mm, then to fractional grid index
    const gx = (lx / MM_TO_SCENE - f.originMm[0]) * inv;
    const gy = (ly / MM_TO_SCENE - f.originMm[1]) * inv;
    const gz = (lz / MM_TO_SCENE - f.originMm[2]) * inv;

    if (gx < 0 || gy < 0 || gz < 0 || gx > n - 1 || gy > n - 1 || gz > n - 1) {
      out.x = out.y = out.z = 0;
      return false;
    }

    const i0 = gx | 0, j0 = gy | 0, k0 = gz | 0;
    const i1 = i0 + 1 < n ? i0 + 1 : i0;
    const j1 = j0 + 1 < n ? j0 + 1 : j0;
    const k1 = k0 + 1 < n ? k0 + 1 : k0;
    const tx = gx - i0, ty = gy - j0, tz = gz - k0;

    const c000 = (i0 * n + j0) * n + k0, c100 = (i1 * n + j0) * n + k0;
    const c010 = (i0 * n + j1) * n + k0, c110 = (i1 * n + j1) * n + k0;
    const c001 = (i0 * n + j0) * n + k1, c101 = (i1 * n + j0) * n + k1;
    const c011 = (i0 * n + j1) * n + k1, c111 = (i1 * n + j1) * n + k1;

    const w000 = (1 - tx) * (1 - ty) * (1 - tz), w100 = tx * (1 - ty) * (1 - tz);
    const w010 = (1 - tx) * ty * (1 - tz),       w110 = tx * ty * (1 - tz);
    const w001 = (1 - tx) * (1 - ty) * tz,       w101 = tx * (1 - ty) * tz;
    const w011 = (1 - tx) * ty * tz,             w111 = tx * ty * tz;

    const lerp = (a) =>
      a[c000] * w000 + a[c100] * w100 + a[c010] * w010 + a[c110] * w110 +
      a[c001] * w001 + a[c101] * w101 + a[c011] * w011 + a[c111] * w111;

    out.x = lerp(f.bx);
    out.y = lerp(f.by);
    out.z = lerp(f.bz);
    return true;
  }
}
