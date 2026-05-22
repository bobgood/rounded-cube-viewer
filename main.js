import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

import { CONFIG } from "./config.js";

// ─── Scene / camera / renderer ───────────────────────────────────────────────
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
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
container.appendChild(renderer.domElement);

// ─── CAD-style orbit controls ─────────────────────────────────────────────────
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping      = true;
controls.dampingFactor      = 0.05;
controls.screenSpacePanning = true;
controls.minDistance        = 1.5;
controls.maxDistance        = 60;
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

// ─── Shared geometry ──────────────────────────────────────────────────────────
const sharedGeometry = new RoundedBoxGeometry(
  CONFIG.CUBE_SIZE, CONFIG.CUBE_SIZE, CONFIG.CUBE_SIZE,
  CONFIG.CUBE_SEGMENTS, CONFIG.CUBE_RADIUS
);

// ─── Canvas texture helpers ───────────────────────────────────────────────────
const TEX_SIZE = 512;
const CELL     = TEX_SIZE / 3;

function cubeIdFromIndex(i) {
  if (i < 26) return String.fromCharCode(97 + i);
  i -= 26;
  return String.fromCharCode(97 + Math.floor(i / 26)) + String.fromCharCode(97 + (i % 26));
}

// Power range [-1, 1]:  0 = off (dark),  +1 = red (outward),  -1 = green (inward)
function powerToRGB(p) {
  const t = Math.min(Math.abs(p), 1);
  if (p >= 0) {
    return [Math.round(30 + t * 225), Math.round(30 - t * 20),  Math.round(30 - t * 20)];
  } else {
    return [Math.round(30 - t * 20),  Math.round(30 + t * 225), Math.round(30 - t * 20)];
  }
}

function drawCoil(ctx, cx, cy, cellSize, power, id) {
  const [r, g, b] = powerToRGB(power);
  const radius = cellSize * 0.38;
  const lw     = cellSize * 0.055;

  const grd = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 1.6);
  grd.addColorStop(0, `rgba(${r},${g},${b},0.15)`);
  grd.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grd;
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 1.6, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "#070d14";
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();

  const alpha = 0.4 + 0.6 * Math.abs(power);
  ctx.strokeStyle = `rgba(${r},${g},${b},${alpha.toFixed(2)})`;
  ctx.lineWidth   = lw;
  ctx.beginPath();
  ctx.arc(cx, cy, radius - lw / 2, 0, Math.PI * 2);
  ctx.stroke();

  const fontSize = Math.round(cellSize * 0.18);
  ctx.fillStyle    = "rgba(180,190,200,0.9)";
  ctx.font         = `bold ${fontSize}px monospace`;
  ctx.textAlign    = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(id, cx, cy);
}

// Per-face canvas coordinate corrections (RoundedBoxGeometry UV × CanvasTexture flipY).
// Faces 0,1 (+X/-X): both col and row flipped → 180° rotation.
// Faces 4,5 (+Z/-Z): row flipped only.
// Faces 2,3 (+Y/-Y): no correction needed.
const FACE_COL_FLIP = [true,  true,  false, false, false, false];
const FACE_ROW_FLIP = [true,  true,  false, false, true,  true ];

function drawFace(canvas, coils, cubeId, faceIdx) {
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
    const col = idx % 3;
    const row = Math.floor(idx / 3);
    const cx = (FACE_COL_FLIP[faceIdx] ? (2 - col) : col) * CELL + CELL / 2;
    const cy = (FACE_ROW_FLIP[faceIdx] ? (2 - row) : row) * CELL + CELL / 2;
    drawCoil(ctx, cx, cy, CELL, c.power, `${cubeId}${faceIdx}${String.fromCharCode(97 + idx)}`);
  });
}

// ─── Module factory ───────────────────────────────────────────────────────────
// Modules start at the origin; Python sends position/orientation every frame.
function createModule(cubeId) {
  const coilData = Array.from({ length: 6 }, () =>
    Array.from({ length: 9 }, () => ({ power: 0 }))
  );

  const textures = Array.from({ length: 6 }, (_, fi) => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = TEX_SIZE;
    drawFace(canvas, coilData[fi], cubeId, fi);
    const tex = new THREE.CanvasTexture(canvas);
    tex.userData.canvas = canvas;
    return tex;
  });

  const mesh = new THREE.Mesh(
    sharedGeometry,
    textures.map(tex => new THREE.MeshStandardMaterial({ map: tex, metalness: 0.08, roughness: 0.6 }))
  );
  mesh.castShadow = mesh.receiveShadow = true;
  scene.add(mesh);

  return { mesh, coilData, textures, cubeId };
}

// ─── Spawn modules ────────────────────────────────────────────────────────────
const modules = [
  createModule(cubeIdFromIndex(0)),   // 'a'
  createModule(cubeIdFromIndex(1)),   // 'b'
];

// Quick lookup by cubeId
const moduleMap = Object.fromEntries(modules.map(m => [m.cubeId, m]));

