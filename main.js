import * as THREE from "three";
import { OrbitControls }      from "three/examples/jsm/controls/OrbitControls.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

import { CONFIG } from "./config.js";

// ─── Scene / camera / renderer ────────────────────────────────────────────────
const container = document.getElementById("app");

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);

const camera = new THREE.PerspectiveCamera(
  50, window.innerWidth / window.innerHeight, 0.1, 1000
);
camera.position.set(6, 4, 7);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type    = THREE.PCFSoftShadowMap;
container.appendChild(renderer.domElement);

// ─── Orbit controls ───────────────────────────────────────────────────────────
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping    = true;
controls.dampingFactor    = 0.05;
controls.screenSpacePanning = true;
controls.minDistance      = 1.5;
controls.maxDistance      = 60;
controls.target.set(0, 0, 0);
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
voxelMesh.count = capMesh.count = plateMesh.count = hsMesh.count = 0;
scene.add(voxelMesh);
scene.add(capMesh);
scene.add(plateMesh);
scene.add(hsMesh);

// ─── View state ────────────────────────────────────────────────────────────────
let _currentView = "cylinder";
let _cyEnabled   = true;
let _caEnabled   = true;
let _plEnabled   = true;
let _hsEnabled   = true;
let _cuEnabled   = true;
let _cvEnabled   = true;
let _ouEnabled   = false;
let _hoEnabled   = false;

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
let _cvObjects    = [];
let _ouGroup      = null;
let _hoGroup      = null;
let _sceneVoxelSize = 0.05;

const _cuUp   = new THREE.Vector3(0, 1, 0);
const _cuDir  = new THREE.Vector3();
const _cuCol  = new THREE.Color();
const _cuQuat   = new THREE.Quaternion();

// ─── Fill InstancedMesh from position array ───────────────────────────────────
const _dummy = new THREE.Object3D();

function fillInstanced(imesh, positions, vs) {
  const n = Math.min(positions.length, imesh.instanceMatrix.count);
  for (let i = 0; i < n; i++) {
    _dummy.position.set(positions[i][0], positions[i][1], positions[i][2]);
    _dummy.scale.setScalar(vs);
    _dummy.updateMatrix();
    imesh.setMatrixAt(i, _dummy.matrix);
  }
  imesh.count = n;
  imesh.instanceMatrix.needsUpdate = true;
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
    transparent: false,
    opacity: 1,
    depthTest: true,
    depthWrite: true,
  });
  mat.userData.ignoreOpacity = true;
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

// ─── Build Ou / Ho Three.js display objects ───────────────────────────────────
function buildOuHo(fc) {
  if (_ouGroup) { scene.remove(_ouGroup); _ouGroup = null; }
  if (_hoGroup) { scene.remove(_hoGroup); _hoGroup = null; }

  const sc = fc.mm_to_scene;
  const ew = fc.edge_mm        * sc;
  const eh = fc.height_mm      * sc;
  const rr = fc.ou_rounding_mm * sc;
  const [or, og, ob] = fc.ou_color;
  const [hr, hg, hb] = fc.ho_color;
  const hd = fc.hole_diameter_mm * sc;

  // Ou: translucent rounded box + wireframe edges
  _ouGroup = new THREE.Group();
  const ouGeo   = new RoundedBoxGeometry(ew, eh, ew, 4, rr);
  const ouSolid = new THREE.Mesh(ouGeo, new THREE.MeshStandardMaterial({
    color: new THREE.Color(or, og, ob),
    transparent: true, opacity: 0.08,
    side: THREE.BackSide,
  }));
  _ouGroup.add(ouSolid);
  _ouGroup.add(new THREE.LineSegments(
    new THREE.EdgesGeometry(ouGeo),
    new THREE.LineBasicMaterial({
      color: new THREE.Color(or, og, ob), transparent: true, opacity: 0.6,
    })
  ));
  _ouGroup.userData.ouSolid = ouSolid;
  scene.add(_ouGroup);

  // Ho: 3 crossing cylinders (subtraction tools) — same visual style as Ou
  const hoColor = new THREE.Color(hr, hg, hb);
  const hoSolidMat = new THREE.MeshStandardMaterial({
    color: hoColor, transparent: true, opacity: 0.08,
    side: THREE.BackSide,
  });
  const hoWireMat = new THREE.LineBasicMaterial({
    color: hoColor, transparent: true, opacity: 0.6,
  });
  _hoGroup = new THREE.Group();
  const addHoCyl = (rx, ry, rz, len) => {
    const geo = new THREE.CylinderGeometry(hd / 2, hd / 2, len, 32);
    const solid = new THREE.Mesh(geo, hoSolidMat);
    solid.rotation.set(rx, ry, rz);
    _hoGroup.add(solid);
    const wire = new THREE.LineSegments(new THREE.EdgesGeometry(geo), hoWireMat);
    wire.rotation.set(rx, ry, rz);
    _hoGroup.add(wire);
  };
  addHoCyl(0,           0, Math.PI / 2, ew);  // X axis
  addHoCyl(0,           0, 0,           eh);  // Y axis
  addHoCyl(Math.PI / 2, 0, 0,           ew);  // Z axis
  _hoGroup.userData.hoSolidMat = hoSolidMat;
  _hoGroup.userData.hoWireMat  = hoWireMat;
  scene.add(_hoGroup);
}

