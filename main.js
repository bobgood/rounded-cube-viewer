import * as THREE from "three";
import { OrbitControls }      from "three/examples/jsm/controls/OrbitControls.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

import { CONFIG } from "./config.js";

// ─── Scene / camera / renderer ────────────────────────────────────────────────
const container = document.getElementById("app");
const viewport  = document.getElementById("viewport");

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);

const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1000);
camera.position.set(6, 4, 7);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type    = THREE.PCFSoftShadowMap;
container.appendChild(renderer.domElement);

function resizeViewport() {
  if (!viewport) return;
  const w = viewport.clientWidth;
  const h = viewport.clientHeight;
  if (w < 1 || h < 1) return;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}
function scheduleResize() {
  resizeViewport();
  requestAnimationFrame(resizeViewport);
}
scheduleResize();
if (viewport && typeof ResizeObserver !== "undefined") {
  new ResizeObserver(scheduleResize).observe(viewport);
}
window.addEventListener("resize", scheduleResize);
window.addEventListener("load", scheduleResize);

// ─── Orbit controls ───────────────────────────────────────────────────────────
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping    = true;
controls.dampingFactor    = 0.05;
controls.screenSpacePanning = true;
controls.minDistance      = 1.5;
controls.maxDistance      = 60;
controls.target.set(0, 0, 0);
controls.addEventListener("change", schedulePeelRefresh);
controls.mouseButtons = {
  LEFT:   THREE.MOUSE.ROTATE,
  MIDDLE: THREE.MOUSE.DOLLY,
  RIGHT:  THREE.MOUSE.PAN,
};

// ─── Lights ───────────────────────────────────────────────────────────────────
scene.add(new THREE.AmbientLight(0x404060, 0.6));

const key = new THREE.DirectionalLight(0xffffff, 1.1);
key.position.set(5, 8, 6);
key.castShadow = true;
key.shadow.mapSize.setScalar(2048);
key.shadow.camera.near   = 0.5;
key.shadow.camera.far    = 40;
key.shadow.camera.left   = key.shadow.camera.bottom = -12;
key.shadow.camera.right  = key.shadow.camera.top    =  12;
scene.add(key);

const fill = new THREE.DirectionalLight(0x8899ff, 0.35);
fill.position.set(-4, 2, -6);
scene.add(fill);

// ─── Ground & grid (spinning-cubes view only) ─────────────────────────────────
const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(40, 40),
  new THREE.MeshStandardMaterial({ color: 0x161b22, metalness: 0.05, roughness: 0.9 })
);
ground.rotation.x    = -Math.PI / 2;
ground.position.y    = -CONFIG.CUBE_SIZE / 2 - 0.001;
ground.receiveShadow = true;
scene.add(ground);

const grid = new THREE.GridHelper(20, 20, 0x30363d, 0x21262d);
grid.position.y = ground.position.y + 0.001;
scene.add(grid);

// ─── Spinning-cubes: texture helpers ──────────────────────────────────────────
const TEX_SIZE = 512;
const CELL     = TEX_SIZE / 3;

function powerToRGB(p) {
  if (p < 0.5) {
    const t = p * 2;
    return [Math.round(t * 150), Math.round(220 - t * 70), Math.round(t * 150)];
  }
  const t = (p - 0.5) * 2;
  return [Math.round(150 + t * 105), Math.round(150 - t * 150), Math.round(150 - t * 150)];
}

function drawCoil(ctx, cx, cy, cellSize, power) {
  const [r, g, b] = powerToRGB(power);
  const color = `rgb(${r},${g},${b})`;
  const maxR  = cellSize * 0.36;
  const lw    = cellSize * 0.066;
  const gap   = lw * 0.45;
  const rings = 4;

  const grd = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR + lw * 3);
  grd.addColorStop(0, `rgba(${r},${g},${b},0.18)`);
  grd.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grd;
  ctx.beginPath();
  ctx.arc(cx, cy, maxR + lw * 3, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "#070d14";
  ctx.beginPath();
  ctx.arc(cx, cy, maxR + lw * 1.1, 0, Math.PI * 2);
  ctx.fill();

  for (let i = 0; i < rings; i++) {
    const ringR = maxR - i * (lw + gap);
    if (ringR < lw / 2) break;
    const alpha = 0.45 + 0.55 * ((rings - i) / rings);
    ctx.strokeStyle = `rgba(${r},${g},${b},${alpha.toFixed(2)})`;
    ctx.lineWidth   = lw;
    ctx.beginPath();
    ctx.arc(cx, cy, ringR, 0, Math.PI * 2);
    ctx.stroke();
  }

  ctx.fillStyle   = color;
  ctx.shadowColor = color;
  ctx.shadowBlur  = lw * 2;
  ctx.beginPath();
  ctx.arc(cx, cy, lw * 0.75, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur  = 0;

  const fs = Math.round(cellSize * 0.11);
  ctx.fillStyle    = `rgba(${r},${g},${b},0.9)`;
  ctx.font         = `bold ${fs}px monospace`;
  ctx.textAlign    = "center";
  ctx.textBaseline = "top";
  ctx.fillText(`${Math.round(power * 100)}%`, cx, cy + maxR + lw * 1.5);
}

function drawFace(canvas, coils) {
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#0c1520";
  ctx.fillRect(0, 0, TEX_SIZE, TEX_SIZE);
  ctx.strokeStyle = "#1c2838";
  ctx.lineWidth   = 1;
  for (let i = 1; i < 3; i++) {
    ctx.beginPath(); ctx.moveTo(i * CELL, 0);       ctx.lineTo(i * CELL, TEX_SIZE); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, i * CELL);       ctx.lineTo(TEX_SIZE, i * CELL); ctx.stroke();
  }
  coils.forEach((c, idx) => {
    const p = (typeof c === "object") ? c.power : c;
    drawCoil(ctx, (idx % 3) * CELL + CELL / 2, Math.floor(idx / 3) * CELL + CELL / 2, CELL, p);
  });
}

// ─── Spinning-cubes: module meshes ────────────────────────────────────────────
const sharedGeo = new RoundedBoxGeometry(
  CONFIG.CUBE_SIZE, CONFIG.CUBE_SIZE, CONFIG.CUBE_SIZE,
  CONFIG.CUBE_SEGMENTS, CONFIG.CUBE_RADIUS
);

function createCubeModule(posX) {
  const coilData = Array.from({ length: 6 }, () =>
    Array.from({ length: 9 }, () => ({ power: Math.random() }))
  );
  const textures = Array.from({ length: 6 }, (_, fi) => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = TEX_SIZE;
    drawFace(canvas, coilData[fi]);
    const tex = new THREE.CanvasTexture(canvas);
    tex.userData.canvas = canvas;
    return tex;
  });
  const materials = textures.map(tex =>
    new THREE.MeshStandardMaterial({ map: tex, metalness: 0.08, roughness: 0.6 })
  );
  const mesh = new THREE.Mesh(sharedGeo, materials);
  mesh.castShadow = mesh.receiveShadow = true;
  mesh.position.set(posX, 0, 0);
  scene.add(mesh);
  return { mesh, coilData, textures };
}