// ─── Ground & grid ────────────────────────────────────────────────────────────
const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(40, 40),
  new THREE.MeshStandardMaterial({ color: 0x161b22, metalness: 0.05, roughness: 0.9 })
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -CONFIG.CUBE_SIZE / 2 - 0.001;
ground.receiveShadow = true;
scene.add(ground);

const grid = new THREE.GridHelper(20, 20, 0x30363d, 0x21262d);
grid.position.y = ground.position.y + 0.001;
scene.add(grid);

// ─── Resize ───────────────────────────────────────────────────────────────────
window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ─── Texture redraw ───────────────────────────────────────────────────────────
let lastTexUpdate = 0;
function maybeRedrawTextures(now) {
  if (now - lastTexUpdate < 33) return;
  lastTexUpdate = now;
  for (const { coilData, textures, cubeId } of modules) {
    for (let fi = 0; fi < 6; fi++) {
      drawFace(textures[fi].userData.canvas, coilData[fi], cubeId, fi);
      textures[fi].needsUpdate = true;
    }
  }
}

// ─── Apply a frame from Python ────────────────────────────────────────────────
// Expected message: { type:"frame", cubes:[{ id, pos:[x,y,z], quat:[x,y,z,w], coils:[[9]×6] }] }
function applyFrame(data) {
  for (const cube of data.cubes) {
    const mod = moduleMap[cube.id];
    if (!mod) continue;

    if (cube.pos)  mod.mesh.position.set(...cube.pos);
    if (cube.quat) mod.mesh.quaternion.set(...cube.quat);

    if (cube.coils) {
      for (let fi = 0; fi < 6; fi++)
        for (let ci = 0; ci < 9; ci++)
          mod.coilData[fi][ci].power = cube.coils[fi][ci] ?? 0;
    }
  }
}

// ─── WebSocket — Python connection ────────────────────────────────────────────
const WS_URL = "ws://localhost:8765";
let ws       = null;
let wsLive   = false;

const statusDot  = document.getElementById("ws-dot");
const statusText = document.getElementById("ws-text");

function setStatus(connected) {
  wsLive = connected;
  statusDot.style.background  = connected ? "#3fb950" : "#f85149";
  statusText.textContent       = connected ? "Python connected" : "No Python server";
}
setStatus(false);

function connectWS() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    setStatus(true);
    sendUI();   // immediately send current slider values
  };

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === "frame") applyFrame(data);
    } catch { /* ignore malformed */ }
  };

  ws.onclose = () => {
    setStatus(false);
    setTimeout(connectWS, 2000);   // auto-reconnect every 2 s
  };

  ws.onerror = () => ws.close();
}
connectWS();

// ─── Send UI state to Python ──────────────────────────────────────────────────
function sendUI() {
  if (!wsLive) return;
  ws.send(JSON.stringify({
    type:     "ui",
    spin:     CONFIG.INITIAL_ANGULAR_SPEED,
    damping:  CONFIG.LINEAR_DAMPING,
    strength: CONFIG.MU_OVER_4PI,
  }));
}

function sendButton(id) {
  if (!wsLive) return;
  ws.send(JSON.stringify({ type: "button", id }));
}

// ─── Control panel ────────────────────────────────────────────────────────────
function bindSlider(id, valId, decimals, cfgKey) {
  const slider  = document.getElementById(id);
  const display = document.getElementById(valId);
  slider.addEventListener("input", () => {
    const v = parseFloat(slider.value);
    display.textContent = v.toFixed(decimals);
    CONFIG[cfgKey] = v;
    sendUI();
  });
}

bindSlider("spin-slider",     "spin-val",     1, "INITIAL_ANGULAR_SPEED");
bindSlider("damp-slider",     "damp-val",     3, "LINEAR_DAMPING");
bindSlider("strength-slider", "strength-val", 2, "MU_OVER_4PI");

document.getElementById("restart-btn").addEventListener("click", () => sendButton("restart"));
document.getElementById("demo-btn").addEventListener("click",   () => sendButton("demo"));

// ─── Console utilities (usable from browser devtools) ─────────────────────────
// setDipole("a4d", 0.8)  — set a single dipole directly in the renderer
window.setDipole = function(id, strength) {
  const match = id.match(/^([a-z]+)([0-5])([a-z])$/);
  if (!match) { console.warn(`setDipole: invalid id "${id}"`); return; }
  const [, cubeId, faceStr, dipoleChar] = match;
  const mod = moduleMap[cubeId];
  if (!mod) { console.warn(`setDipole: unknown cube "${cubeId}"`); return; }
  const fi = parseInt(faceStr, 10);
  const ci = dipoleChar.charCodeAt(0) - 97;
  if (ci < 0 || ci > 8) { console.warn(`setDipole: dipole "${dipoleChar}" out of range`); return; }
  mod.coilData[fi][ci].power = strength;
};

// applyFrame({cubes:[...]})  — drive the renderer directly from the console
window.applyFrame = applyFrame;

// ─── Render loop ──────────────────────────────────────────────────────────────
function tick(now) {
  requestAnimationFrame(tick);
  maybeRedrawTextures(now);
  controls.update();
  renderer.render(scene, camera);
}
tick(performance.now());