// ─── Checklist ────────────────────────────────────────────────────────────────
function _appendChecklistItems(rowEl, items) {
  if (!rowEl) return;
  for (const item of items) {
    const div = document.createElement("div");
    div.className = "cl-item";
    const cb = document.createElement("input");
    cb.type    = "checkbox";
    cb.checked = item.get();
    cb.addEventListener("change", () => item.set(cb.checked));
    const lbl = document.createElement("label");
    lbl.textContent = item.label;
    div.appendChild(cb);
    div.appendChild(lbl);
    rowEl.appendChild(div);
  }
}

function buildChecklist(hasPlates, hasHs, hasCu, hasCv, hasOuHo) {
  const row1 = document.getElementById("scene-checklist-row1");
  const row2 = document.getElementById("scene-checklist-row2");
  if (!row1 || !row2) return;
  row1.innerHTML = "";
  row2.innerHTML = "";

  const line1 = [
    { label: "Cy", get: () => _cyEnabled, set: v => { _cyEnabled = v; applyView(); } },
    { label: "Ca", get: () => _caEnabled, set: v => { _caEnabled = v; applyView(); } },
  ];
  if (hasPlates) {
    line1.push({ label: "Pl", get: () => _plEnabled, set: v => { _plEnabled = v; applyView(); } });
  }
  if (hasHs) {
    line1.push({ label: "Hs", get: () => _hsEnabled, set: v => { _hsEnabled = v; applyView(); } });
  }

  const line2 = [];
  if (hasCu) {
    line2.push({ label: "Cu", get: () => _cuEnabled, set: v => { _cuEnabled = v; applyView(); } });
  }
  if (hasCv) {
    line2.push({ label: "Cv", get: () => _cvEnabled, set: v => { _cvEnabled = v; applyView(); } });
  }
  if (hasOuHo) {
    line2.push(
      { label: "Ou", get: () => _ouEnabled, set: v => { _ouEnabled = v; applyView(); } },
      { label: "Ho", get: () => _hoEnabled, set: v => { _hoEnabled = v; applyView(); } },
    );
  }

  _appendChecklistItems(row1, line1);
  _appendChecklistItems(row2, line2);
}

// ─── View visibility ──────────────────────────────────────────────────────────
function applyView() {
  const isCyl = _currentView === "cylinder";
  voxelMesh.visible = isCyl && _cyEnabled;
  capMesh.visible   = isCyl && _caEnabled;
  plateMesh.visible = isCyl && _plEnabled;
  hsMesh.visible    = isCyl && _hsEnabled;
  if (_cuArrowMesh) _cuArrowMesh.visible = isCyl && _cuEnabled;
  if (_cvArrowMesh) _cvArrowMesh.visible = isCyl && _cvEnabled;
  if (_ouGroup) _ouGroup.visible = isCyl && _ouEnabled;
  if (_hoGroup) _hoGroup.visible = isCyl && _hoEnabled;

  const isSpin = _currentView === "spinning_cubes";
  cubeModules.forEach(m => { m.mesh.visible = isSpin; });
  ground.visible = isSpin;
  grid.visible   = isSpin;
}

