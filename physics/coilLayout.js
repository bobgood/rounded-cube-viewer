/**
 * Converts a module's rigid-body transform + coil power data into an array
 * of world-space magnetic dipoles, one per coil (54 total: 6 faces × 9 coils).
 *
 * Face group order matches BoxGeometry / RoundedBoxGeometry:
 *   0 +X right   1 −X left   2 +Y top
 *   3 −Y bottom  4 +Z front  5 −Z back
 *
 * Each face has a local normal and two tangent vectors (U column, V row) that
 * define a 3×3 grid at positions ±step and 0 from the face centre.
 */

import * as THREE from "three";
import { CONFIG } from "../config.js";

// Local-space normals for each face
const FACE_NORMALS = [
  new THREE.Vector3( 1,  0,  0),
  new THREE.Vector3(-1,  0,  0),
  new THREE.Vector3( 0,  1,  0),
  new THREE.Vector3( 0, -1,  0),
  new THREE.Vector3( 0,  0,  1),
  new THREE.Vector3( 0,  0, -1),
];

// Tangent U (column direction) and V (row direction) for each face
const FACE_U = [
  new THREE.Vector3( 0,  0,  1),   // +X
  new THREE.Vector3( 0,  0, -1),   // −X
  new THREE.Vector3( 1,  0,  0),   // +Y
  new THREE.Vector3( 1,  0,  0),   // −Y
  new THREE.Vector3( 1,  0,  0),   // +Z
  new THREE.Vector3(-1,  0,  0),   // −Z
];
const FACE_V = [
  new THREE.Vector3( 0,  1,  0),
  new THREE.Vector3( 0,  1,  0),
  new THREE.Vector3( 0,  0,  1),
  new THREE.Vector3( 0,  0, -1),
  new THREE.Vector3( 0,  1,  0),
  new THREE.Vector3( 0,  1,  0),
];

const HALF = CONFIG.CUBE_SIZE / 2;
const STEP = CONFIG.CUBE_SIZE / 3;
const OFFSETS = [-STEP, 0, STEP];   // column / row offsets in the tangent plane

/**
 * Build world-space dipole descriptors for every coil on this module.
 *
 * @param {import('../physics/rigidBody').RigidBody} rb
 * @param {Array<Array<{power: number}>>} coilData  [6][9]
 * @returns {Array<{ worldPos: THREE.Vector3, moment: THREE.Vector3 }>}
 */
export function getCoilDipoles(rb, coilData) {
  const dipoles = [];

  for (let fi = 0; fi < 6; fi++) {
    const localN = FACE_NORMALS[fi];
    const localU = FACE_U[fi];
    const localV = FACE_V[fi];

    // Rotate tangent vectors into world space
    const wNormal = localN.clone().applyQuaternion(rb.orientation);

    for (let ci = 0; ci < 9; ci++) {
      const col = ci % 3;
      const row = Math.floor(ci / 3);

      // Local position: face-centre + grid offset in tangent plane
      const lx = localN.x * HALF + localU.x * OFFSETS[col] + localV.x * OFFSETS[row];
      const ly = localN.y * HALF + localU.y * OFFSETS[col] + localV.y * OFFSETS[row];
      const lz = localN.z * HALF + localU.z * OFFSETS[col] + localV.z * OFFSETS[row];

      // Transform to world: rotate then translate
      const worldPos = new THREE.Vector3(lx, ly, lz)
        .applyQuaternion(rb.orientation)
        .add(rb.position);

      const power  = coilData[fi][ci].power;
      const moment = wNormal.clone().multiplyScalar(power * CONFIG.MOMENT_SCALE);

      dipoles.push({ worldPos, moment });
    }
  }

  return dipoles;
}