const cubeModules = [createCubeModule(-1.2), createCubeModule(1.2)];

// ─── Voxel renderer: InstancedMesh setup ──────────────────────────────────────
const VOXEL_CAPACITY = 200_000;
const CAP_CAPACITY   = 300_000;
const PLATE_CAPACITY =  60_000;
const HS_CAPACITY    =  30_000;
const GM_CAPACITY    = 300_000;
const CU_ARROW_MAX   =  12_000;
const CV_ARROW_MAX   =  20_000;

const _voxGeo = new THREE.BoxGeometry(1, 1, 1);

const voxelMat = new THREE.MeshStandardMaterial({
  color: 0xffffff, metalness: 0.45, roughness: 0.45,
  transparent: true, opacity: 1.0,
});
const capMat = new THREE.MeshStandardMaterial({
  color: 0xffffff, metalness: 0.45, roughness: 0.45,
  transparent: true, opacity: 1.0,
});
const plateMat = new THREE.MeshStandardMaterial({
  color: 0xffffff, metalness: 0.45, roughness: 0.45,
  transparent: true, opacity: 1.0,
});
const hsMat = new THREE.MeshStandardMaterial({
  color: 0xffffff, metalness: 0.45, roughness: 0.45,
  transparent: true, opacity: 1.0,
});
const voxelMesh = new THREE.InstancedMesh(_voxGeo, voxelMat, VOXEL_CAPACITY);
const capMesh   = new THREE.InstancedMesh(_voxGeo, capMat,   CAP_CAPACITY);
const plateMesh = new THREE.InstancedMesh(_voxGeo, plateMat, PLATE_CAPACITY);
const hsMesh    = new THREE.InstancedMesh(_voxGeo, hsMat,    HS_CAPACITY);
const gmMat = new THREE.MeshStandardMaterial({
  color: 0x55cc66, metalness: 0.35, roughness: 0.5,
  transparent: true, opacity: 1.0,
});
const gmMesh    = new THREE.InstancedMesh(_voxGeo, gmMat, GM_CAPACITY);
voxelMesh.count = capMesh.count = plateMesh.count = hsMesh.count = gmMesh.count = 0;
scene.add(voxelMesh);
scene.add(capMesh);
scene.add(plateMesh);
scene.add(hsMesh);
scene.add(gmMesh);

// ─── Unified modes (one dropdown: experiments + spinning cubes) ───────────────
const MODE_OPTIONS = [
  { id: "cylinder:ngmesh",    view: "cylinder",       scene: "ngmesh",    label: "NGSolve mesh (rod + coil)" },
  { id: "cylinder:frame",     view: "cylinder",       scene: "frame",     label: "30 coils experiment" },
  { id: "cylinder:dipole",    view: "cylinder",       scene: "dipole",    label: "Dipole (e12 rod + coil)" },
  { id: "cylinder:12dipoles", view: "cylinder",       scene: "12dipoles", label: "12 dipoles (all edges)" },
  { id: "spinning_cubes",     view: "spinning_cubes", scene: null,        label: "Spinning cubes" },
];

// ─── View state (opacity sliders; 0 = hidden) ─────────────────────────────────
let _currentView = "cylinder";
let _activeScene = "frame";
let _hasVoxelScene = false;
let _partsOpacity = 0.5;
let _metalOpacity = 0.0;
let _currentOpacity = 0.85;
let _currentDebugOpacity = 0.0;

let _cylObjects   = [];
let _capObjects   = [];
let _plateObjects = [];
let _hsObjects    = [];
let _cuObjects    = [];
let _cuSendTimer  = null;
let _coilWeights  = null;
let _feaRunning   = false;
let _cuFieldBase  = null;
let _cvFieldBase  = null;
let _cuArrowMesh  = null;
let _cvArrowMesh  = null;
let _cmArrowMesh  = null;
let _cmFieldBase  = null;
let _cvObjects    = [];
/** Cm: copper grid J arrows (debug; default off). */
const CM_ARROW_MAX = 50_000;
const _cmDebugCol = new THREE.Color(0.95, 0.72, 0.15);
let _ouGroup      = null;
let _ouOpacity    = 0.35;
let _sceneVoxelSize = 0.05;
/** Slightly >1 so box faces overlap (removes grid-line gaps, esp. with transparency). */
const VOXEL_FILL = 1.03;
let _peelCamDist = 0;
let _peelRaf = 0;
const _camWorld = new THREE.Vector3();
const _posCache = { cyl: null, cap: null, pl: null, hs: null, gm: null };

const _cuUp   = new THREE.Vector3(0, 1, 0);
const _cuDir  = new THREE.Vector3();
const _cuCol  = new THREE.Color();
const _cuQuat   = new THREE.Quaternion();

// ─── Fill InstancedMesh from position array ───────────────────────────────────
const _dummy = new THREE.Object3D();

function fillInstanced(imesh, positions, vs, minDistFromCam = 0) {
  const cap = imesh.instanceMatrix.count;
  const scale = vs * VOXEL_FILL;
  let j = 0;
  if (minDistFromCam > 0) {
    camera.getWorldPosition(_camWorld);
    const cx = _camWorld.x;
    const cy = _camWorld.y;
    const cz = _camWorld.z;
    for (let i = 0; i < positions.length && j < cap; i++) {
      const p = positions[i];
      const dx = p[0] - cx;
      const dy = p[1] - cy;
      const dz = p[2] - cz;
      if (dx * dx + dy * dy + dz * dz < minDistFromCam * minDistFromCam) continue;
      _dummy.position.set(p[0], p[1], p[2]);
      _dummy.scale.setScalar(scale);
      _dummy.updateMatrix();
      imesh.setMatrixAt(j++, _dummy.matrix);
    }
  } else {
    const n = Math.min(positions.length, cap);
    for (let i = 0; i < n; i++) {
      _dummy.position.set(positions[i][0], positions[i][1], positions[i][2]);
      _dummy.scale.setScalar(scale);
      _dummy.updateMatrix();
      imesh.setMatrixAt(i, _dummy.matrix);
    }
    j = n;
  }
  imesh.count = j;
  imesh.instanceMatrix.needsUpdate = true;
}

function _clearInstanced(imesh) {
  imesh.count = 0;
  imesh.instanceMatrix.needsUpdate = true;
}

