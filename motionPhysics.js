// motionPhysics.js — level-1, no-iron-coupling field & force engine for the
// motion-staging view. Superposes each cube's precomputed single-body B field
// (linear basis) and reads force off the field, never off coil positions.
//
//  • sampleWorldB   — total B (Tesla) at a world point = Σ bodies.
//  • buildBMagGrid  — |B| on a world-centred cubic lattice for the isosurface.
//  • computeForces  — net force + torque + per-corner "twist" arrows on each
//                     body via the Maxwell-stress CROSS term (the only part that
//                     survives as a genuine inter-body force; the self-field
//                     integrates to zero and is excluded, so it never swamps the
//                     interaction).
//
// A "body descriptor" is: { config, pos:Vector3, qTot:Quaternion (canonical→
// world), qInv:Quaternion (world→canonical), scale:Number (current×polarity) }.

import * as THREE from "three";

const _MU0 = 4 * Math.PI * 1e-7;

const _pl = new THREE.Vector3();
const _bl = new THREE.Vector3();
const _bw = new THREE.Vector3();

// B (Tesla) from ONE body at a world point → out.
export function sampleBodyB(store, body, px, py, pz, out) {
  _pl.set(px - body.pos.x, py - body.pos.y, pz - body.pos.z).applyQuaternion(body.qInv);
  if (store.sample(body.config, _pl.x, _pl.y, _pl.z, _bl)) {
    out.copy(_bl).applyQuaternion(body.qTot).multiplyScalar(body.scale);
  } else {
    out.set(0, 0, 0);
  }
  return out;
}

// Total B (Tesla) from ALL bodies at a world point → out.
export function sampleWorldB(store, bodies, px, py, pz, out) {
  out.set(0, 0, 0);
  for (const b of bodies) {
    _pl.set(px - b.pos.x, py - b.pos.y, pz - b.pos.z).applyQuaternion(b.qInv);
    if (store.sample(b.config, _pl.x, _pl.y, _pl.z, _bl)) {
      _bw.copy(_bl).applyQuaternion(b.qTot).multiplyScalar(b.scale);
      out.add(_bw);
    }
  }
  return out;
}

// |B| on a world cubic lattice (origin scalar, uniform step) ready for
// extractIsosurface(values, n, iso, origin, step).
export function buildBMagGrid(store, bodies, half, n) {
  const values = new Float32Array(n * n * n);
  const step = (2 * half) / (n - 1);
  const origin = -half;
  const b = new THREE.Vector3();
  let bMax = 0;
  let idx = 0;
  for (let i = 0; i < n; i++) {
    const x = origin + i * step;
    for (let j = 0; j < n; j++) {
      const y = origin + j * step;
      for (let k = 0; k < n; k++) {
        const z = origin + k * step;
        sampleWorldB(store, bodies, x, y, z, b);
        const m = b.length();
        values[idx++] = m;
        if (m > bMax) bMax = m;
      }
    }
  }
  return { values, n, origin, step, bMax };
}

// Canonical box faces: outward normal + two in-plane axes.
const _FACES = [
  { n: [ 1, 0, 0], u: [0, 1, 0], v: [0, 0, 1] },
  { n: [-1, 0, 0], u: [0, 1, 0], v: [0, 0, 1] },
  { n: [0,  1, 0], u: [1, 0, 0], v: [0, 0, 1] },
  { n: [0, -1, 0], u: [1, 0, 0], v: [0, 0, 1] },
  { n: [0, 0,  1], u: [1, 0, 0], v: [0, 1, 0] },
  { n: [0, 0, -1], u: [1, 0, 0], v: [0, 1, 0] },
];

const _btot = new THREE.Vector3();
const _bself = new THREE.Vector3();
const _bother = new THREE.Vector3();
const _nW = new THREE.Vector3();
const _pW = new THREE.Vector3();
const _Tn = new THREE.Vector3();
const _t1 = new THREE.Vector3();
const _r = new THREE.Vector3();

/**
 * Net force, torque and per-corner differential ("twist") force for each body,
 * from a Maxwell-stress integral over an oriented box hugging the cube.
 *
 * @param half     cube half-edge (scene units)
 * @param margin   box stand-off beyond the cube faces (scene units)
 * @param faceG    samples per face edge (faceG² points per face)
 * @param sceneToM metres per scene unit — converts the area element to m² so the
 *                 returned force is in real NEWTONS and torque in real N·m.
 */
export function computeForces(store, bodies, half, margin = 0.25, faceG = 6, sceneToM = 0.01) {
  const HB = half + margin;
  const celluv = (2 * HB) / faceG;
  const dAm = (celluv * sceneToM) * (celluv * sceneToM);   // area element in m²
  const out = [];

  for (const body of bodies) {
    const net = new THREE.Vector3();
    const torque = new THREE.Vector3();
    const cornerSum = Array.from({ length: 8 }, () => new THREE.Vector3());

    for (const f of _FACES) {
      for (let a = 0; a < faceG; a++) {
        const su = -HB + (a + 0.5) * celluv;
        for (let c = 0; c < faceG; c++) {
          const sv = -HB + (c + 0.5) * celluv;
          const lx = f.n[0] * HB + f.u[0] * su + f.v[0] * sv;
          const ly = f.n[1] * HB + f.u[1] * su + f.v[1] * sv;
          const lz = f.n[2] * HB + f.u[2] * su + f.v[2] * sv;

          _pW.set(lx, ly, lz).applyQuaternion(body.qTot).add(body.pos);
          _nW.set(f.n[0], f.n[1], f.n[2]).applyQuaternion(body.qTot);

          sampleWorldB(store, bodies, _pW.x, _pW.y, _pW.z, _btot);
          sampleBodyB(store, body, _pW.x, _pW.y, _pW.z, _bself);
          _bother.copy(_btot).sub(_bself);

          // Cross-term stress: T·n = (1/μ0)[ (Bs·n)Bo + (Bo·n)Bs − (Bs·Bo) n ]
          const sn = _bself.dot(_nW);
          const on = _bother.dot(_nW);
          const so = _bself.dot(_bother);
          _Tn.set(0, 0, 0)
            .addScaledVector(_bother, sn)
            .addScaledVector(_bself, on)
            .addScaledVector(_nW, -so)
            .multiplyScalar(dAm / _MU0);                 // Newtons (B in Tesla, dAm in m²)

          net.add(_Tn);
          _r.copy(_pW).sub(body.pos);
          torque.add(_t1.crossVectors(_r, _Tn));         // N·(scene units) — scaled to N·m below

          const ci = (lx >= 0 ? 1 : 0) | (ly >= 0 ? 2 : 0) | (lz >= 0 ? 4 : 0);
          cornerSum[ci].add(_Tn);
        }
      }
    }
    torque.multiplyScalar(sceneToM);                     // lever arm scene units → m ⇒ N·m

    const avg = net.clone().multiplyScalar(1 / 8);
    const cornerPos = [];
    const cornerForce = [];
    for (let ci = 0; ci < 8; ci++) {
      const sx = (ci & 1) ? half : -half;
      const sy = (ci & 2) ? half : -half;
      const sz = (ci & 4) ? half : -half;
      cornerPos.push(new THREE.Vector3(sx, sy, sz).applyQuaternion(body.qTot).add(body.pos));
      cornerForce.push(cornerSum[ci].sub(avg));   // differential = pure twist
    }

    out.push({ force: net, torque, center: body.pos.clone(), cornerPos, cornerForce });
  }
  return out;
}
