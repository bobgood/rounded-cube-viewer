import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

import { CONFIG }     from "./config.js";
import { RigidBody }  from "./physics/rigidBody.js";
import { Simulation } from "./physics/simulation.js";

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

// ─── Shared geometry (both modules use the same shape) ────────────────────────
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

function powerToRGB(p) {
  if (p < 0.5) {
    const t = p * 2;
    return [Math.round(t * 150), Math.round(220 - t * 70), Math.round(t * 150)];
  }
  const t = (p - 0.5) * 2;
  return [Math.round(150 + t * 105), Math.round(150 - t * 150), Math.round(150 - t * 150)];
}

function drawCoil(ctx, cx, cy, cellSize, power, id) {
  const [r, g, b] = powerToRGB(power);
  const radius = cellSize * 0.38;
  const lw     = cellSize * 0.055;

  // Soft glow behind circle
  const grd = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 1.6);
  grd.addColorStop(0, `rgba(${r},${g},${b},0.15)`);
  grd.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grd;
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 1.6, 0, Math.PI * 2);
  ctx.fill();

  // Dark filled circle body
  ctx.fillStyle = "#070d14";
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();

  // Colored stroke ring — brightness encodes power
  const alpha = 0.4 + 0.6 * power;
  ctx.strokeStyle = `rgba(${r},${g},${b},${alpha.toFixed(2)})`;
  ctx.lineWidth   = lw;
  ctx.beginPath();
  ctx.arc(cx, cy, radius - lw / 2, 0, Math.PI * 2);
  ctx.stroke();

  // ID label centered inside
  const fontSize = Math.round(cellSize * 0.18);
  ctx.fillStyle    = `rgba(${r},${g},${b},0.92)`;
  ctx.font         = `bold ${fontSize}px monospace`;
  ctx.textAlign    = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(id, cx, cy);
}

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
    const dipoleChar = String.fromCharCode(97 + idx);
    const id = `${cubeId}${faceIdx}${dipoleChar}`;
    drawCoil(ctx, (idx % 3) * CELL + CELL / 2, Math.floor(idx / 3) * CELL + CELL / 2, CELL, c.power, id);
  });
}

// ─── Module factory ───────────────────────────────────────────────────────────
function createModule(posX, cubeId) {
  // Independent coil power state
  const coilData = Array.from({ length: 6 }, () =>
    Array.from({ length: 9 }, () => ({
      power:  Math.random(),
      target: Math.random(),
      speed:  CONFIG.COIL_SPEED_MIN + Math.random() * (CONFIG.COIL_SPEED_MAX - CONFIG.COIL_SPEED_MIN),
    }))
  );

  // Per-face canvas textures
  const textures = Array.from({ length: 6 }, (_, fi) => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = TEX_SIZE;
    drawFace(canvas, coilData[fi], cubeId, fi);
    const tex = new THREE.CanvasTexture(canvas);
    tex.userData.canvas = canvas;
    return tex;
  });

  const materials = textures.map(tex =>
    new THREE.MeshStandardMaterial({ map: tex, metalness: 0.08, roughness: 0.6 })
  );

  const mesh = new THREE.Mesh(sharedGeometry, materials);
  mesh.castShadow = mesh.receiveShadow = true;
  scene.add(mesh);


  // Rigid body — initial position + random spin
  const rb = new RigidBody(new THREE.Vector3(posX, 0, 0));
  if (CONFIG.INITIAL_ANGULAR_SPEED > 0) {
    rb.angularVelocity.set(
      (Math.random() - 0.5) * 2 * CONFIG.INITIAL_ANGULAR_SPEED,
      (Math.random() - 0.5) * 2 * CONFIG.INITIAL_ANGULAR_SPEED,
      (Math.random() - 0.5) * 2 * CONFIG.INITIAL_ANGULAR_SPEED
    );
  }

  return { mesh, coilData, textures, rigidBody: rb, cubeId };
}

// ─── Spawn two modules ────────────────────────────────────────────────────────
const GAP     = 2.4;
const modules = [
  createModule(-GAP / 2, cubeIdFromIndex(0)),
  createModule( GAP / 2, cubeIdFromIndex(1)),
];