function refreshVoxelMeshes() {
  const vs = _sceneVoxelSize;
  const peel = _peelCamDist;
  if (_posCache.cyl) fillInstanced(voxelMesh, _posCache.cyl, vs, peel);
  else _clearInstanced(voxelMesh);
  if (_posCache.cap) fillInstanced(capMesh, _posCache.cap, vs, peel);
  else _clearInstanced(capMesh);
  if (_posCache.pl) fillInstanced(plateMesh, _posCache.pl, vs, peel);
  else _clearInstanced(plateMesh);
  if (_posCache.hs) fillInstanced(hsMesh, _posCache.hs, vs, peel);
  else _clearInstanced(hsMesh);
  if (_posCache.gm) fillInstanced(gmMesh, _posCache.gm, vs, peel);
  else _clearInstanced(gmMesh);
}

function schedulePeelRefresh() {
  if (_peelCamDist <= 0) return;
  if (_peelRaf) return;
  _peelRaf = requestAnimationFrame(() => {
    _peelRaf = 0;
    refreshVoxelMeshes();
  });
}

// ─── Cu / Cv FEA fields: instanced arrow glyphs ─────────────────────────────
function _disposeArrowMesh(mesh) {
  if (!mesh) return;
  scene.remove(mesh);
  mesh.geometry.dispose();
  mesh.material.dispose();
}

// Shared Cu/Cv palette: sign → hue, |weight| → intensity (keeps chroma, not grey).
const _coilColPos = new THREE.Color(1.0, 0.72, 0.12);
const _coilColNeg = new THREE.Color(0.35, 0.88, 1.0);
const COIL_INTENSITY_FLOOR = 0.32;

function _setCoilPalette(posRgb, negRgb) {
  if (posRgb) _coilColPos.setRGB(posRgb[0], posRgb[1], posRgb[2]);
  if (negRgb) _coilColNeg.setRGB(negRgb[0], negRgb[1], negRgb[2]);
}

function _coilArrowColor(a) {
  const t = Math.min(1, Math.abs(a));
  const inten = COIL_INTENSITY_FLOOR + (1 - COIL_INTENSITY_FLOOR) * t;
  _cuCol.copy(a >= 0 ? _coilColPos : _coilColNeg).multiplyScalar(inten);
  return _cuCol;
}

function _applyCurrentArrows(field, vs, maxCount, renderOrder, logTag, feaScale = 1.0) {
  if (!field?.sites?.positions?.length) return null;

  const pos = field.sites.positions;
  const dir = field.sites.directions;
  const amp = field.sites.amplitudes;
  const scale = _feaRunning ? feaScale : 1.0;
  const n   = Math.min(pos.length, dir.length, amp.length, maxCount);
  _setCoilPalette(field.color_positive, field.color_negative);

  const baseLen = Math.max(0.18, vs * 4.0);
  const baseRad = baseLen * 0.28;
  const geo = new THREE.ConeGeometry(baseRad, baseLen, 8);
  geo.translate(0, baseLen * 0.5, 0);
  const mat = new THREE.MeshBasicMaterial({
    toneMapped: false,
    transparent: true,
    opacity: _currentOpacity,
    depthTest: false,
    depthWrite: false,
  });
  const mesh = new THREE.InstancedMesh(geo, mat, n);
  mesh.frustumCulled = false;
  mesh.renderOrder = renderOrder;

  let count = 0;
  for (let i = 0; i < n; i++) {
    _cuDir.set(dir[i][0], dir[i][1], dir[i][2]);
    if (_cuDir.lengthSq() < 1e-8) continue;
    _cuDir.normalize();

    _dummy.position.set(pos[i][0], pos[i][1], pos[i][2]);
    _cuQuat.setFromUnitVectors(_cuUp, _cuDir);
    if (Number.isNaN(_cuQuat.x)) {
      _dummy.quaternion.setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
    } else {
      _dummy.quaternion.copy(_cuQuat);
    }

    const a   = amp[i] * scale;
    const mag = Math.min(1, Math.abs(a));
    const s   = 0.55 + 0.45 * mag;
    _dummy.scale.set(s, s, s);
    _dummy.updateMatrix();
    mesh.setMatrixAt(count, _dummy.matrix);
    mesh.setColorAt(count, _coilArrowColor(a));
    count++;
  }
  mesh.count = count;
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  scene.add(mesh);
  console.info(`[${logTag}] ${count} current arrows`);
  return mesh;
}

function clearCuArrows() {
  _disposeArrowMesh(_cuArrowMesh);
  _cuArrowMesh = null;
}

function clearCvArrows() {
  _disposeArrowMesh(_cvArrowMesh);
  _cvArrowMesh = null;
}

/** Instanced cones on fea_grid coil cells (Cu + Cv); direction from J (uniform debug color). */
function _applyCmGridArrows(coil, vs) {
  if (!coil?.positions?.length || !coil?.J?.length) return null;

  const pos = coil.positions;
  const J   = coil.J;
  const n   = Math.min(pos.length, J.length, CM_ARROW_MAX);

  const baseLen = Math.max(vs * 3.5, 0.14);
  const baseRad = baseLen * 0.24;
  const geo = new THREE.ConeGeometry(baseRad, baseLen, 6);
  geo.translate(0, baseLen * 0.5, 0);
  const mat = new THREE.MeshBasicMaterial({
    toneMapped: false,
    transparent: true,
    opacity: _currentDebugOpacity,
    depthTest: true,
    depthWrite: false,
  });
  const mesh = new THREE.InstancedMesh(geo, mat, n);
  mesh.frustumCulled = false;
  mesh.renderOrder = 12;

  let count = 0;
  for (let i = 0; i < n; i++) {
    const jx = J[i][0];
    const jy = J[i][1];
    const jz = J[i][2];
    const mag = Math.hypot(jx, jy, jz);
    if (mag < 1e-8) continue;
    _cuDir.set(jx / mag, jy / mag, jz / mag);

    _dummy.position.set(pos[i][0], pos[i][1], pos[i][2]);
    _cuQuat.setFromUnitVectors(_cuUp, _cuDir);
    if (Number.isNaN(_cuQuat.x)) {
      _dummy.quaternion.setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
    } else {
      _dummy.quaternion.copy(_cuQuat);
    }

    const s = 0.5 + 0.25 * Math.min(1, mag / 1.5);
    _dummy.scale.set(s, s, s);
    _dummy.updateMatrix();
    mesh.setMatrixAt(count, _dummy.matrix);
    mesh.setColorAt(count, _cmDebugCol);
    count++;
  }
  mesh.count = count;
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  scene.add(mesh);
  if (count < n) {
    console.warn(`[Cm] showing ${count.toLocaleString()} / ${n.toLocaleString()} (raise CM_ARROW_MAX)`);
  } else {
    console.info(`[Cm] ${count.toLocaleString()} coil-grid J arrows (Cu + Cv)`);
  }
  return mesh;
}

function clearCmArrows() {
  _disposeArrowMesh(_cmArrowMesh);
  _cmArrowMesh = null;
}

function clearCmField() {
  clearCmArrows();
  _cmFieldBase = null;
}

