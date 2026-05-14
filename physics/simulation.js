/**
 * Physics simulation — owns the pairwise dipole-force loop and syncs
 * rigid-body results back to Three.js mesh transforms each tick.
 *
 * Usage:
 *   const sim = new Simulation(modules);
 *   // in render loop:
 *   sim.update(dt);
 */

import { CONFIG } from "../config.js";
import { dipolePairInteraction } from "./dipole.js";
import { getCoilDipoles } from "./coilLayout.js";

export class Simulation {
  /**
   * @param {Array<{
   *   rigidBody: import('./rigidBody').RigidBody,
   *   coilData:  Array<Array<{power: number}>>,
   *   mesh:      THREE.Mesh,
   *   labelSprite?: THREE.Sprite
   * }>} modules
   */
  constructor(modules) {
    this.modules = modules;
  }

  /**
   * Advance physics by dt seconds and sync Three.js transforms.
   * @param {number} dt  elapsed seconds since last frame (will be clamped)
   */
  update(dt) {
    dt = Math.min(dt, 0.05);  // cap at ~20 fps equivalent to keep numerics stable

    // ── Reset per-frame accumulators ────────────────────────────────────────
    for (const m of this.modules) m.rigidBody.resetAccumulators();

    // ── Build world-space dipole lists for every module ─────────────────────
    const dipoleArrays = this.modules.map(m =>
      getCoilDipoles(m.rigidBody, m.coilData)
    );

    // ── Broad-phase + narrow-phase pairwise interaction ─────────────────────
    //    Only unique pairs (a < b) — Newton 3rd handles the other direction.
    const maxCoilReach = CONFIG.CUBE_SIZE * Math.SQRT2 / 2;  // half-diagonal of face

    for (let a = 0; a < this.modules.length; a++) {
      for (let b = a + 1; b < this.modules.length; b++) {
        const rbA = this.modules[a].rigidBody;
        const rbB = this.modules[b].rigidBody;

        // Broad-phase: skip module pair if no coils can possibly be within cutoff
        const centreDist = rbA.position.distanceTo(rbB.position);
        if (centreDist > CONFIG.DIPOLE_CUTOFF_DIST + 2 * maxCoilReach) continue;

        const dipolesA = dipoleArrays[a];
        const dipolesB = dipoleArrays[b];

        // Narrow-phase: every coil on A vs every coil on B  (54×54 = 2916 pairs)
        for (const dA of dipolesA) {
          for (const dB of dipolesB) {
            const result = dipolePairInteraction(
              dA.worldPos, dA.moment,
              dB.worldPos, dB.moment
            );
            if (result === null) continue;

            const { force, torque1, torque2 } = result;

            // Apply to B: force at coil-B position + magnetic alignment torque
            rbB.applyForceAtPoint(force, dB.worldPos);
            rbB.applyTorque(torque2);

            // Apply to A: Newton 3rd (negate in-place — force is a fresh clone)
            force.negate();
            rbA.applyForceAtPoint(force, dA.worldPos);
            rbA.applyTorque(torque1);
          }
        }
      }
    }

    // ── Integrate all rigid bodies ──────────────────────────────────────────
    for (const m of this.modules) m.rigidBody.integrate(dt);

    // ── Sync Three.js mesh transforms ──────────────────────────────────────
    for (const m of this.modules) {
      m.mesh.position.copy(m.rigidBody.position);
      m.mesh.quaternion.copy(m.rigidBody.orientation);

      if (m.labelSprite) {
        m.labelSprite.position.set(
          m.rigidBody.position.x,
          m.rigidBody.position.y + CONFIG.CUBE_SIZE / 2 + 0.5,
          m.rigidBody.position.z
        );
      }
    }
  }
}
