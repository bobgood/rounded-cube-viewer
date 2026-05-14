/**
 * Magnetic dipole–dipole interaction.
 *
 * Reference formula (SI-like, but K = µ₀/4π is a dimensionless tuning knob here):
 *
 *   Field of dipole-1 at displacement r from p1:
 *     B₁ = K/r³ · [3(m₁·r̂)r̂ − m₁]
 *
 *   Force on dipole-2 sitting in B₁:
 *     F = 3K/r⁴ · [(m₁·r̂)m₂ + (m₂·r̂)m₁ + (m₁·m₂)r̂ − 5(m₁·r̂)(m₂·r̂)r̂]
 *
 *   Magnetic alignment torque on dipole-2:
 *     τ₂ = m₂ × B₁
 *
 *   By Newton's third law, force on dipole-1 = −F.
 *   Field of dipole-2 at p1 uses the same formula (the two sign flips cancel).
 */

import * as THREE from "three";
import { CONFIG } from "../config.js";

// Pre-allocated scratch vectors — safe for single-threaded JS
const _r    = new THREE.Vector3();
const _rhat = new THREE.Vector3();
const _B1   = new THREE.Vector3();
const _B2   = new THREE.Vector3();
const _F    = new THREE.Vector3();
const _tmp  = new THREE.Vector3();

/**
 * Compute the pairwise interaction between two magnetic dipoles.
 *
 * @param {THREE.Vector3} pos1  world position of dipole 1
 * @param {THREE.Vector3} m1    magnetic moment of dipole 1
 * @param {THREE.Vector3} pos2  world position of dipole 2
 * @param {THREE.Vector3} m2    magnetic moment of dipole 2
 *
 * @returns {{ force: THREE.Vector3, torque1: THREE.Vector3, torque2: THREE.Vector3 } | null}
 *   force   — force on dipole-2 (force on dipole-1 = −force, Newton 3rd)
 *   torque1 — magnetic alignment torque on body that owns dipole-1
 *   torque2 — magnetic alignment torque on body that owns dipole-2
 *   Returns null when the pair is beyond DIPOLE_CUTOFF_DIST.
 */
export function dipolePairInteraction(pos1, m1, pos2, m2) {
  _r.subVectors(pos2, pos1);
  let r = _r.length();

  if (r > CONFIG.DIPOLE_CUTOFF_DIST) return null;
  r = Math.max(r, CONFIG.DIPOLE_MIN_DIST);

  _rhat.copy(_r).divideScalar(r);

  const K  = CONFIG.MU_OVER_4PI;
  const r3 = r * r * r;
  const r4 = r3 * r;

  // ── Fields ─────────────────────────────────────────────────────────────────
  // B₁ at pos2  (r̂ points from 1 → 2)
  const m1DotR = m1.dot(_rhat);
  _B1.copy(_rhat).multiplyScalar(3 * m1DotR).sub(m1).multiplyScalar(K / r3);

  // B₂ at pos1  (r̂₂₁ = −r̂, double-negative resolves to same formula with m2)
  const m2DotR = m2.dot(_rhat);
  _B2.copy(_rhat).multiplyScalar(3 * m2DotR).sub(m2).multiplyScalar(K / r3);

  // ── Force on dipole-2 ──────────────────────────────────────────────────────
  const m1DotM2 = m1.dot(m2);
  _F.set(0, 0, 0);
  _tmp.copy(m2).multiplyScalar(m1DotR);                          // (m₁·r̂) m₂
  _F.add(_tmp);
  _tmp.copy(m1).multiplyScalar(m2DotR);                          // (m₂·r̂) m₁
  _F.add(_tmp);
  _tmp.copy(_rhat).multiplyScalar(m1DotM2);                      // (m₁·m₂) r̂
  _F.add(_tmp);
  _tmp.copy(_rhat).multiplyScalar(-5 * m1DotR * m2DotR);         // −5(…)(…) r̂
  _F.add(_tmp);
  _F.multiplyScalar(3 * K / r4);

  // Safety clamp — prevents blow-up when r is near DIPOLE_MIN_DIST
  const fLen = _F.length();
  if (fLen > CONFIG.MAX_FORCE_PER_PAIR) {
    _F.multiplyScalar(CONFIG.MAX_FORCE_PER_PAIR / fLen);
  }

  // ── Magnetic alignment torques  τ = m × B ─────────────────────────────────
  const torque2 = new THREE.Vector3().crossVectors(m2, _B1);
  const torque1 = new THREE.Vector3().crossVectors(m1, _B2);

  return { force: _F.clone(), torque1, torque2 };
}
