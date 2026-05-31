// motion.js — staging view for two-body (and N-body) motion modelling.
//
// This is the VISUAL/STAGING layer only: rounded-cube bodies, offset from the
// origin, each carrying a yellow "magnetic-north" arrow along every energised
// edge. It needs no solver and no B-field files — arrow direction comes purely
// from the config weights and the chosen orientation. The B-field files plug in
// LATER at the force/motion stage, which is intentionally kept out of here.
//
// Shared seam for other scenes: a body is built from a SCENE DESCRIPTOR
// (geometry + feature list + config map + orientation group). Only the
// 12-dipole descriptor exists today; 1-dipole / pot-core / 30-coil descriptors
// can be added the same way without touching the stage/Body machinery.

import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

// ── Cube envelope geometry (matches cube_config.py: 32 mm edge, 5 mm fillet,
//    MM_TO_SCENE = 0.1 → 3.2 scene-unit cube, 0.5 fillet radius) ───────────────
export const HALF = 1.6;     // half edge in scene units (FRAME_EDGE_MM/2 * MM_TO_SCENE)
const RR   = 0.5;     // corner/edge fillet radius   (FRAME_INSET_MM * MM_TO_SCENE)
const SEG  = 6;       // rounded-box subdivision

const OU_COLOR    = new THREE.Color(0.35, 0.65, 1.0);   // cube envelope (matches Ou)
const ARROW_COLOR = new THREE.Color(0xffd21f);          // magnetic-north arrow (yellow)

// ── Cube skeleton: corner numbering + edge labels (mirror of ng_dipoles.py /
//    ng_config.NG12_EDGES). Source of truth for physics is the server; this is
//    a presentational mirror for the staging arrows. ───────────────────────────
const CORNER_SIGN = {
  1: [+1, +1, +1], 2: [+1, -1, +1], 3: [-1, -1, +1], 4: [-1, +1, +1],
  5: [+1, +1, -1], 6: [+1, -1, -1], 7: [-1, -1, -1], 8: [-1, +1, -1],
};
// edge label → [cornerA, cornerB]; +weight ⇒ magnetic north toward cornerA.
const EDGE_CORNERS = {
  e12: [1, 2], e23: [2, 3], e34: [3, 4], e41: [4, 1],   // top ring (+Z)
  e56: [5, 6], e67: [6, 7], e78: [7, 8], e85: [8, 5],   // bottom ring (−Z)
  e15: [1, 5], e26: [2, 6], e37: [3, 7], e48: [4, 8],   // vertical struts
};

// ── Named configs (mirror of ng_config.NG12_CONFIGS): sparse {edge: weight} ────
export const MOTION_CONFIGS = {
  face:   { e15: 1, e26: 1, e37: 1, e48: 1 },
  edge:   { e15: 1, e26: 1 },
  twist1: { e15: 1, e26: -1 },
  twist2: { e15: 1, e26: 1, e37: -1, e48: -1 },
  corner: { e12: 1, e41: -1, e15: 1 },   // three edges at corner 1, all north toward it
  dipole: { e15: 1 },                    // single coil
};

// Per-box power/polarity level t ∈ [-1, +1]:
//   |t| sets the current multiplier on a LOG scale 0.1×…1× (= 1%…100% power,
//   since ohmic power ∝ current²); the SIGN reverses polarity (flips north↔south).
export function levelToDrive(t) {
  const v = Math.max(-1, Math.min(1, Number(t)));
  const mag = Math.abs(v);
  const currentScale = Math.pow(10, mag - 1);          // 0.1 … 1.0
  return {
    signed: v,
    currentScale,
    powerPct: currentScale * currentScale * 100,        // 1 … 100
    polarity: v < 0 ? -1 : 1,
  };
}

// ── Orientation = primary face-axis × NSEW roll (24 = full cube rotation group) ─
export const ORIENT_AXES = {
  "+X": [1, 0, 0], "-X": [-1, 0, 0],
  "+Y": [0, 1, 0], "-Y": [0, -1, 0],
  "+Z": [0, 0, 1], "-Z": [0, 0, -1],
};
export const ORIENT_ROLLS = { N: 0, E: 90, S: 180, W: 270 };

const _UP = new THREE.Vector3(0, 0, 1);