// ─── Apply voxel scene from Python ────────────────────────────────────────────
function applyVoxelScene(data) {
  const vs = data.voxel_size;
  _sceneVoxelSize = vs;

  const cc = data.cylinders.color;
  voxelMat.color.setRGB(cc[0], cc[1], cc[2]);
  fillInstanced(voxelMesh, data.cylinders.positions, vs);
  _cylObjects = data.cylinders.objects;

  const cc2 = data.caps.color;
  capMat.color.setRGB(cc2[0], cc2[1], cc2[2]);
  fillInstanced(capMesh, data.caps.positions, vs);
  _capObjects = data.caps.objects;

  if (data.plates) {
    const pc = data.plates.color;
    plateMat.color.setRGB(pc[0], pc[1], pc[2]);
    fillInstanced(plateMesh, data.plates.positions, vs);
    _plateObjects = data.plates.objects;
  } else {
    plateMesh.count = 0;
    plateMesh.instanceMatrix.needsUpdate = true;
    _plateObjects = [];
  }

  if (data.hs) {
    const hc = data.hs.color;
    hsMat.color.setRGB(hc[0], hc[1], hc[2]);
    fillInstanced(hsMesh, data.hs.positions, vs);
    _hsObjects = data.hs.objects;
  } else {
    hsMesh.count = 0;
    hsMesh.instanceMatrix.needsUpdate = true;
    _hsObjects = [];
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

  _cubeCorners = data.frame_config?.cube_corners ?? null;
  _buildPickAnchors(data);

  if (data.frame_config) buildOuHo(data.frame_config);
  buildChecklist(!!data.plates, !!data.hs, !!data.cu, !!data.cv, !!data.frame_config);
  applyView();
  applyOpacityFromSlider();
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

// ─── WebSocket client ──────────────────────────────────────────────────────────
let _ws = null;

function sendUIState() {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  const spin     = parseFloat(document.getElementById("spin-slider")?.value     ?? 0.8);
  const damping  = parseFloat(document.getElementById("damp-slider")?.value     ?? 0.985);
  const strength = parseFloat(document.getElementById("strength-slider")?.value ?? 0.4);
  _ws.send(JSON.stringify({ type: "ui_state", spin, damping, strength }));
  if (_feaRunning) refreshCoilArrows(_sceneVoxelSize);
}

function sendFeaStart() {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  const strength = parseFloat(document.getElementById("strength-slider")?.value ?? 0.4);
  _feaRunning = true;
  _ws.send(JSON.stringify({ type: "fea_start", strength }));
}

function sendView(view) {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  _ws.send(JSON.stringify({ type: "view", view }));
}

function connectWS() {
  _ws = new WebSocket("ws://localhost:8765");
  _ws.addEventListener("open", () => {
    sendUIState(false);
    sendView(_currentView);
  });
  _ws.addEventListener("message", e => {
    const data = JSON.parse(e.data);
    if      (data.type === "voxel_scene") applyVoxelScene(data);
    else if (data.type === "frame")       applyFrame(data);
  });
  _ws.addEventListener("close", () => setTimeout(connectWS, 2000));
}

connectWS();

// ─── Hover detection ──────────────────────────────────────────────────────────
const _raycaster = new THREE.Raycaster();
const _mouse     = new THREE.Vector2();
const _mouseBase = new THREE.Vector2();
const _edgeEndA  = new THREE.Vector3();
const _edgeEndB  = new THREE.Vector3();
const _pickCent  = new THREE.Vector3();
const _pickScr   = new THREE.Vector3();
const _RAY_JITTER = [
  [0, 0], [-0.004, 0], [0.004, 0], [0, -0.004], [0, 0.004],
  [-0.003, -0.003], [0.003, 0.003],
];
let   _lastHover = 0;
let   _cubeCorners = null;
let   _pickAnchors = [];

function _findObject(objects, instanceId) {
  for (const obj of objects) {
    if (instanceId >= obj.start && instanceId < obj.start + obj.count) return obj;
  }
  return null;
}

function _objectsForMesh(mesh) {
  if (mesh === capMesh) return _capObjects;
  if (mesh === voxelMesh) return _cylObjects;
  if (mesh === hsMesh) return _hsObjects;
  if (mesh === plateMesh) return _plateObjects;
  if (mesh === _cuArrowMesh) return _cuObjects;
  if (mesh === _cvArrowMesh) return _cvObjects;
  return null;
}

function _centroidFromRange(positions, start, count) {
  _pickCent.set(0, 0, 0);
  const end = Math.min(start + count, positions.length);
  let n = 0;
  for (let i = start; i < end; i++) {
    _pickCent.x += positions[i][0];
    _pickCent.y += positions[i][1];
    _pickCent.z += positions[i][2];
    n++;
  }
  if (n) _pickCent.divideScalar(n);
  return _pickCent.clone();
}

function _buildPickAnchors(data) {
  _pickAnchors = [];
  const vs = data.voxel_size ?? _sceneVoxelSize;
  const add = (positions, objects, mesh, radiusMul) => {
    if (!positions?.length || !objects?.length) return;
    const r = Math.max(vs * radiusMul, 0.35);
    for (const obj of objects) {
      _pickAnchors.push({
        mesh,
        obj,
        center: _centroidFromRange(positions, obj.start, obj.count),
        radius: r,
      });
    }
  };
  add(data.cylinders?.positions, data.cylinders?.objects, voxelMesh, 18);
  add(data.caps?.positions, data.caps?.objects, capMesh, 20);
  add(data.hs?.positions, data.hs?.objects, hsMesh, 22);
  add(data.plates?.positions, data.plates?.objects, plateMesh, 16);
}

function _cornerLabel(obj) {
  if (obj.corner != null) return `C${obj.corner}`;
  const m = /^C?(\d+)$/.exec(obj.label ?? "");
  return m ? `C${m[1]}` : obj.label;
}

function _cornerWorld(cornerId) {
  const p = _cubeCorners?.[String(cornerId)];
  if (!p) return null;
  _edgeEndA.fromArray(p);
  return _edgeEndA;
}

/** Face id with closest corner first: F1234 → F2341 when corner 2 is nearest. */
function _faceLabelFromPoint(faceStr, hitPoint) {
  const ids = [...faceStr].map(ch => parseInt(ch, 10));
  if (ids.length !== 4 || ids.some(n => Number.isNaN(n))) return `F${faceStr}`;
  let bestI = 0;
  let bestD = Infinity;
  for (let i = 0; i < ids.length; i++) {
    const w = _cornerWorld(ids[i]);
    if (!w) continue;
    const d = hitPoint.distanceToSquared(w);
    if (d < bestD) {
      bestD = d;
      bestI = i;
    }
  }
  const rot = ids.slice(bestI).concat(ids.slice(0, bestI));
  return `F${rot.join("")}`;
}

/** Closest corner first → E12 vs E21 for two coils per edge. */
function _directedEdgeLabel(obj, hitPoint) {
  if (!obj.corners || obj.corners.length !== 2 || !obj.ends || obj.ends.length !== 2) {
    return obj.label;
  }
  const [c1, c2] = obj.corners;
  _edgeEndA.fromArray(obj.ends[0]);
  _edgeEndB.fromArray(obj.ends[1]);
  const d1 = hitPoint.distanceToSquared(_edgeEndA);
  const d2 = hitPoint.distanceToSquared(_edgeEndB);
  return d1 <= d2 ? `E${c1}${c2}` : `E${c2}${c1}`;
}

function _hoverLabel(mesh, obj, hitPoint) {
  if (mesh === capMesh) return _cornerLabel(obj);
  if (mesh === _cvArrowMesh) return obj.edge ?? obj.label;
  if (mesh === voxelMesh && obj.corners) return _directedEdgeLabel(obj, hitPoint);
  if (mesh === plateMesh || mesh === hsMesh) {
    const face = obj.face ?? (obj.label?.match(/^F(\d{4})$/)?.[1]);
    if (face) return _faceLabelFromPoint(face, hitPoint);
  }
  if (obj.label?.match(/^F\d{4}/)) {
    const face = obj.label.slice(1, 5);
    return _faceLabelFromPoint(face, hitPoint);
  }
  return obj.label;
}

function _frontVisibleHit(hits) {
  if (!hits.length) return null;
  const front = hits[0];
  if (front.object !== _cuArrowMesh && front.object !== _cvArrowMesh) return front;
  const slack = Math.max(_sceneVoxelSize * 2, 0.04);
  for (let i = 1; i < hits.length; i++) {
    const h = hits[i];
    if (h.object === _cuArrowMesh || h.object === _cvArrowMesh) continue;
    if (h.distance <= front.distance + slack) return h;
    break;
  }
  return front;
}

function _gatherVoxelHits(meshes, baseX, baseY) {
  const all = [];
  for (const [dx, dy] of _RAY_JITTER) {
    _mouse.set(baseX + dx, baseY + dy);
    _raycaster.setFromCamera(_mouse, camera);
    all.push(..._raycaster.intersectObjects(meshes, false));
  }
  all.sort((a, b) => a.distance - b.distance);
  return all;
}

function _rayParamAndPerp(center, ray) {
  _pickScr.copy(center).sub(ray.origin);
  const t = _pickScr.dot(ray.direction);
  if (t < 0) return { t: -1, perp: Infinity };
  _edgeEndB.copy(ray.direction).multiplyScalar(t);
  const perp = _pickScr.sub(_edgeEndB).length();
  return { t, perp };
}

/** Front-most anchor along ray (visible layers only); used when voxels are missed. */
function _anchorPick(ray, mousePxX, mousePxY) {
  let best = null;
  let bestT = Infinity;
  const pxLim = 32;
  for (const a of _pickAnchors) {
    if (!a.mesh?.visible || a.mesh.count === 0) continue;
    const { t, perp } = _rayParamAndPerp(a.center, ray);
    if (t < 0 || t >= bestT || perp > a.radius) continue;
    _pickScr.copy(a.center).project(camera);
    const sx = (_pickScr.x * 0.5 + 0.5) * window.innerWidth;
    const sy = (-_pickScr.y * 0.5 + 0.5) * window.innerHeight;
    const dx = sx - mousePxX;
    const dy = sy - mousePxY;
    if (dx * dx + dy * dy > pxLim * pxLim) continue;
    bestT = t;
    best = a;
  }
  return best;
}

window.addEventListener("mousemove", e => {
  const now = performance.now();
  if (now - _lastHover < 32) return;
  _lastHover = now;

  const hi = document.getElementById("hover-info");
  if (!hi) return;

  _mouseBase.x = (e.clientX / window.innerWidth) * 2 - 1;
  _mouseBase.y = -(e.clientY / window.innerHeight) * 2 + 1;

  const meshes = [capMesh, voxelMesh, hsMesh, plateMesh, _cuArrowMesh, _cvArrowMesh]
    .filter(m => m && m.visible && m.count > 0);

  if (!meshes.length) {
    hi.textContent = "";
    return;
  }

  const hits = _gatherVoxelHits(meshes, _mouseBase.x, _mouseBase.y);
  let mesh = null;
  let obj = null;
  let hitPoint = null;

  const pick = _frontVisibleHit(hits);
  if (pick) {
    mesh = pick.object;
    hitPoint = pick.point;
    const objects = _objectsForMesh(mesh);
    obj = objects ? _findObject(objects, pick.instanceId) : null;
  }

  if (!obj) {
    _mouse.copy(_mouseBase);
    _raycaster.setFromCamera(_mouse, camera);
    const anchor = _anchorPick(_raycaster.ray, e.clientX, e.clientY);
    if (anchor) {
      mesh = anchor.mesh;
      obj = anchor.obj;
      hitPoint = anchor.center;
    }
  }

  hi.textContent = obj && mesh ? _hoverLabel(mesh, obj, hitPoint) : "";
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

bindSlider("spin-slider",     "spin-val",     1, () => sendUIState(false));
bindSlider("damp-slider",     "damp-val",     3, () => sendUIState(false));
bindSlider("strength-slider", "strength-val", 2, () => sendUIState());

const _opSlider = document.getElementById("opacity-slider");
function applyOpacityFromSlider() {
  if (!_opSlider) return;
  const op  = parseFloat(_opSlider.value);
  const opV = document.getElementById("opacity-val");
  if (opV) opV.textContent = op.toFixed(2);
  voxelMat.opacity  = op;
  capMat.opacity    = op;
  plateMat.opacity  = op;
  hsMat.opacity     = op;
  // Cu/Cv arrows: always full brightness (not affected by opacity slider)
  if (_ouGroup?.userData.ouSolid)
    _ouGroup.userData.ouSolid.material.opacity = Math.max(0.02, op * 0.08);
  if (_hoGroup?.userData.hoSolidMat)
    _hoGroup.userData.hoSolidMat.opacity = Math.max(0.02, op * 0.08);
  if (_hoGroup?.userData.hoWireMat)
    _hoGroup.userData.hoWireMat.opacity = Math.max(0.02, op * 0.6);
}
if (_opSlider) {
  _opSlider.addEventListener("input", applyOpacityFromSlider);
  applyOpacityFromSlider();
}

const _viewSelect = document.getElementById("view-select");
if (_viewSelect) {
  _viewSelect.addEventListener("change", () => {
    _currentView = _viewSelect.value;
    sendView(_currentView);
    applyView();
  });
}

document.getElementById("restart-btn")?.addEventListener("click", () => sendUIState(false));

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

// ─── Resize ───────────────────────────────────────────────────────────────────
window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ─── Render loop ──────────────────────────────────────────────────────────────
function tick(now) {
  requestAnimationFrame(tick);
  maybeRedrawTextures(now);
  controls.update();
  renderer.render(scene, camera);
}
tick(performance.now());