function rebuildCmArrows(vs) {
  clearCmArrows();
  if (!_cmFieldBase) return;
  _cmArrowMesh = _applyCmGridArrows(_cmFieldBase, vs);
  updateCmVisibility();
}

function updateCmVisibility() {
  if (!_cmArrowMesh) return;
  const show = _currentView === "cylinder" && _currentDebugOpacity > 0.001;
  _cmArrowMesh.visible = show;
  if (_cmArrowMesh.material) _cmArrowMesh.material.opacity = _currentDebugOpacity;
}

function _cloneCoilField(field) {
  if (!field?.sites) return null;
  return {
    ...field,
    sites: {
      positions: field.sites.positions,
      directions: field.sites.directions,
      amplitudes: field.sites.amplitudes?.slice() ?? [],
    },
  };
}

function refreshCoilArrows(vs = _sceneVoxelSize) {
  if (_cuFieldBase) applyCuField(_cuFieldBase, vs);
  if (_cvFieldBase) applyCvField(_cvFieldBase, vs);
}

function applyCuField(cu, vs, feaScale = 1.0) {
  clearCuArrows();
  if (!cu?.sites?.positions?.length) {
    _cuObjects = [];
    console.warn("[Cu] no sites — restart python -u server.py");
    return;
  }
  _cuArrowMesh = _applyCurrentArrows(cu, vs, CU_ARROW_MAX, 50, "Cu", feaScale);
  _cuObjects = cu.objects ?? [];
}

function applyCvField(cv, vs, feaScale = 1.0) {
  clearCvArrows();
  if (!cv?.sites?.positions?.length) {
    _cvObjects = [];
    console.warn("[Cv] no sites — restart python -u server.py");
    return;
  }
  _cvArrowMesh = _applyCurrentArrows(cv, vs, CV_ARROW_MAX, 51, "Cv", feaScale);
  _cvObjects = cv.objects ?? [];
}

// ─── Cube envelope outline (Ou only; Ho removed) ────────────────────────────────
function buildOuOutline(fc) {
  if (_ouGroup) { scene.remove(_ouGroup); _ouGroup = null; }

  const sc = fc.mm_to_scene;
  const ew = fc.edge_mm        * sc;
  const eh = fc.height_mm      * sc;
  const rr = fc.ou_rounding_mm * sc;
  const [or, og, ob] = fc.ou_color;

  _ouGroup = new THREE.Group();
  const ouGeo = new RoundedBoxGeometry(ew, eh, ew, 4, rr);
  const ouSolid = new THREE.Mesh(ouGeo, new THREE.MeshStandardMaterial({
    color: new THREE.Color(or, og, ob),
    transparent: true,
    opacity: 0.08,
    side: THREE.BackSide,
    depthWrite: false,
  }));
  const ouWire = new THREE.LineSegments(
    new THREE.EdgesGeometry(ouGeo),
    new THREE.LineBasicMaterial({
      color: new THREE.Color(or, og, ob),
      transparent: true,
      opacity: 0.6,
      depthWrite: false,
    }),
  );
  _ouGroup.add(ouSolid);
  _ouGroup.add(ouWire);
  _ouGroup.userData.ouSolid = ouSolid;
  _ouGroup.userData.ouWire  = ouWire;
  scene.add(_ouGroup);
  applyOuOpacityFromSlider();
}

function applyOuOpacityFromSlider() {
  if (!_ouGroup) return;
  const show = _currentView === "cylinder" && _ouOpacity > 0.001;
  _ouGroup.visible = show;
  const solidOp = _ouOpacity * 0.12;
  const wireOp  = Math.min(1, _ouOpacity * 1.4);
  if (_ouGroup.userData.ouSolid?.material) {
    _ouGroup.userData.ouSolid.material.opacity = solidOp;
  }
  if (_ouGroup.userData.ouWire?.material) {
    _ouGroup.userData.ouWire.material.opacity = wireOp;
  }
}

// ─── View visibility (opacity-driven) ─────────────────────────────────────────
function applyView() {
  const isCyl = _currentView === "cylinder";
  const parts = _partsOpacity > 0.001;
  voxelMesh.visible  = isCyl && parts && voxelMesh.count > 0;
  capMesh.visible    = isCyl && parts && capMesh.count > 0;
  plateMesh.visible  = isCyl && parts && plateMesh.count > 0;
  hsMesh.visible     = isCyl && parts && hsMesh.count > 0;
  gmMesh.visible     = isCyl && _metalOpacity > 0.001 && gmMesh.count > 0;
  if (_cuArrowMesh) {
    const show = isCyl && _currentOpacity > 0.001;
    _cuArrowMesh.visible = show;
    if (_cuArrowMesh.material) _cuArrowMesh.material.opacity = _currentOpacity;
  }
  if (_cvArrowMesh) {
    const show = isCyl && _currentOpacity > 0.001;
    _cvArrowMesh.visible = show;
    if (_cvArrowMesh.material) _cvArrowMesh.material.opacity = _currentOpacity;
  }
  updateCmVisibility();
  applyBlineVisibility();
  applyGridOpacity();
  applyOuOpacityFromSlider();

  const isSpin = _currentView === "spinning_cubes";
  cubeModules.forEach(m => { m.mesh.visible = isSpin; });
  ground.visible = isSpin;
  grid.visible   = isSpin;
}

