// obbCollision.js — Separating-Axis (SAT) contact between two equal oriented
// cubes of half-edge h. Covers all contact features:
//   • corner-face / edge-face  → the min-penetration axis is a box face normal
//   • edge-edge                → the min-penetration axis is an edgeₐ × edge_b
// Returns the minimum-translation normal (oriented A→B), penetration depth, and a
// representative contact point in world space — enough for an impulse resolver.
//
// The contact point is the penetration-weighted centroid of the incident box's
// vertices that lie under the reference face (so face-flush gives the face centre
// → little spin; a single corner gives that corner → strong spin), or the segment
// closest-point for edge-edge.

import * as THREE from "three";

const _mat = new THREE.Matrix4();
const _A = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
const _B = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
const _d = new THREE.Vector3();
const _L = new THREE.Vector3();
const _bestL = new THREE.Vector3();
const _cross = new THREE.Vector3();
const _vert = new THREE.Vector3();
const _acc = new THREE.Vector3();
const _ec1 = new THREE.Vector3();
const _ec2 = new THREE.Vector3();
const _csR = new THREE.Vector3();
const _csP = new THREE.Vector3();
const _csQ = new THREE.Vector3();

const _SIGNS = [];
for (let i = -1; i <= 1; i += 2)
  for (let j = -1; j <= 1; j += 2)
    for (let k = -1; k <= 1; k += 2) _SIGNS.push([i, j, k]);

function axesFromQuat(q, out) {
  _mat.makeRotationFromQuaternion(q);
  const e = _mat.elements;
  out[0].set(e[0], e[1], e[2]);
  out[1].set(e[4], e[5], e[6]);
  out[2].set(e[8], e[9], e[10]);
}

// Half-projection of an h-cube with the given axes onto unit L.
function radius(axes, h, L) {
  return h * (Math.abs(axes[0].dot(L)) + Math.abs(axes[1].dot(L)) + Math.abs(axes[2].dot(L)));
}

// Closest points between segments c1±h1·d1 and c2±h2·d2 (d unit) → midpoint into out.
function closestSegMid(c1, d1, h1, c2, d2, h2, out) {
  _csR.subVectors(c1, c2);
  const b = d1.dot(d2);
  const cc = d1.dot(_csR);
  const f = d2.dot(_csR);
  const denom = 1 - b * b;          // a·e − b² with unit dirs
  let s = denom > 1e-8 ? (b * f - cc) / denom : 0;
  s = Math.max(-h1, Math.min(h1, s));
  let t = b * s + f;
  t = Math.max(-h2, Math.min(h2, t));
  s = b * t - cc;
  s = Math.max(-h1, Math.min(h1, s));
  _csP.copy(c1).addScaledVector(d1, s);
  _csQ.copy(c2).addScaledVector(d2, t);
  out.copy(_csP).add(_csQ).multiplyScalar(0.5);
}

/**
 * @param {THREE.Vector3} pa  centre of cube A
 * @param {THREE.Quaternion} qa orientation of A
 * @param {THREE.Vector3} pb  centre of cube B
 * @param {THREE.Quaternion} qb orientation of B
 * @param {number} h half-edge (same for both)
 * @param {{n:THREE.Vector3, depth:number, point:THREE.Vector3}} out
 * @returns out, or null if the cubes are separated (no contact)
 */
export function obbContact(pa, qa, pb, qb, h, out) {
  axesFromQuat(qa, _A);
  axesFromQuat(qb, _B);
  _d.subVectors(pb, pa);

  let minPen = Infinity;
  let type = -1, si = -1, sj = -1;   // type 0=A face, 1=B face, 2=edge×edge

  // Returns false if THIS axis separates the boxes (→ no contact at all).
  const consider = (L, kind, i, j, bias) => {
    const len = L.length();
    if (len < 1e-6) return true;     // degenerate (parallel edges) — not separating
    _L.copy(L).multiplyScalar(1 / len);
    const dist = Math.abs(_d.dot(_L));
    const pen = radius(_A, h, _L) + radius(_B, h, _L) - dist;
    if (pen < 0) return false;       // gap on this axis → separated
    if (pen + bias < minPen) { minPen = pen + bias; _bestL.copy(_L); type = kind; si = i; sj = j; }
    return true;
  };

  for (let i = 0; i < 3; i++) if (!consider(_A[i], 0, i, -1, 0)) return null;
  for (let i = 0; i < 3; i++) if (!consider(_B[i], 1, i, -1, 0)) return null;
  // Edge×edge axes carry a tiny bias so a face wins near-ties (avoids jitter).
  for (let i = 0; i < 3; i++)
    for (let j = 0; j < 3; j++) {
      _cross.crossVectors(_A[i], _B[j]);
      if (!consider(_cross, 2, i, j, 1e-3)) return null;
    }

  if (_d.dot(_bestL) < 0) _bestL.negate();          // orient normal A→B
  out.n.copy(_bestL);
  out.depth = Math.max(0, radius(_A, h, _bestL) + radius(_B, h, _bestL) - Math.abs(_d.dot(_bestL)));

  if (type === 2) {
    // Edge-edge: extremal edge of A toward +n and of B toward −n, then closest pts.
    const a1 = (si + 1) % 3, a2 = (si + 2) % 3;
    _ec1.copy(pa)
      .addScaledVector(_A[a1], h * (Math.sign(_A[a1].dot(_bestL)) || 1))
      .addScaledVector(_A[a2], h * (Math.sign(_A[a2].dot(_bestL)) || 1));
    const b1 = (sj + 1) % 3, b2 = (sj + 2) % 3;
    _ec2.copy(pb)
      .addScaledVector(_B[b1], -h * (Math.sign(_B[b1].dot(_bestL)) || 1))
      .addScaledVector(_B[b2], -h * (Math.sign(_B[b2].dot(_bestL)) || 1));
    closestSegMid(_ec1, _A[si], h, _ec2, _B[sj], h, out.point);
  } else {
    // Face contact: reference box owns the normal; average the incident box's
    // penetrating vertices (weighted by depth below the reference face).
    const refC   = type === 0 ? pa : pb;
    const incC   = type === 0 ? pb : pa;
    const incAx  = type === 0 ? _B : _A;
    const sign   = type === 0 ? 1 : -1;                 // ref face faces +n (A) or −n (B)
    const planePos = refC.dot(_bestL) + sign * h;
    _acc.set(0, 0, 0);
    let wsum = 0;
    for (const s of _SIGNS) {
      _vert.copy(incC)
        .addScaledVector(incAx[0], h * s[0])
        .addScaledVector(incAx[1], h * s[1])
        .addScaledVector(incAx[2], h * s[2]);
      const along = _vert.dot(_bestL);
      const depth = sign > 0 ? planePos - along : along - planePos;
      if (depth > 0) { _acc.addScaledVector(_vert, depth); wsum += depth; }
    }
    if (wsum > 1e-9) out.point.copy(_acc).multiplyScalar(1 / wsum);
    else out.point.copy(pa).add(pb).multiplyScalar(0.5);
  }
  return out;
}