// Rotation that maps canonical +Z → the chosen face-axis, then rolls NSEW about
// it. This single rotation is applied to BOTH the arrow geometry now and (later)
// to the stored B-field basis — keeping the staging view and the force engine
// consistent.
function orientationMatrix(axisKey, rollKey) {
  const axis = new THREE.Vector3(...(ORIENT_AXES[axisKey] ?? ORIENT_AXES["+Z"]));
  const q = new THREE.Quaternion();
  // setFromUnitVectors degenerates for the antiparallel case; nudge it.
  if (axis.dot(_UP) < -0.9999) {
    q.setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
  } else {
    q.setFromUnitVectors(_UP, axis);
  }
  const deg = ORIENT_ROLLS[rollKey] ?? 0;
  if (deg) {
    q.premultiply(new THREE.Quaternion().setFromAxisAngle(axis, THREE.MathUtils.degToRad(deg)));
  }
  return new THREE.Matrix4().makeRotationFromQuaternion(q);
}

function cornerVec(id) {
  const s = CORNER_SIGN[id];
  return new THREE.Vector3(s[0] * HALF, s[1] * HALF, s[2] * HALF);
}

// Closest point on the rounded-box SURFACE (axis-aligned, centred at origin).
// Clamp to the inner box [-(HALF-RR), HALF-RR]^3, then push out by RR along the
// offset direction. Sampling an edge corner-to-corner and projecting this way
// gives a straight ridge in the middle that curves around the fillet at the
// corners — so the arrow hugs the curved edge.
const _inner = HALF - RR;
function surfaceProject(p, out) {
  const cx = Math.max(-_inner, Math.min(_inner, p.x));
  const cy = Math.max(-_inner, Math.min(_inner, p.y));
  const cz = Math.max(-_inner, Math.min(_inner, p.z));
  let dx = p.x - cx, dy = p.y - cy, dz = p.z - cz;
  const len = Math.hypot(dx, dy, dz) || 1;
  // small epsilon (1.04) lifts the tube just proud of the surface
  out.set(cx + dx / len * RR * 1.04, cy + dy / len * RR * 1.04, cz + dz / len * RR * 1.04);
  return out;
}

// One yellow arrow hugging the edge between two (already-rotated) cube corners,
// pointing toward `headCorner` (the magnetic-north end). `sizeF` scales the
// tube/head so lower power reads as a thinner, smaller arrow. Returns a Group.
function buildEdgeArrow(startCorner, headCorner, sizeF = 1) {
  const grp = new THREE.Group();
  const a = startCorner.clone();   // tail end
  const b = headCorner.clone();    // north (head) end
  const tmp = new THREE.Vector3();

  // Sample along the edge (trim the ends so the arrow stays clear of the
  // adjacent edges meeting at each corner), projected onto the fillet surface.
  const N = 16, t0 = 0.14, t1 = 0.90;
  const pts = [];
  for (let i = 0; i <= N; i++) {
    const t = t0 + (t1 - t0) * (i / N);
    tmp.copy(a).lerp(b, t);
    pts.push(surfaceProject(tmp, new THREE.Vector3()));
  }
  const curve = new THREE.CatmullRomCurve3(pts);
  const tube = new THREE.Mesh(
    new THREE.TubeGeometry(curve, 24, 0.045 * sizeF, 8, false),
    new THREE.MeshStandardMaterial({
      color: ARROW_COLOR, emissive: ARROW_COLOR, emissiveIntensity: 0.45,
      roughness: 0.4, metalness: 0.0,
    }),
  );
  grp.add(tube);

  // Cone arrowhead at the north end, oriented along the local tangent.
  const tip = pts[pts.length - 1];
  const prev = pts[pts.length - 2];
  const dir = new THREE.Vector3().subVectors(tip, prev).normalize();
  const cone = new THREE.Mesh(
    new THREE.ConeGeometry(0.11 * sizeF, 0.26 * sizeF, 12),
    new THREE.MeshStandardMaterial({
      color: ARROW_COLOR, emissive: ARROW_COLOR, emissiveIntensity: 0.5,
      roughness: 0.4, metalness: 0.0,
    }),
  );
  cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
  cone.position.copy(tip).addScaledVector(dir, 0.10 * sizeF);
  grp.add(cone);
  return grp;
}