// ─── Apply voxel scene from Python ────────────────────────────────────────────
function applyVoxelScene(data) {
  clearNgMesh();
  _hasVoxelScene = true;
  const vs = data.voxel_size;
  _sceneVoxelSize = vs;

  _posCache.cyl = data.cylinders.positions;
  _posCache.cap = data.caps.positions;
  _posCache.pl  = data.plates?.positions ?? null;
  _posCache.hs  = data.hs?.positions ?? null;
  _posCache.gm  = data.fea_grid?.metal?.positions ?? null;

  const cc = data.cylinders.color;
  voxelMat.color.setRGB(cc[0], cc[1], cc[2]);
  _cylObjects = data.cylinders.objects;

  const cc2 = data.caps.color;
  capMat.color.setRGB(cc2[0], cc2[1], cc2[2]);
  _capObjects = data.caps.objects;

  if (data.plates) {
    const pc = data.plates.color;
    plateMat.color.setRGB(pc[0], pc[1], pc[2]);
    _plateObjects = data.plates.objects;
  } else {
    _plateObjects = [];
  }

  if (data.hs) {
    const hc = data.hs.color;
    hsMat.color.setRGB(hc[0], hc[1], hc[2]);
    _hsObjects = data.hs.objects;
  } else {
    _hsObjects = [];
  }

  if (data.fea_grid?.metal?.positions?.length) {
    const gc = data.fea_grid.color ?? [0.35, 0.85, 0.45];
    gmMat.color.setRGB(gc[0], gc[1], gc[2]);
  }

  refreshVoxelMeshes();

  if (data.fea_grid?.metal?.cell_count) {
    if (gmMesh.count < data.fea_grid.metal.cell_count) {
      console.warn(
        `[Gm] showing ${gmMesh.count.toLocaleString()} / ${data.fea_grid.metal.cell_count.toLocaleString()} union cells (raise GM_CAPACITY)`
      );
    } else if (_posCache.gm) {
      console.info(
        `[Gm] ${gmMesh.count.toLocaleString()} union metal cells (raw ${data.fea_grid.metal.sources?.raw_total?.toLocaleString() ?? "?"})`
      );
    }
  }

  _coilWeights = data.coil?.weights ?? data.frame_config?.coil_weights ?? null;
  _setCoilPalette(data.coil?.color_positive, data.coil?.color_negative);
  _feaRunning = false;

  if (data.cu) {
    _cuFieldBase = _cloneCoilField(data.cu);
    applyCuField(data.cu, vs);
  } else {
    _cuFieldBase = null;
    clearCuArrows();
  }

  if (data.cv) {
    _cvFieldBase = _cloneCoilField(data.cv);
    applyCvField(data.cv, vs);
  } else {
    _cvFieldBase = null;
    clearCvArrows();
  }

  const coilCells = data.fea_grid?.cells?.coil ?? data.fea_grid?.cells?.copper;
  if (coilCells?.positions?.length && coilCells.J?.length) {
    _cmFieldBase = {
      positions: coilCells.positions,
      J: coilCells.J,
      weight: coilCells.weight ?? [],
      color_positive: data.cu?.color_positive ?? data.coil?.color_positive,
      color_negative: data.cu?.color_negative ?? data.coil?.color_negative,
    };
    if (_currentDebugOpacity > 0.001) rebuildCmArrows(vs);
  } else {
    clearCmField();
  }

  _activeScene = data.scene_id ?? "frame";
  _cubeCorners = data.frame_config?.cube_corners ?? null;
  syncModeSelectFromState();

  if (data.frame_config) buildOuOutline(data.frame_config);
  applyView();
  applyOpacityFromSlider();
  applyMetalOpacityFromSlider();
  applyCurrentOpacityFromSlider();
  applyCurrentDebugOpacityFromSlider();
  scheduleResize();

  const status = document.getElementById("solve-status");
  if (status && _currentView === "cylinder") {
    const n = voxelMesh.count + capMesh.count;
    status.textContent = n > 0 ? `${n.toLocaleString()} voxels · ${_activeScene}` : "";
    status.style.color = "#8b949e";
  }
}

// ─── Apply spinning-cubes frame from Python ───────────────────────────────────
function applyFrame(data) {
  if (!data.cubes) return;
  data.cubes.forEach((c, i) => {
    if (i >= cubeModules.length) return;
    const m = cubeModules[i];
    m.mesh.position.fromArray(c.pos);
    m.mesh.quaternion.fromArray(c.quat);   // [qx, qy, qz, qw]
    if (c.coils) {
      c.coils.forEach((faceCoils, fi) => {
        faceCoils.forEach((p, ci) => {
          m.coilData[fi][ci].power = (p + 1) / 2;  // remap [-1,1] -> [0,1]
        });
      });
    }
  });
}

// ─── B-field lines ──────────────────────────────────────────────────────────
let _blineGroup = null;
const _blineColorLo = new THREE.Color(0.20, 0.55, 1.00);  // weak  |B| (blue)
const _blineColorHi = new THREE.Color(1.00, 0.45, 0.15);  // strong |B| (orange)

function clearBlines() {
  if (!_blineGroup) return;
  scene.remove(_blineGroup);
  _blineGroup.traverse(o => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) o.material.dispose();
  });
  _blineGroup = null;
}

function _blineOpacity() {
  return parseFloat(document.getElementById("bline-opacity-slider")?.value ?? 0.9);
}

function applyBfieldLines(data) {
  clearBlines();
  const lines = data.lines ?? [];
  const op = _blineOpacity();
  _blineGroup = new THREE.Group();
  const _c = new THREE.Color();

  for (const poly of lines) {
    if (!poly || poly.length < 2) continue;
    const n = poly.length;
    const pos = new Float32Array(n * 3);
    const col = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const p = poly[i];
      pos[i * 3] = p[0]; pos[i * 3 + 1] = p[1]; pos[i * 3 + 2] = p[2];
      // colour by field strength |B| (p[3] in [0,1]); sqrt lifts weak-field detail
      const b = p.length > 3 ? Math.sqrt(Math.min(1, Math.max(0, p[3]))) : 0.5;
      _c.copy(_blineColorLo).lerp(_blineColorHi, b);
      col[i * 3] = _c.r; col[i * 3 + 1] = _c.g; col[i * 3 + 2] = _c.b;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    const mat = new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: op,
      depthWrite: false,
    });
    _blineGroup.add(new THREE.Line(geo, mat));
  }
  scene.add(_blineGroup);
  applyBlineVisibility();

  const meta = data.meta ?? {};
  const status = document.getElementById("solve-status");
  if (status) {
    const maxB = meta.max_B_T != null ? meta.max_B_T.toExponential(2) : "?";
    const mu = meta.mu_r != null ? ` · μ=${Math.round(meta.mu_r)}` : "";
    const scene = _activeScene ? ` · ${_activeScene}` : "";
    status.textContent = `${meta.n_lines ?? lines.length} lines · max|B|=${maxB} T${mu}${scene}`;
    status.style.color = "#3fb950";
  }
  const btn = document.getElementById("solve-btn");
  if (btn) { btn.disabled = false; }
}

function applyBfieldStatus(data) {
  const status = document.getElementById("solve-status");
  const btn = document.getElementById("solve-btn");
  if (data.state === "solving") {
    if (status) { status.textContent = "Solving B field…"; status.style.color = "#d29922"; }
    if (btn) btn.disabled = true;
  } else if (data.state === "error") {
    if (status) { status.textContent = `Error: ${data.message ?? "solve failed"}`; status.style.color = "#f85149"; }
    if (btn) btn.disabled = false;
  }
}

function applyBlineVisibility() {
  if (!_blineGroup) return;
  const op = _blineOpacity();
  _blineGroup.visible = _currentView === "cylinder" && op > 0.001;
  _blineGroup.traverse(o => { if (o.material) o.material.opacity = op; });
}

// ─── NGSolve / Netgen surface mesh (fea_mesh payload) ──────────────────────────
let _ngMeshGroup = null;

function clearNgMesh() {
  if (!_ngMeshGroup) return;
  scene.remove(_ngMeshGroup);
  _ngMeshGroup.traverse(o => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) o.material.dispose();
  });
  _ngMeshGroup = null;
}