// ─── Physics simulation ───────────────────────────────────────────────────────
const simulation = new Simulation(modules);

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

// ─── Coil power animation ─────────────────────────────────────────────────────
function stepCoils() {
  for (const { coilData } of modules) {
    for (const face of coilData) {
      for (const c of face) {
        c.power += (c.target - c.power) * c.speed;
        if (Math.abs(c.power - c.target) < 0.01) {
          c.target = Math.random();
          c.speed  = CONFIG.COIL_SPEED_MIN + Math.random() * (CONFIG.COIL_SPEED_MAX - CONFIG.COIL_SPEED_MIN);
        }
      }
    }
  }
}

let lastTexUpdate = 0;
function maybeRedrawTextures(now) {
  if (now - lastTexUpdate < 33) return;   // ~30 fps redraws
  lastTexUpdate = now;
  for (const { coilData, textures, cubeId } of modules) {
    for (let fi = 0; fi < 6; fi++) {
      drawFace(textures[fi].userData.canvas, coilData[fi], cubeId, fi);
      textures[fi].needsUpdate = true;
    }
  }
}

// ─── Control panel ────────────────────────────────────────────────────────────
const MODULE_START_X = [-GAP / 2, GAP / 2];

function applyRandomSpin() {
  const speed = CONFIG.INITIAL_ANGULAR_SPEED;
  modules.forEach((m, i) => {
    // Reset position and orientation back to starting state
    m.rigidBody.position.set(MODULE_START_X[i], 0, 0);
    m.rigidBody.velocity.set(0, 0, 0);
    m.rigidBody.orientation.set(0, 0, 0, 1);
    m.rigidBody.angularVelocity.set(
      (Math.random() - 0.5) * 2 * speed,
      (Math.random() - 0.5) * 2 * speed,
      (Math.random() - 0.5) * 2 * speed
    );
  });
}

function bindSlider(id, valId, decimals, onValue) {
  const slider = document.getElementById(id);
  const display = document.getElementById(valId);
  slider.addEventListener("input", () => {
    const v = parseFloat(slider.value);
    display.textContent = v.toFixed(decimals);
    onValue(v);
  });
}

bindSlider("spin-slider",     "spin-val",     1, v => { CONFIG.INITIAL_ANGULAR_SPEED = v; });
bindSlider("damp-slider",     "damp-val",     3, v => { CONFIG.LINEAR_DAMPING = v; CONFIG.ANGULAR_DAMPING = v; });
bindSlider("strength-slider", "strength-val", 2, v => { CONFIG.MU_OVER_4PI = v; });

document.getElementById("restart-btn").addEventListener("click", applyRandomSpin);

// ─── Dipole API ───────────────────────────────────────────────────────────────
// setDipole("a4d", 0.8) — cubeId(letters) + faceNum(0-5) + dipoleChar(a-i)
window.setDipole = function(id, strength) {
  const match = id.match(/^([a-z]+)([0-5])([a-z])$/);
  if (!match) { console.warn(`setDipole: invalid id "${id}"`); return; }
  const [, cubeId, faceStr, dipoleChar] = match;
  const faceIdx   = parseInt(faceStr, 10);
  const coilIdx   = dipoleChar.charCodeAt(0) - 97;
  const mod = modules.find(m => m.cubeId === cubeId);
  if (!mod) { console.warn(`setDipole: no module with cubeId "${cubeId}"`); return; }
  if (coilIdx < 0 || coilIdx >= mod.coilData[faceIdx].length) {
    console.warn(`setDipole: dipole "${dipoleChar}" out of range`); return;
  }
  const coil = mod.coilData[faceIdx][coilIdx];
  coil.power  = strength;
  coil.target = strength;
};

// ─── Render loop ──────────────────────────────────────────────────────────────
let lastTime = performance.now();

function tick(now) {
  requestAnimationFrame(tick);
  const dt = (now - lastTime) / 1000;
  lastTime = now;

  stepCoils();
  simulation.update(dt);
  maybeRedrawTextures(now);

  controls.update();
  renderer.render(scene, camera);
}
tick(performance.now());