// Build a single body (rounded cube + its energised-edge north arrows) for the
// given excitation state. `state` = { config, axis, roll }.
function buildBody(state) {
  const body = new THREE.Group();

  // Solid rounded-cube body + crisp edge wireframe for definition.
  const cubeGeo = new RoundedBoxGeometry(HALF * 2, HALF * 2, HALF * 2, SEG, RR);
  const cubeMesh = new THREE.Mesh(cubeGeo, new THREE.MeshStandardMaterial({
    color: OU_COLOR, roughness: 0.55, metalness: 0.15, side: THREE.FrontSide,
  }));
  body.add(cubeMesh);
  body.userData.cube = cubeMesh;   // kept for the debug selection tint
  body.add(new THREE.LineSegments(
    new THREE.EdgesGeometry(cubeGeo),
    new THREE.LineBasicMaterial({ color: 0x0d1117, transparent: true, opacity: 0.4 }),
  ));

  // Power/polarity for this box: magnitude scales arrow size; sign flips north.
  const drive = levelToDrive(state.level ?? 1);
  const sizeF = 0.45 + 0.55 * drive.currentScale;

  // North arrows for every energised edge, with the orientation rotation applied.
  const weights = MOTION_CONFIGS[state.config] ?? {};
  const R = orientationMatrix(state.axis, state.roll);

  // Field-sampling metadata: which config's B grid, the canonical→oriented
  // rotation baked into the arrows, and the linear current×polarity scale.
  body.userData.config = state.config ?? "face";
  body.userData.orientQuat = new THREE.Quaternion().setFromRotationMatrix(R);
  body.userData.fieldScale = drive.currentScale * drive.polarity;
  for (const [edge, w] of Object.entries(weights)) {
    if (!w) continue;
    const [ca, cb] = EDGE_CORNERS[edge];
    const A = cornerVec(ca).applyMatrix4(R);   // canonical +polarity (north) corner
    const B = cornerVec(cb).applyMatrix4(R);
    // Effective north sign = config sign × box polarity.
    const north = (w > 0 ? 1 : -1) * drive.polarity;
    body.add(north > 0 ? buildEdgeArrow(B, A, sizeF) : buildEdgeArrow(A, B, sizeF));
  }
  return body;
}

function disposeGroup(grp) {
  grp.traverse(o => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) {
      if (Array.isArray(o.material)) o.material.forEach(m => m.dispose());
      else o.material.dispose();
    }
  });
}

// ── Stage: holds N bodies, each at a fixed offset. Repositioning / rotation of
//    the bodies themselves is intentionally NOT exposed yet. ───────────────────
const _HILITE = new THREE.Color(1.0, 0.55, 0.1);   // debug selection tint (orange)

export class MotionStage {
  constructor(scene) {
    this._scene = scene;
    this.group = new THREE.Group();
    this.group.visible = false;
    scene.add(this.group);
    this._bodies = [];
    // Per-body flag: once a body has been hand-placed (debug drag), its
    // position/orientation survives rebuilds triggered by the config/power UI.
    this._moved = [];
  }

  get bodies() { return this._bodies; }

  // states = [{ config, axis, roll, offset:[x,y,z] }, ...]
  setBodies(states) {
    // Snapshot existing transforms so hand-placed bodies keep their pose when
    // a dropdown/slider change forces a rebuild.
    const prev = this._bodies.map(b => ({ p: b.position.clone(), q: b.quaternion.clone() }));
    for (const b of this._bodies) { this.group.remove(b); disposeGroup(b); }
    this._bodies = [];
    states.forEach((st, i) => {
      const body = buildBody(st);
      if (this._moved[i] && prev[i]) {
        body.position.copy(prev[i].p);
        body.quaternion.copy(prev[i].q);
      } else {
        const o = st.offset ?? [0, 0, 0];
        body.position.set(o[0], o[1], o[2]);
      }
      this.group.add(body);
      this._bodies.push(body);
    });
  }

  // Debug selection tint: glow the cube body emissive so the picked module reads.
  highlight(body, on) {
    const mesh = body?.userData?.cube;
    if (!mesh?.material) return;
    if (on) {
      mesh.material.emissive.copy(_HILITE);
      mesh.material.emissiveIntensity = 0.55;
    } else {
      mesh.material.emissive.setRGB(0, 0, 0);
      mesh.material.emissiveIntensity = 1;
    }
  }

  // Mark a body as hand-placed so its pose persists across rebuilds.
  markMoved(i) { if (i >= 0) this._moved[i] = true; }

  // Field-sampling descriptors for the physics engine. qTot maps a vector in
  // the cube's canonical (solver) frame to world: drag rotation ∘ axis/roll.
  bodyDescriptors() {
    const I = new THREE.Quaternion();
    return this._bodies.map(b => {
      const u = b.userData;
      const qTot = b.quaternion.clone().multiply(u.orientQuat ?? I);
      return {
        config: u.config ?? "face",
        scale:  u.fieldScale ?? 1,
        pos:    b.position.clone(),
        qTot,
        qInv:   qTot.clone().invert(),
      };
    });
  }

  setVisible(v) { this.group.visible = !!v; }

  dispose() {
    for (const b of this._bodies) { this.group.remove(b); disposeGroup(b); }
    this._bodies = [];
    this._scene.remove(this.group);
  }
}

// Default placement: two cubes offset along X, a comfortable gap apart.
export const MOTION_OFFSET = 2.6;
