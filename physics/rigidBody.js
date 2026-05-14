/**
 * Rigid body state and semi-implicit Euler integrator.
 *
 * Tracks position, linear velocity, orientation (quaternion), and angular
 * velocity.  Forces and torques are accumulated each frame then integrated.
 *
 * Inertia model: uniform solid cube  →  I = (1/6) m L²
 * (diagonal tensor — same on all axes due to symmetry)
 */

import * as THREE from "three";
import { CONFIG } from "../config.js";

export class RigidBody {
  /**
   * @param {THREE.Vector3} position  initial world position
   */
  constructor(position) {
    this.position        = position.clone();
    this.velocity        = new THREE.Vector3();
    this.orientation     = new THREE.Quaternion();   // unit quaternion
    this.angularVelocity = new THREE.Vector3();      // world-space, rad/s

    this.mass  = CONFIG.CUBE_MASS;
    const I    = (CONFIG.CUBE_MASS * CONFIG.CUBE_SIZE * CONFIG.CUBE_SIZE) / 6;
    this.invI  = 1 / I;   // scalar (isotropic cube)

    // Accumulated for current frame — reset each tick
    this._force  = new THREE.Vector3();
    this._torque = new THREE.Vector3();
  }

  // ── Accumulator API ────────────────────────────────────────────────────────

  resetAccumulators() {
    this._force.set(0, 0, 0);
    this._torque.set(0, 0, 0);
  }

  /**
   * Apply a force at a world-space point.
   * Contributes to both linear momentum and angular momentum (r × F).
   *
   * @param {THREE.Vector3} force     force vector (read-only)
   * @param {THREE.Vector3} worldPos  point of application in world space
   */
  applyForceAtPoint(force, worldPos) {
    this._force.add(force);
    // Torque about CoM: τ = r × F
    const r = new THREE.Vector3().subVectors(worldPos, this.position);
    this._torque.add(r.cross(force));   // r.cross() modifies r in-place
  }

  /**
   * Apply a pure torque (e.g. magnetic alignment m × B).
   * @param {THREE.Vector3} torque  (read-only)
   */
  applyTorque(torque) {
    this._torque.add(torque);
  }

  // ── Integration ────────────────────────────────────────────────────────────

  /**
   * Semi-implicit Euler step.
   * @param {number} dt  seconds
   */
  integrate(dt) {
    // ── Linear ───────────────────────────────────────────────────────────────
    this.velocity.addScaledVector(this._force, dt / this.mass);
    this.velocity.multiplyScalar(CONFIG.LINEAR_DAMPING);
    this.position.addScaledVector(this.velocity, dt);

    // Soft boundary spring — pulls back if too far from origin
    const dist = this.position.length();
    if (dist > CONFIG.WORLD_BOUND) {
      const excess   = dist - CONFIG.WORLD_BOUND;
      const springAcc = -CONFIG.BOUND_STIFFNESS * excess / this.mass;
      // direction toward origin
      this.velocity.addScaledVector(this.position, springAcc * dt / dist);
    }

    // ── Angular ───────────────────────────────────────────────────────────────
    this.angularVelocity.addScaledVector(this._torque, dt * this.invI);
    this.angularVelocity.multiplyScalar(CONFIG.ANGULAR_DAMPING);

    // Quaternion integration:  q += ½ dt · ω_quat · q
    // ω_quat = (ωx, ωy, ωz, 0) — pure quaternion
    const ox = this.angularVelocity.x;
    const oy = this.angularVelocity.y;
    const oz = this.angularVelocity.z;
    const qx = this.orientation.x;
    const qy = this.orientation.y;
    const qz = this.orientation.z;
    const qw = this.orientation.w;

    // ω_quat × q  (quaternion product with pure quaternion on left)
    const half_dt = 0.5 * dt;
    this.orientation.set(
      qx + half_dt * ( ox * qw + oy * qz - oz * qy),
      qy + half_dt * (-ox * qz + oy * qw + oz * qx),
      qz + half_dt * ( ox * qy - oy * qx + oz * qw),
      qw + half_dt * (-ox * qx - oy * qy - oz * qz)
    ).normalize();
  }
}