function applyFeaMesh(data) {
  clearNgMesh();
  // Switching to the mesh scene: clear voxel + arrow state so only the mesh shows.
  _posCache.cyl = _posCache.cap = _posCache.pl = _posCache.hs = _posCache.gm = null;
  refreshVoxelMeshes();
  clearCuArrows();
  clearCvArrows();
  clearCmField();
  clearBlines();

  const verts = data.vertices ?? [];
  _ngMeshGroup = new THREE.Group();

  if (verts.length) {
    const flat = new Float32Array(verts.length * 3);
    for (let i = 0; i < verts.length; i++) {
      flat[i * 3] = verts[i][0];
      flat[i * 3 + 1] = verts[i][1];
      flat[i * 3 + 2] = verts[i][2];
    }
    const posAttr = new THREE.BufferAttribute(flat, 3);

    for (const region of data.regions ?? []) {
      const tris = region.triangles ?? [];
      if (!tris.length) continue;
      const idx = new Uint32Array(tris.length * 3);
      for (let i = 0; i < tris.length; i++) {
        idx[i * 3] = tris[i][0];
        idx[i * 3 + 1] = tris[i][1];
        idx[i * 3 + 2] = tris[i][2];
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", posAttr);
      geo.setIndex(new THREE.BufferAttribute(idx, 1));
      geo.computeVertexNormals();

      const [r, g, b] = region.color ?? [0.8, 0.82, 0.85];
      const col = new THREE.Color(r, g, b);
      const solidOp = region.solid_opacity ?? 0.18;
      const wireOp = region.wire_opacity ?? 0.75;

      const solidMat = new THREE.MeshStandardMaterial({
        color: col, metalness: 0.2, roughness: 0.7,
        transparent: true, opacity: solidOp,
        side: THREE.DoubleSide, depthWrite: false,
      });
      solidMat.userData.baseOpacity = solidOp;
      const wireMat = new THREE.LineBasicMaterial({
        color: col, transparent: true, opacity: wireOp, depthWrite: false,
      });
      wireMat.userData.baseOpacity = wireOp;
      _ngMeshGroup.add(new THREE.Mesh(geo, solidMat));
      _ngMeshGroup.add(new THREE.LineSegments(new THREE.WireframeGeometry(geo), wireMat));
    }
  }
  scene.add(_ngMeshGroup);

  // Mesh defaults to visible: nudge the (shared) grid slider up if it's at zero.
  const gridSl = document.getElementById("metal-opacity-slider");
  if (gridSl && parseFloat(gridSl.value) < 0.001) {
    gridSl.value = "1";
    _metalOpacity = 1.0;
    const gv = document.getElementById("metal-opacity-val");
    if (gv) gv.textContent = "1.00";
  }

  _hasVoxelScene = true;            // prevent applyMode from re-requesting the scene
  _activeScene = data.scene_id ?? "ngmesh";
  _cubeCorners = data.frame_config?.cube_corners ?? null;
  if (data.frame_config) buildOuOutline(data.frame_config);
  syncModeSelectFromState();
  applyView();
  scheduleResize();

  const meta = data.meta ?? {};
  const status = document.getElementById("solve-status");
  if (status && _currentView === "cylinder") {
    if (meta.error) {
      status.textContent = `Mesh error: ${meta.error}`;
      status.style.color = "#f85149";
    } else {
      status.textContent =
        `${(meta.n_tris ?? 0).toLocaleString()} tris · ${(meta.n_points ?? 0).toLocaleString()} pts · maxh ${meta.maxh_mm}mm`;
      status.style.color = "#3fb950";
    }
  }
}

function applyGridOpacity() {
  if (!_ngMeshGroup) return;
  const g = _metalOpacity;
  _ngMeshGroup.visible = _currentView === "cylinder" && g > 0.001;
  _ngMeshGroup.traverse(o => {
    const base = o.material?.userData?.baseOpacity;
    if (base != null) o.material.opacity = base * g;
  });
}

// ─── WebSocket client ──────────────────────────────────────────────────────────
let _ws = null;

const _BLINE_MU_MAX = 5000;
function _blineMu() {
  const t = parseFloat(document.getElementById("bline-mu-slider")?.value ?? 0);
  return Math.max(1, Math.round(Math.pow(_BLINE_MU_MAX, t)));  // log: t=0 -> 1, t=1 -> 5000
}

// Strength slider is logarithmic: t in [0,1] maps to a current scale in
// [_STRENGTH_MIN, _STRENGTH_MAX], with the centre (t=0.5) landing on 1.0x.
const _STRENGTH_MIN = 0.1, _STRENGTH_MAX = 10;
function _strength() {
  const t = parseFloat(document.getElementById("strength-slider")?.value ?? 0.5);
  return _STRENGTH_MIN * Math.pow(_STRENGTH_MAX / _STRENGTH_MIN, t);
}
function _fmtStrength(s) { return s >= 1 ? s.toFixed(2) : s.toFixed(3); }

function sendSolveBfield() {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  const strength = _strength();
  const mu_r = _blineMu();
  const saturate = document.getElementById("sat-checkbox")?.checked ?? true;
  const btn = document.getElementById("solve-btn");
  if (btn) btn.disabled = true;
  const status = document.getElementById("solve-status");
  if (status) {
    status.textContent = `Solving B field (μ=${mu_r}, ${strength.toFixed(2)}×${saturate ? ", sat" : ""})…`;
    status.style.color = "#d29922";
  }
  _ws.send(JSON.stringify({ type: "solve_bfield", strength, mu_r, saturate }));
}

function sendUIState() {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  const spin     = parseFloat(document.getElementById("spin-slider")?.value     ?? 0.8);
  const damping  = parseFloat(document.getElementById("damp-slider")?.value     ?? 0.985);
  const strength = _strength();
  _ws.send(JSON.stringify({ type: "ui_state", spin, damping, strength }));
  if (_feaRunning) refreshCoilArrows(_sceneVoxelSize);
}

function sendFeaStart() {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  const strength = _strength();
  _feaRunning = true;
  _ws.send(JSON.stringify({ type: "fea_start", strength }));
}

function sendView(view) {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  _ws.send(JSON.stringify({ type: "view", view }));
}

function sendScene(sceneId) {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  clearBlines();
  // Scene geometry uses coil_init weights as-is; Strength slider applies via fea_start only.
  _ws.send(JSON.stringify({ type: "scene", scene: sceneId }));
}

function currentModeId() {
  if (_currentView === "spinning_cubes") return "spinning_cubes";
  return `cylinder:${_activeScene}`;
}

function syncModeSelectFromState() {
  const sel = document.getElementById("mode-select");
  if (!sel) return;
  const id = currentModeId();
  if (sel.value !== id) sel.value = id;
  updateControlSections();
}

function updateModeOptionLabels(scenes) {
  const sel = document.getElementById("mode-select");
  if (!sel || !scenes?.length) return;
  for (const s of scenes) {
    const opt = sel.querySelector(`option[value="cylinder:${s.id}"]`);
    if (opt) opt.textContent = s.label;
  }
}

function updateControlSections() {
  const cyl = _currentView === "cylinder";
  document.getElementById("cylinder-controls")?.classList.toggle("hidden", !cyl);
  document.getElementById("spin-controls")?.classList.toggle("hidden", cyl);
  const hint = document.getElementById("hint");
  if (hint) hint.style.display = cyl ? "" : "none";
  const hi = document.getElementById("hover-info");
  if (hi && !cyl) hi.textContent = "";
}

function setLoadStatus(msg) {
  const status = document.getElementById("solve-status");
  if (!status || _currentView !== "cylinder") return;
  status.textContent = msg;
  status.style.color = "#d29922";
}

function applyMode(modeId) {
  const mode = MODE_OPTIONS.find(m => m.id === modeId) ?? MODE_OPTIONS[0];
  const prevView  = _currentView;
  const prevScene = _activeScene;

  if (mode.view === "spinning_cubes") {
    _currentView = "spinning_cubes";
    sendView("spinning_cubes");
    applyView();
    updateControlSections();
    syncModeSelectFromState();
    return;
  }

  _currentView = "cylinder";
  const scene = mode.scene ?? "frame";
  const sceneChanged = scene !== prevScene;

  // Always ask server for voxel geometry (fixes connect when server still on spinning_cubes).
  sendView("cylinder");
  if (sceneChanged) {
    _activeScene = scene;
    _hasVoxelScene = false;
    setLoadStatus("Loading scene…");
    sendScene(scene);
  } else if (!_hasVoxelScene) {
    setLoadStatus("Loading scene…");
    sendScene(scene);
  }

  applyView();
  updateControlSections();
  syncModeSelectFromState();
  scheduleResize();
}

function connectWS() {
  _ws = new WebSocket("ws://localhost:8765");
  _ws.addEventListener("open", () => {
    sendUIState();
    applyMode(document.getElementById("mode-select")?.value ?? currentModeId());
  });
  _ws.addEventListener("message", e => {
    const data = JSON.parse(e.data);
    if      (data.type === "voxel_scene")   applyVoxelScene(data);
    else if (data.type === "fea_mesh")      applyFeaMesh(data);
    else if (data.type === "scene_list") {
      updateModeOptionLabels(data.scenes ?? []);
      if (data.active) {
        _activeScene = data.active;
        syncModeSelectFromState();
      }
    }
    else if (data.type === "frame")         applyFrame(data);
    else if (data.type === "bfield_lines")  applyBfieldLines(data);
    else if (data.type === "bfield_status") applyBfieldStatus(data);
  });
  _ws.addEventListener("close", () => setTimeout(connectWS, 2000));
}

connectWS();

// ─── Hover: nearest face → nearest corner (c1–c8) ─────────────────────────────
const _raycaster = new THREE.Raycaster();
const _mouse     = new THREE.Vector2();
const _hoverPt   = new THREE.Vector3();
const _facePlane = new THREE.Plane();
// Must match geometry_ids.FACE_CLOCKWISE (+Z, -Z, +X, -X, +Y, -Y)
const _FACE_CORNERS = [
  [1, 2, 3, 4], [5, 6, 7, 8], [1, 2, 6, 5], [3, 4, 8, 7], [1, 4, 8, 5], [3, 2, 7, 6],
];
// Distinct temp vectors (no aliasing!)
const _qa = new THREE.Vector3();
const _qb = new THREE.Vector3();
const _qc = new THREE.Vector3();
const _qd = new THREE.Vector3();
const _qn = new THREE.Vector3();
const _qe1 = new THREE.Vector3();
const _qe2 = new THREE.Vector3();
const _qcp = new THREE.Vector3();
let _cubeCorners = null;

function _hasCorners() {
  return !!(_cubeCorners && _cubeCorners["1"]);
}

function _setPointerNdc(clientX, clientY) {
  const el = viewport ?? renderer.domElement;
  const rect = el.getBoundingClientRect();
  const w = rect.width || 1;
  const h = rect.height || 1;
  _mouse.x = ((clientX - rect.left) / w) * 2 - 1;
  _mouse.y = -((clientY - rect.top) / h) * 2 + 1;
}

/** Nearest of all 8 corners to a 3D point on the cube surface (robust for any rotation). */
function _cornerFromPoint(pt) {
  if (!_hasCorners()) return "";
  let bestC = 0;
  let bestD = Infinity;
  for (let id = 1; id <= 8; id++) {
    const p = _cubeCorners[String(id)];
    if (!p) continue;
    const dx = pt.x - p[0];
    const dy = pt.y - p[1];
    const dz = pt.z - p[2];
    const d = dx * dx + dy * dy + dz * dz;
    if (d < bestD) { bestD = d; bestC = id; }
  }
  return bestC ? `c${bestC}` : "";
}

function _edgeInside(p, q, pt, n) {
  _qe1.subVectors(q, p);
  _qe2.subVectors(pt, p);
  _qcp.crossVectors(_qe1, _qe2);
  return _qcp.dot(n) >= -1e-5;
}

function _pointInQuad(pt, a, b, c, d, n) {
  return _edgeInside(a, b, pt, n) && _edgeInside(b, c, pt, n) &&
         _edgeInside(c, d, pt, n) && _edgeInside(d, a, pt, n);
}

/** Front-most cube-face plane hit (used when the ray misses voxel geometry). */
function _raycastCubePoint(ray) {
  if (!_hasCorners()) return null;
  let bestT = Infinity;
  let bestPt = null;
  for (const ids of _FACE_CORNERS) {
    if (!_cubeCorners[String(ids[0])]) continue;
    _qa.fromArray(_cubeCorners[String(ids[0])]);
    _qb.fromArray(_cubeCorners[String(ids[1])]);
    _qc.fromArray(_cubeCorners[String(ids[2])]);
    _qd.fromArray(_cubeCorners[String(ids[3])]);
    _qe1.subVectors(_qb, _qa);
    _qe2.subVectors(_qc, _qa);
    _qn.crossVectors(_qe1, _qe2).normalize();
    _facePlane.setFromNormalAndCoplanarPoint(_qn, _qa);
    const hit = ray.intersectPlane(_facePlane, _hoverPt);
    if (!hit) continue;
    const t = hit.distanceTo(ray.origin);
    if (t >= bestT) continue;
    if (!_pointInQuad(hit, _qa, _qb, _qc, _qd, _qn)) continue;
    bestT = t;
    bestPt = hit.clone();
  }
  return bestPt;
}

window.addEventListener("mousemove", e => {
  const hi = document.getElementById("hover-info");
  if (!hi || _currentView !== "cylinder" || !_hasCorners()) {
    if (hi) hi.textContent = "";
    return;
  }
  _setPointerNdc(e.clientX, e.clientY);
  _raycaster.setFromCamera(_mouse, camera);
  const meshes = [voxelMesh, capMesh, plateMesh, hsMesh, gmMesh]
    .filter(m => m.visible && m.count > 0);
  let pt = null;
  if (meshes.length) {
    const hits = _raycaster.intersectObjects(meshes, false);
    if (hits.length) pt = hits[0].point;
  }
  if (!pt) pt = _raycastCubePoint(_raycaster.ray);
  hi.textContent = pt ? _cornerFromPoint(pt) : "";
});

// ─── UI controls ──────────────────────────────────────────────────────────────
function bindSlider(id, valId, decimals, cb) {
  const sl  = document.getElementById(id);
  const val = document.getElementById(valId);
  if (!sl) return;
  sl.addEventListener("input", () => {
    const v = parseFloat(sl.value);
    if (val) val.textContent = v.toFixed(decimals);
    cb(v);
  });
}

bindSlider("spin-slider",     "spin-val",     1, () => sendUIState());
bindSlider("damp-slider",     "damp-val",     3, () => sendUIState());
const _strengthSlider = document.getElementById("strength-slider");
if (_strengthSlider) {
  const showStrength = () => {
    const val = document.getElementById("strength-val");
    if (val) val.textContent = _fmtStrength(_strength());
  };
  _strengthSlider.addEventListener("input", () => {
    showStrength();
    sendUIState();
    sendFeaStart();
  });
  showStrength();
}

const _opSlider = document.getElementById("opacity-slider");
const _metalOpSlider = document.getElementById("metal-opacity-slider");

function applyOpacityFromSlider() {
  if (!_opSlider) return;
  _partsOpacity = parseFloat(_opSlider.value);
  const opV = document.getElementById("opacity-val");
  if (opV) opV.textContent = _partsOpacity.toFixed(2);
  voxelMat.opacity  = _partsOpacity;
  capMat.opacity    = _partsOpacity;
  plateMat.opacity  = _partsOpacity;
  hsMat.opacity     = _partsOpacity;
  applyView();
}

function applyMetalOpacityFromSlider() {
  if (!_metalOpSlider) return;
  _metalOpacity = parseFloat(_metalOpSlider.value);
  const opV = document.getElementById("metal-opacity-val");
  if (opV) opV.textContent = _metalOpacity.toFixed(2);
  gmMat.opacity = _metalOpacity;
  applyGridOpacity();
  applyView();
}

function applyCurrentOpacityFromSlider() {
  const sl = document.getElementById("current-opacity-slider");
  if (!sl) return;
  _currentOpacity = parseFloat(sl.value);
  const opV = document.getElementById("current-opacity-val");
  if (opV) opV.textContent = _currentOpacity.toFixed(2);
  applyView();
}

function applyCurrentDebugOpacityFromSlider() {
  const sl = document.getElementById("current-debug-opacity-slider");
  if (!sl) return;
  _currentDebugOpacity = parseFloat(sl.value);
  const opV = document.getElementById("current-debug-opacity-val");
  if (opV) opV.textContent = _currentDebugOpacity.toFixed(2);
  if (_currentDebugOpacity > 0.001 && _cmFieldBase && !_cmArrowMesh) {
    rebuildCmArrows(_sceneVoxelSize);
  }
  applyView();
}

const _ouOpSlider = document.getElementById("ou-opacity-slider");
function applyOuOpacitySliderUi() {
  if (!_ouOpSlider) return;
  _ouOpacity = parseFloat(_ouOpSlider.value);
  const opV = document.getElementById("ou-opacity-val");
  if (opV) opV.textContent = _ouOpacity.toFixed(2);
  applyOuOpacityFromSlider();
}
if (_ouOpSlider) {
  _ouOpSlider.addEventListener("input", applyOuOpacitySliderUi);
  applyOuOpacitySliderUi();
}

if (_opSlider) {
  _opSlider.addEventListener("input", applyOpacityFromSlider);
  applyOpacityFromSlider();
}
if (_metalOpSlider) {
  _metalOpSlider.addEventListener("input", applyMetalOpacityFromSlider);
  applyMetalOpacityFromSlider();
}
const _curOpSlider = document.getElementById("current-opacity-slider");
if (_curOpSlider) {
  _curOpSlider.addEventListener("input", applyCurrentOpacityFromSlider);
  applyCurrentOpacityFromSlider();
}
const _curDbgSlider = document.getElementById("current-debug-opacity-slider");
if (_curDbgSlider) {
  _curDbgSlider.addEventListener("input", applyCurrentDebugOpacityFromSlider);
  applyCurrentDebugOpacityFromSlider();
}

const _peelSlider = document.getElementById("peel-slider");
function applyPeelFromSlider() {
  if (!_peelSlider) return;
  _peelCamDist = parseFloat(_peelSlider.value);
  const peelV = document.getElementById("peel-val");
  if (peelV) peelV.textContent = _peelCamDist.toFixed(2);
  refreshVoxelMeshes();
}
if (_peelSlider) {
  _peelSlider.addEventListener("input", applyPeelFromSlider);
  applyPeelFromSlider();
}

const _modeSelect = document.getElementById("mode-select");
if (_modeSelect) {
  _modeSelect.addEventListener("change", () => applyMode(_modeSelect.value));
}
updateControlSections();

document.getElementById("restart-btn")?.addEventListener("click", () => {
  sendUIState();
  sendFeaStart();
});
document.getElementById("solve-btn")?.addEventListener("click", () => sendSolveBfield());

const _blineSlider = document.getElementById("bline-opacity-slider");
if (_blineSlider) {
  _blineSlider.addEventListener("input", () => {
    const v = parseFloat(_blineSlider.value);
    const val = document.getElementById("bline-opacity-val");
    if (val) val.textContent = v.toFixed(2);
    applyBlineVisibility();
  });
}

const _blineMuSlider = document.getElementById("bline-mu-slider");
if (_blineMuSlider) {
  const showMu = () => {
    const val = document.getElementById("bline-mu-val");
    if (val) val.textContent = String(_blineMu());
  };
  _blineMuSlider.addEventListener("input", showMu);
  showMu();
}

// ─── Coil texture updates (spinning-cubes view) ───────────────────────────────
let _lastTexUpdate = 0;
function maybeRedrawTextures(now) {
  if (_currentView !== "spinning_cubes") return;
  if (now - _lastTexUpdate < 50) return;
  _lastTexUpdate = now;
  for (const { coilData, textures } of cubeModules) {
    for (let fi = 0; fi < 6; fi++) {
      drawFace(textures[fi].userData.canvas, coilData[fi]);
      textures[fi].needsUpdate = true;
    }
  }
}

// ─── Render loop ──────────────────────────────────────────────────────────────
function tick(now) {
  requestAnimationFrame(tick);
  maybeRedrawTextures(now);
  controls.update();
  updateCmVisibility();
  renderer.render(scene, camera);
}
tick(performance.now());
