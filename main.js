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

const voxelMesh = new THREE.InstancedMesh(_voxGeo, voxelMat, VOXEL_CAPACITY);
const capMesh   = new THREE.InstancedMesh(_voxGeo, capMat,   CAP_CAPACITY);
const plateMesh = new THREE.InstancedMesh(_voxGeo, plateMat, PLATE_CAPACITY);
voxelMesh.count = capMesh.count = plateMesh.count = 0;
scene.add(voxelMesh);
scene.add(capMesh);
scene.add(plateMesh);

// ─── View state ────────────────────────────────────────────────────────────────
let _currentView = "cylinder";
let _cyEnabled   = true;
let _caEnabled   = true;
let _plEnabled   = true;
let _ouEnabled   = true;
let _hoEnabled   = true;

let _cylObjects   = [];
let _capObjects   = [];
let _plateObjects = [];
let _ouGroup      = null;
let _hoGroup      = null;

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

  // Ho: 3 crossing cylinders
  _hoGroup = new THREE.Group();
  const hoMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color(hr, hg, hb), transparent: true, opacity: 0.3,
  });
  const mkHoCyl = (rx, ry, rz, len) => {
    const m = new THREE.Mesh(
      new THREE.CylinderGeometry(hd / 2, hd / 2, len, 32), hoMat
    );
    m.rotation.set(rx, ry, rz);
    return m;
  };
  _hoGroup.add(mkHoCyl(0,           0, Math.PI / 2, ew));  // X axis
  _hoGroup.add(mkHoCyl(0,           0, 0,           eh));  // Y axis
  _hoGroup.add(mkHoCyl(Math.PI / 2, 0, 0,           ew));  // Z axis
  _hoGroup.userData.hoMat = hoMat;
  scene.add(_hoGroup);
}

// ─── Checklist ────────────────────────────────────────────────────────────────
function buildChecklist(hasPlates, hasOuHo) {
  const cl = document.getElementById("scene-checklist");
  if (!cl) return;
  cl.innerHTML = "";

  const items = [
    { label: "Cy", get: () => _cyEnabled, set: v => { _cyEnabled = v; applyView(); } },
    { label: "Ca", get: () => _caEnabled, set: v => { _caEnabled = v; applyView(); } },
  ];
  if (hasPlates) items.push(
    { label: "Pl", get: () => _plEnabled, set: v => { _plEnabled = v; applyView(); } }
  );
  if (hasOuHo) items.push(
    { label: "Ou", get: () => _ouEnabled, set: v => { _ouEnabled = v; applyView(); } },
    { label: "Ho", get: () => _hoEnabled, set: v => { _hoEnabled = v; applyView(); } }
  );

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
    cl.appendChild(div);
  }
}

// ─── View visibility ──────────────────────────────────────────────────────────
function applyView() {
  const isCyl = _currentView === "cylinder";
  voxelMesh.visible = isCyl && _cyEnabled;
  capMesh.visible   = isCyl && _caEnabled;
  plateMesh.visible = isCyl && _plEnabled;
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

  if (data.frame_config) buildOuHo(data.frame_config);
  buildChecklist(!!data.plates, !!data.frame_config);
  applyView();
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
}

function sendView(view) {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  _ws.send(JSON.stringify({ type: "view", view }));
}

function connectWS() {
  _ws = new WebSocket("ws://localhost:8765");
  _ws.addEventListener("open", () => {
    sendUIState();
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
let   _lastHover = 0;

function _findObject(objects, instanceId) {
  for (const obj of objects) {
    if (instanceId >= obj.start && instanceId < obj.start + obj.count) return obj;
  }
  return null;
}

window.addEventListener("mousemove", e => {
  const now = performance.now();
  if (now - _lastHover < 50) return;   // ~20 fps throttle
  _lastHover = now;

  const hi = document.getElementById("hover-info");
  if (!hi) return;

  _mouse.x =  (e.clientX / window.innerWidth)  * 2 - 1;
  _mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
  _raycaster.setFromCamera(_mouse, camera);

  const pairs = [
    [voxelMesh, _cylObjects],
    [capMesh,   _capObjects],
    [plateMesh, _plateObjects],
  ].filter(([m]) => m.visible && m.count > 0);

  for (const [mesh, objects] of pairs) {
    const hits = _raycaster.intersectObject(mesh);
    if (hits.length > 0) {
      const obj = _findObject(objects, hits[0].instanceId);
      if (obj) { hi.textContent = obj.label; return; }
    }
  }
  hi.textContent = "";
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
bindSlider("strength-slider", "strength-val", 2, () => sendUIState());

const _opSlider = document.getElementById("opacity-slider");
if (_opSlider) {
  _opSlider.addEventListener("input", () => {
    const op  = parseFloat(_opSlider.value);
    const opV = document.getElementById("opacity-val");
    if (opV) opV.textContent = op.toFixed(2);
    voxelMat.opacity  = op;
    capMat.opacity    = op;
    plateMat.opacity  = op;
    if (_ouGroup?.userData.ouSolid)
      _ouGroup.userData.ouSolid.material.opacity = Math.max(0.02, op * 0.08);
    if (_hoGroup?.userData.hoMat)
      _hoGroup.userData.hoMat.opacity = Math.max(0.05, op * 0.3);
  });
}

const _viewSelect = document.getElementById("view-select");
if (_viewSelect) {
  _viewSelect.addEventListener("change", () => {
    _currentView = _viewSelect.value;
    sendView(_currentView);
    applyView();
  });
}

document.getElementById("restart-btn")?.addEventListener("click", () => sendUIState());

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
