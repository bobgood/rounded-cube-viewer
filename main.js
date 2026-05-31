import * as THREE from "three";
import { OrbitControls }      from "three/examples/jsm/controls/OrbitControls.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { extractIsosurface }  from "./marching_cubes.js";
import { MotionStage, MOTION_OFFSET, levelToDrive } from "./motion.js";

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
controls.addEventListener("change", scheduleResize);
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

const CU_ARROW_MAX = 12_000;

// ─── NGSolve scene modes ──────────────────────────────────────────────────────
const MODE_OPTIONS = [
  { id: "cylinder:1dipole",      view: "cylinder", scene: "1dipole",      label: "1 dipole" },
  { id: "cylinder:12dipoles_ng", view: "cylinder", scene: "12dipoles_ng", label: "12 dipoles" },
  { id: "cylinder:potcore_ng", view: "cylinder", scene: "potcore_ng", label: "1 pot core" },
  { id: "cylinder:30coils_ng",   view: "cylinder", scene: "30coils_ng",   label: "30 coils" },
  { id: "motion:12dipoles_ng",   view: "motion",   scene: "12dipoles_ng", label: "12 dipole motion" },
];

// ─── View state (opacity sliders; 0 = hidden) ─────────────────────────────────
let _currentView = "cylinder";
let _currentModeId = "cylinder:1dipole";
let _activeScene = "1dipole";
let _motion = null;   // lazily-built MotionStage (motion view)
let _selectedIdx = -1;   // debug: index of the hand-manipulated motion body (-1 = none)
let _hasScene = false;
let _driveBase = null;   // { total_current_A, total_power_W, n_active_coils } at 1×
let _partsOpacity = 0.5;
let _metalOpacity = 0.0;
let _currentOpacity = 0.85;

let _cuFieldBase  = null;
let _cuArrowMesh       = null;
let _cuArrowMeshBehind = null;
let _ouGroup      = null;
let _ouOpacity    = 0.35;
let _sceneVoxelSize = 0.05;

const _cuUp   = new THREE.Vector3(0, 1, 0);
const _cuDir  = new THREE.Vector3();
const _cuCol  = new THREE.Color();
const _cuQuat = new THREE.Quaternion();
const _dummy = new THREE.Object3D();

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

function _applyCurrentArrows(field, vs, maxCount, renderOrder, logTag) {
  if (!field?.sites?.positions?.length) return null;

  const pos = field.sites.positions;
  const dir = field.sites.directions;
  const amp = field.sites.amplitudes;
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
    depthTest: true,
    depthWrite: false,
  });
  const mesh = new THREE.InstancedMesh(geo, mat, n);
  mesh.frustumCulled = false;
  // Front pass: default LessEqualDepth. Must render AFTER the steel writes depth
  // (steel renderOrder 1), so arrows behind the metal fail the test and only the
  // in-front arrows draw — at full opacity regardless of how transparent the metal is.
  mesh.material.depthFunc = THREE.LessEqualDepth;
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

    const a   = amp[i];
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
  // ── Behind pass: same geometry, GreaterDepth test, faded opacity ────────
  // Renders only where the arrow is BEHIND geometry already in the depth
  // buffer (steel/voxels) — giving a natural fade-through look.
  // renderOrder must match the front pass so both run after the surface writes depth.
  const matBehind = new THREE.MeshBasicMaterial({
    toneMapped: false,
    transparent: true,
    opacity: _currentOpacity * 0.18,
    depthTest: true,
    depthWrite: false,
    depthFunc: THREE.GreaterDepth,
  });
  const meshBehind = new THREE.InstancedMesh(geo, matBehind, count);
  meshBehind.frustumCulled = false;
  meshBehind.renderOrder = renderOrder;
  for (let i = 0; i < count; i++) {
    mesh.getMatrixAt(i, _dummy.matrix);
    meshBehind.setMatrixAt(i, _dummy.matrix);
    const col = new THREE.Color();
    mesh.getColorAt(i, col);
    meshBehind.setColorAt(i, col);
  }
  meshBehind.count = count;
  meshBehind.instanceMatrix.needsUpdate = true;
  if (meshBehind.instanceColor) meshBehind.instanceColor.needsUpdate = true;
  scene.add(meshBehind);

  console.info(`[${logTag}] ${count} current arrows`);
  return [mesh, meshBehind];
}

function clearCuArrows() {
  _disposeArrowMesh(_cuArrowMesh);
  _disposeArrowMesh(_cuArrowMeshBehind);
  _cuArrowMesh = null;
  _cuArrowMeshBehind = null;
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

function applyCuField(cu, vs) {
  clearCuArrows();
  if (!cu?.sites?.positions?.length) {
    console.warn("[Cu] no sites — restart python -u server.py");
    return;
  }
  [_cuArrowMesh, _cuArrowMeshBehind] = _applyCurrentArrows(cu, vs, CU_ARROW_MAX, 2, "Cu");
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
  if (_motion) _motion.setVisible(_currentView === "motion");
  const parts = _partsOpacity > 0.001;
  if (_ngSteelGroup) _ngSteelGroup.visible = isCyl && parts;
  if (_cuArrowMesh) {
    const show = isCyl && _currentOpacity > 0.001;
    _cuArrowMesh.visible = show;
    if (_cuArrowMesh.material) _cuArrowMesh.material.opacity = _currentOpacity;
  }
  if (_cuArrowMeshBehind) {
    _cuArrowMeshBehind.visible = isCyl && _currentOpacity > 0.001 && _partsOpacity < 0.001;
    if (_cuArrowMeshBehind.material) _cuArrowMeshBehind.material.opacity = _currentOpacity * 0.35;
  }
  applyBlineVisibility();
  applyBsurfVisibility();
  applyGridOpacity();
  applyOuOpacityFromSlider();
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

  // Cache the sampled |B| grid and (re)build the force-metric isosurface.
  if (data.field?.b?.length) {
    _field = {
      n: data.field.n,
      origin: data.field.origin,
      step: data.field.step,
      b: Float32Array.from(data.field.b),
      b_max: data.field.b_max,
    };
  } else {
    _field = null;
  }
  rebuildBsurf();
  updateBsurfReadout();

  const meta = data.meta ?? {};
  const status = document.getElementById("solve-status");
  if (status) {
    const maxB = meta.max_B_T != null ? meta.max_B_T.toExponential(2) : "?";
    const mu = meta.mu_r != null ? ` · μ=${Math.round(meta.mu_r)}` : "";
    const scene = _activeScene ? ` · ${_activeScene}` : "";
    status.textContent = `${meta.n_lines ?? lines.length} lines · max|B|=${maxB} T${mu}${scene}`;
    status.style.color = "#3fb950";
  }
  setBusyFlag("solve", false);
}

function applyBfieldStatus(data) {
  const status = document.getElementById("solve-status");
  if (data.state === "solving") {
    if (status) { status.textContent = "Solving B field…"; status.style.color = "#d29922"; }
    setBusyFlag("solve", true);
  } else if (data.state === "error") {
    if (status) { status.textContent = `Error: ${data.message ?? "solve failed"}`; status.style.color = "#f85149"; }
    setBusyFlag("solve", false);
  }
}

function applyBlineVisibility() {
  if (!_blineGroup) return;
  const op = _blineOpacity();
  // B lines yield to the force-metric surface when it is active.
  const bsurfOn = _bsurfLevel() != null;
  _blineGroup.visible = _currentView === "cylinder" && op > 0.001 && !bsurfOn;
  _blineGroup.traverse(o => { if (o.material) o.material.opacity = op; });
}

// ─── Force-metric isosurface (B surf slider) ──────────────────────────────────
// The metric is the magnetic pressure p = B²/(2μ0) — the attractive force
// density between two equal fields facing each other. It is monotonic in |B|,
// so we threshold the sampled |B| grid directly and label the level as force.
const _MU0 = 4 * Math.PI * 1e-7;
let _field = null;       // { n, origin, step, b:Float32Array, b_max }
let _bsurfMesh = null;
let _bsurfRaf = 0;

function clearBsurf() {
  if (_bsurfMesh) {
    scene.remove(_bsurfMesh);
    _bsurfMesh.geometry?.dispose();
    _bsurfMesh.material?.dispose();
    _bsurfMesh = null;
  }
}

// Slider t∈[0,1] → |B| isolevel, logarithmic in force from a fixed 0.1 Pa floor
// up to b_max. t≈0 is "off". The floor B = √(2μ0·p) ≈ 0.5 mT gives a faint,
// far-reaching "area of influence" surface. Returns null when off / no field.
const _BSURF_MIN_PA = 0.1;
function _bsurfLevel() {
  if (!_field || !(_field.b_max > 0)) return null;
  const t = parseFloat(document.getElementById("bsurf-slider")?.value ?? 0);
  if (t <= 0.001) return null;
  const bMax = _field.b_max;
  const bMin = Math.min(Math.sqrt(2 * _MU0 * _BSURF_MIN_PA), bMax * 0.5);
  return bMin * Math.pow(bMax / bMin, t);   // t→0: bMin (0.1 Pa), t=1: bMax
}

function _fmtForce(pa) {
  if (pa >= 1e6) return `${(pa / 1e6).toFixed(2)}MPa`;
  if (pa >= 1e3) return `${(pa / 1e3).toFixed(0)}kPa`;
  return `${pa.toFixed(0)}Pa`;
}

function updateBsurfReadout() {
  const el = document.getElementById("bsurf-val");
  if (!el) return;
  const bLevel = _bsurfLevel();
  if (bLevel == null) { el.textContent = "off"; return; }
  el.textContent = _fmtForce((bLevel * bLevel) / (2 * _MU0));
}

function rebuildBsurf() {
  clearBsurf();
  const bLevel = _bsurfLevel();
  if (bLevel == null || !_field) return;

  const verts = extractIsosurface(_field.b, _field.n, bLevel, _field.origin, _field.step);
  if (!verts.length) return;

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(verts, 3));
  geo.computeVertexNormals();

  // Colour by the level on the same blue→orange scale the B lines use.
  const frac = Math.sqrt(Math.min(1, bLevel / _field.b_max));
  const col = _blineColorLo.clone().lerp(_blineColorHi, frac);
  const mat = new THREE.MeshStandardMaterial({
    color: col, metalness: 0.0, roughness: 0.5,
    transparent: true, opacity: _blineOpacity(),
    side: THREE.DoubleSide, depthWrite: false,
  });
  _bsurfMesh = new THREE.Mesh(geo, mat);
  _bsurfMesh.renderOrder = 2;
  scene.add(_bsurfMesh);
  applyBsurfVisibility();
  applyBlineVisibility();
}

// Coalesce rapid slider input into one rebuild per frame.
function scheduleBsurf() {
  updateBsurfReadout();
  applyBlineVisibility();   // toggle lines off/on as the surface turns on/off
  if (_bsurfRaf) return;
  _bsurfRaf = requestAnimationFrame(() => { _bsurfRaf = 0; rebuildBsurf(); });
}

function applyBsurfVisibility() {
  if (!_bsurfMesh) return;
  const op = _blineOpacity();
  _bsurfMesh.visible = _currentView === "cylinder" && op > 0.001;
  if (_bsurfMesh.material) _bsurfMesh.material.opacity = op;
}

// ─── NGSolve / Netgen surface mesh (fea_mesh payload) ──────────────────────────
let _ngMeshGroup = null;   // air box wireframe — grid slider
let _ngSteelGroup = null;  // steel solid skin  — parts (opacity) slider

function clearNgMesh() {
  for (const grp of [_ngMeshGroup, _ngSteelGroup]) {
    if (!grp) continue;
    scene.remove(grp);
    grp.traverse(o => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
  }
  _ngMeshGroup = null;
  _ngSteelGroup = null;
}

function applyFeaMesh(data) {
  clearNgMesh();
  clearCuArrows();
  clearBlines();
  clearBsurf();
  _field = null;
  updateBsurfReadout();

  const verts = data.vertices ?? [];
  _ngMeshGroup  = new THREE.Group();   // air box wireframe (grid slider)
  _ngSteelGroup = new THREE.Group();   // steel solid skin  (parts slider)

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

      const [r, g, b] = region.color ?? [0.8, 0.82, 0.85];
      const col = new THREE.Color(r, g, b);
      const solidOp = region.solid_opacity ?? 0;
      const wireOp  = region.wire_opacity  ?? 0;

      // ── Mesh slider overlay (all regions, mesh-slider driven) ─────────────
      geo.computeVertexNormals();
      if (solidOp > 0.001) {
        const solidMat = new THREE.MeshStandardMaterial({
          color: col, metalness: 0.2, roughness: 0.7,
          transparent: true, opacity: solidOp,
          side: THREE.DoubleSide, depthWrite: false,
        });
        solidMat.userData.baseOpacity = solidOp;
        _ngMeshGroup.add(new THREE.Mesh(geo, solidMat));
      }
      if (wireOp > 0.001) {
        const wireMat = new THREE.LineBasicMaterial({
          color: col, transparent: true, opacity: wireOp, depthWrite: false,
        });
        wireMat.userData.baseOpacity = wireOp;
        _ngMeshGroup.add(new THREE.LineSegments(new THREE.WireframeGeometry(geo), wireMat));
      }

      // ── Parts slider solid skin (steel only, opaque-capable) ──────────────
      if (region.name === "steel") {
        // FrontSide only (Netgen normals are consistently outward for a solid).
        // renderOrder 1: steel renders and writes depth BEFORE arrows (renderOrder 0
        // in GreaterDepth behind-pass), so the depth test correctly separates
        // in-front arrows (full opacity) from behind arrows (faded).
        const mat = new THREE.MeshStandardMaterial({
          color: col, metalness: 0.35, roughness: 0.55,
          transparent: true, opacity: _partsOpacity,
          side: THREE.FrontSide, depthWrite: true,
        });
        const steelMesh = new THREE.Mesh(geo, mat);
        steelMesh.renderOrder = 1;
        _ngSteelGroup.add(steelMesh);
      }
    }
  }
  scene.add(_ngSteelGroup);
  scene.add(_ngMeshGroup);

  // Coil current arrows
  const vs = data.voxel_size ?? 0.15;
  _sceneVoxelSize = vs;
  if (data.cu?.sites?.positions?.length) {
    _cuFieldBase = _cloneCoilField(data.cu);
    applyCuField(data.cu, vs);
  } else {
    _cuFieldBase = null;
  }

  _hasScene = true;
  _activeScene = data.scene_id ?? "1dipole";
  _cubeCorners = data.frame_config?.cube_corners ?? null;
  if (data.frame_config) buildOuOutline(data.frame_config);
  syncModeSelectFromState();
  applyView();
  applyOpacityFromSlider();
  applyCurrentOpacityFromSlider();
  scheduleResize();

  const meta = data.meta ?? {};
  if (meta.extended_grid != null) {
    const ext = document.getElementById("extgrid-checkbox");
    if (ext) ext.checked = !!meta.extended_grid;
  }
  applyConfigUi(meta.config);
  _driveBase = (meta.total_power_W != null || meta.total_mass_g != null)
    ? { total_power_W: meta.total_power_W ?? 0,
        total_mass_g: meta.total_mass_g ?? 0,
        n_active_coils: meta.n_active_coils ?? 0 }
    : null;
  updateDriveReadout();
  const status = document.getElementById("solve-status");
  if (status && _currentView === "cylinder" && !_busyFlags.has("build")) {
    if (meta.error) {
      status.textContent = `Mesh error: ${meta.error}`;
      status.style.color = "#f85149";
    } else {
      const box = meta.air_box_mm != null ? ` · box ${meta.air_box_mm}mm` : "";
      status.textContent =
        `${(meta.n_tris ?? 0).toLocaleString()} tris · ${(meta.n_points ?? 0).toLocaleString()} pts · maxh ${meta.maxh_mm}mm${box}`;
      status.style.color = "#3fb950";
    }
  }
  setBusyFlag("mesh", false);   // mesh ready — unlock unless solve/build still running
}

// Excitation (config) changed: geometry is identical, so we only refresh the
// coil arrows, frame polarity and drive totals — no mesh rebuild. Any prior
// B-field solve no longer matches the new excitation, so it is cleared.
function applyCoilUpdate(data) {
  clearCuArrows();
  clearBlines();
  clearBsurf();
  _field = null;
  updateBsurfReadout();

  const vs = data.voxel_size ?? _sceneVoxelSize ?? 0.15;
  _sceneVoxelSize = vs;
  if (data.cu?.sites?.positions?.length) {
    _cuFieldBase = _cloneCoilField(data.cu);
    applyCuField(data.cu, vs);
  } else {
    _cuFieldBase = null;
  }
  if (data.frame_config) {
    _cubeCorners = data.frame_config.cube_corners ?? _cubeCorners;
    buildOuOutline(data.frame_config);
  }

  const meta = data.meta ?? {};
  applyConfigUi(meta.config);
  if (meta.total_power_W != null) {
    _driveBase = {
      total_power_W: meta.total_power_W ?? 0,
      total_mass_g: _driveBase?.total_mass_g ?? 0,   // mass is config-independent
      n_active_coils: meta.n_active_coils ?? 0,
    };
  }
  updateDriveReadout();
  applyView();
  applyOpacityFromSlider();
  applyCurrentOpacityFromSlider();
  const status = document.getElementById("solve-status");
  if (status && _currentView === "cylinder") {
    status.textContent = `config: ${meta.config ?? "?"} · solve to update B`;
    status.style.color = "#8b949e";
  }
  // Config is instant (arrows only) — never clears mesh/solve/build busy flags.
}

function applyGridOpacity() {
  // Air box wireframe — grid (metal-opacity) slider.
  if (_ngMeshGroup) {
    const g = _metalOpacity;
    _ngMeshGroup.visible = _currentView === "cylinder" && g > 0.001;
    _ngMeshGroup.traverse(o => {
      const base = o.material?.userData?.baseOpacity;
      if (base != null) o.material.opacity = base * g;
    });
  }
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

function _fmtW(w) {
  // Watts: integer up to ~10 kW, then "12.3kW".
  return Math.abs(w) >= 1e4 ? `${(w / 1e3).toFixed(1)}kW` : `${Math.round(w)}W`;
}

// Drive readout on the Sat line: ohmic power (scales with Strength²) + total
// mass (fixed). Power base is at 1×; mass is geometry-only.
function updateDriveReadout() {
  const el = document.getElementById("drive-readout");
  if (!el) return;
  if (!_driveBase) {
    el.textContent = "";
    return;
  }
  const s = _strength();
  const pow = (_driveBase.total_power_W ?? 0) * s * s;
  const mass = _driveBase.total_mass_g ?? 0;
  const parts = [];
  if (_driveBase.n_active_coils > 0) parts.push(_fmtW(pow));
  if (mass > 0) parts.push(`${Math.round(mass)}g`);
  el.textContent = parts.join(" · ");
  el.style.color = "#8b949e";
}

function sendSolveBfield() {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  const strength = _strength();
  const mu_r = _blineMu();
  const saturate = document.getElementById("sat-checkbox")?.checked ?? true;
  setBusyFlag("solve", true);
  const status = document.getElementById("solve-status");
  if (status) {
    status.textContent = `Solving B field (μ=${mu_r}, ${strength.toFixed(2)}×${saturate ? ", sat" : ""})…`;
    status.style.color = "#d29922";
  }
  _ws.send(JSON.stringify({ type: "solve_bfield", strength, mu_r, saturate }));
}

function sendUIState() {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  _ws.send(JSON.stringify({ type: "ui_state", strength: _strength() }));
}

function sendScene(sceneId) {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  clearBlines();
  setBusyFlag("mesh", true);   // mesh rebuild in flight — lock out solves/builds
  _ws.send(JSON.stringify({ type: "scene", scene: sceneId }));
}

function currentModeId() {
  return _currentModeId;
}

function syncModeSelectFromState() {
  const sel = document.getElementById("mode-select");
  if (!sel) return;
  const id = currentModeId();
  if (sel.value !== id) sel.value = id;
  applyConfigUi();
}

// Read the per-box dropdowns + power slider into MotionStage body states.
function motionStatesFromUI() {
  const read = (suffix) => ({
    config: document.getElementById(`cfg${suffix}`)?.value ?? "face",
    axis:   document.getElementById(`axis${suffix}`)?.value ?? "+Z",
    roll:   document.getElementById(`roll${suffix}`)?.value ?? "N",
    level:  parseFloat(document.getElementById(`pow${suffix}`)?.value ?? "1"),
  });
  return [
    { ...read("A"), offset: [-MOTION_OFFSET, 0, 0] },
    { ...read("B"), offset: [ MOTION_OFFSET, 0, 0] },
  ];
}

// Power readout: signed percentage of full power (− = reversed polarity).
function updateMotionPowReadout(suffix) {
  const el = document.getElementById(`pow${suffix}-val`);
  if (!el) return;
  const d = levelToDrive(parseFloat(document.getElementById(`pow${suffix}`)?.value ?? "1"));
  const pct = Math.round(d.powerPct);
  el.textContent = `${d.polarity < 0 ? "\u2212" : "+"}${pct}%`;
}

function refreshMotion() {
  if (!_motion) _motion = new MotionStage(scene);
  updateMotionPowReadout("A");
  updateMotionPowReadout("B");
  _motion.setBodies(motionStatesFromUI());
  // Rebuild creates fresh body groups — re-apply the debug selection tint.
  if (_selectedIdx >= 0 && _selectedIdx < _motion.bodies.length) {
    _motion.highlight(_motion.bodies[_selectedIdx], true);
  } else {
    _selectedIdx = -1;
  }
  updateMotionSelReadout();
}

function enterMotionView() {
  _currentView = "motion";
  refreshMotion();
  document.getElementById("controls")?.classList.add("view-motion");
  applyView();
  syncModeSelectFromState();
  scheduleResize();
}

// The config dropdown only drives the 12-dipole scene; the others have a single
// fixed excitation, so disable it elsewhere. `active` (when given) reflects the
// config the server actually built.
function applyConfigUi(active) {
  const is12 = _activeScene === "12dipoles_ng";
  const sel = document.getElementById("config-select");
  if (sel) {
    sel.disabled = !is12;
    if (active && sel.value !== active) sel.value = active;
  }
  const btn = document.getElementById("build-fields-btn");
  if (btn) btn.disabled = !is12;
}

function updateModeOptionLabels(scenes) {
  const sel = document.getElementById("mode-select");
  if (!sel || !scenes?.length) return;
  for (const s of scenes) {
    const opt = sel.querySelector(`option[value="cylinder:${s.id}"]`);
    if (opt) opt.textContent = s.label;
  }
}

function setLoadStatus(msg) {
  const status = document.getElementById("solve-status");
  if (!status || _currentView !== "cylinder") return;
  status.textContent = msg;
  status.style.color = "#d29922";
}

function applyMode(modeId) {
  const mode = MODE_OPTIONS.find(m => m.id === modeId) ?? MODE_OPTIONS[0];
  _currentModeId = mode.id;
  const view = mode.view ?? "cylinder";

  // Motion view is fully client-side (no mesh build / solver). It just stages
  // rounded cubes + north arrows; the camera/orbit controls keep working.
  if (view === "motion") {
    enterMotionView();
    return;
  }

  const prevScene = _activeScene;
  _currentView = "cylinder";
  selectMotionBody(-1);   // leaving motion view: drop any debug selection
  document.getElementById("controls")?.classList.remove("view-motion");
  if (_motion) _motion.setVisible(false);

  const sceneId = mode.scene ?? "1dipole";
  const sceneChanged = sceneId !== prevScene;

  if (sceneChanged) {
    _activeScene = sceneId;
    _hasScene = false;
    setLoadStatus(`Building ${mode.label}…`);
    sendScene(sceneId);
  } else if (!_hasScene) {
    setLoadStatus(`Building ${mode.label}…`);
    sendScene(sceneId);
  }

  applyView();
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
    if      (data.type === "fea_mesh")     applyFeaMesh(data);
    else if (data.type === "coil_update")  applyCoilUpdate(data);
    else if (data.type === "scene_list") {
      updateModeOptionLabels(data.scenes ?? []);
      if (data.active) {
        _activeScene = data.active;
        // Don't let a server scene broadcast override the motion-view selection.
        if (_currentView === "cylinder") {
          _currentModeId = `cylinder:${_activeScene}`;
          syncModeSelectFromState();
        }
      }
    }
    else if (data.type === "bfield_lines")  applyBfieldLines(data);
    else if (data.type === "bfield_status") applyBfieldStatus(data);
    else if (data.type === "build_fields_status")   applyBuildFieldsStatus(data);
    else if (data.type === "build_fields_progress") applyBuildFieldsProgress(data);
  });
  _ws.addEventListener("close", () => setTimeout(connectWS, 2000));
}

connectWS();

// ─── Hover: nearest face → nearest corner (c1–c8) ─────────────────────────────
const _raycaster = new THREE.Raycaster();
const _mouse     = new THREE.Vector2();
const _hoverPt   = new THREE.Vector3();
const _facePlane = new THREE.Plane();
// Cube face corner order (+Z, -Z, +X, -X, +Y, -Y)
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
  if (!hi) return;
  if (_currentView !== "cylinder") return;   // motion view owns hover-info (debug readout)
  if (!_hasCorners()) { hi.textContent = ""; return; }
  _setPointerNdc(e.clientX, e.clientY);
  _raycaster.setFromCamera(_mouse, camera);
  let pt = null;
  if (_ngSteelGroup?.visible) {
    const hits = _raycaster.intersectObject(_ngSteelGroup, true);
    if (hits.length) pt = hits[0].point;
  }
  if (!pt) pt = _raycastCubePoint(_raycaster.ray);
  hi.textContent = pt ? _cornerFromPoint(pt) : "";
});

// ─── Motion-view debug: double-click select a cube, drag to pose it ────────────
// Double-click a cube → it tints and orbit rotate/pan are remapped to act on
// THAT body (left = rotate, right = pan). Double-click empty space → deselect
// and the camera controls return. Hand-placed poses persist across config /
// power UI changes, so this doubles as a quick way to lay out the starting
// coordinates of two (or more) cubes for later animation.
let _dragBtn = -1;
let _lastX = 0, _lastY = 0;
const _camRight = new THREE.Vector3();
const _camUp    = new THREE.Vector3();
const _camFwd   = new THREE.Vector3();
const _dragQuat = new THREE.Quaternion();

function _selectedBody() {
  return _selectedIdx >= 0 && _motion && _selectedIdx < _motion.bodies.length
    ? _motion.bodies[_selectedIdx] : null;
}

function updateMotionSelReadout() {
  const hi = document.getElementById("hover-info");
  if (!hi) return;
  const b = _selectedBody();
  if (!b) { if (_currentView === "motion") hi.textContent = ""; return; }
  const p = b.position;
  const e = new THREE.Euler().setFromQuaternion(b.quaternion, "XYZ");
  const d = v => THREE.MathUtils.radToDeg(v).toFixed(0);
  hi.textContent =
    `box ${_selectedIdx === 0 ? "A" : _selectedIdx === 1 ? "B" : _selectedIdx} · ` +
    `pos(${p.x.toFixed(2)}, ${p.y.toFixed(2)}, ${p.z.toFixed(2)}) · ` +
    `rot(${d(e.x)}°, ${d(e.y)}°, ${d(e.z)}°)`;
}

function selectMotionBody(idx) {
  if (_motion && _selectedIdx >= 0 && _selectedIdx < _motion.bodies.length) {
    _motion.highlight(_motion.bodies[_selectedIdx], false);
  }
  _selectedIdx = (idx != null && idx >= 0) ? idx : -1;
  const picked = _selectedBody();
  if (picked) {
    _motion.highlight(picked, true);
    controls.enableRotate = false;   // orbit rotate/pan now drive the body
    controls.enablePan    = false;
  } else {
    controls.enableRotate = true;
    controls.enablePan    = true;
  }
  updateMotionSelReadout();
}

function _pickMotionBody(clientX, clientY) {
  if (!_motion?.bodies?.length) return -1;
  _setPointerNdc(clientX, clientY);
  _raycaster.setFromCamera(_mouse, camera);
  const hits = _raycaster.intersectObjects(_motion.bodies, true);
  if (!hits.length) return -1;
  let o = hits[0].object;
  while (o && !_motion.bodies.includes(o)) o = o.parent;
  return o ? _motion.bodies.indexOf(o) : -1;
}

function _rotateSelected(dx, dy) {
  const b = _selectedBody();
  if (!b) return;
  camera.matrixWorld.extractBasis(_camRight, _camUp, _camFwd);
  const speed = 0.01;
  _dragQuat.setFromAxisAngle(_camUp, dx * speed);
  b.quaternion.premultiply(_dragQuat);
  _dragQuat.setFromAxisAngle(_camRight, dy * speed);
  b.quaternion.premultiply(_dragQuat);
  _motion.markMoved(_selectedIdx);
  updateMotionSelReadout();
}

function _panSelected(dx, dy) {
  const b = _selectedBody();
  if (!b) return;
  camera.matrixWorld.extractBasis(_camRight, _camUp, _camFwd);
  // world units per screen pixel at the body's depth
  const dist = camera.position.distanceTo(b.position);
  const vh   = (viewport ?? renderer.domElement).clientHeight || 1;
  const wpp  = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * dist / vh;
  b.position.addScaledVector(_camRight,  dx * wpp);
  b.position.addScaledVector(_camUp,    -dy * wpp);
  _motion.markMoved(_selectedIdx);
  updateMotionSelReadout();
}

renderer.domElement.addEventListener("dblclick", e => {
  if (_currentView !== "motion") return;
  selectMotionBody(_pickMotionBody(e.clientX, e.clientY));
});

renderer.domElement.addEventListener("mousedown", e => {
  if (_currentView !== "motion" || !_selectedBody()) return;
  if (e.button !== 0 && e.button !== 2) return;
  _dragBtn = e.button;
  _lastX = e.clientX;
  _lastY = e.clientY;
  e.preventDefault();
});

window.addEventListener("mousemove", e => {
  if (_dragBtn < 0 || !_selectedBody()) return;
  const dx = e.clientX - _lastX;
  const dy = e.clientY - _lastY;
  _lastX = e.clientX;
  _lastY = e.clientY;
  if (_dragBtn === 0) _rotateSelected(dx, dy);
  else if (_dragBtn === 2) _panSelected(dx, dy);
});

window.addEventListener("mouseup", () => { _dragBtn = -1; });

renderer.domElement.addEventListener("contextmenu", e => {
  if (_currentView === "motion" && _selectedBody()) e.preventDefault();
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

const _strengthSlider = document.getElementById("strength-slider");
if (_strengthSlider) {
  const showStrength = () => {
    const val = document.getElementById("strength-val");
    if (val) val.textContent = _fmtStrength(_strength());
    updateDriveReadout();
  };
  _strengthSlider.addEventListener("input", () => {
    showStrength();
    sendUIState();
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
  if (_ngSteelGroup) {
    _ngSteelGroup.traverse(o => {
      if (o.isMesh && o.material) {
        o.material.opacity = _partsOpacity;
        o.material.transparent = _partsOpacity < 0.999;
        o.material.needsUpdate = true;
      }
    });
  }
  applyView();
}

function applyMetalOpacityFromSlider() {
  if (!_metalOpSlider) return;
  _metalOpacity = parseFloat(_metalOpSlider.value);
  const opV = document.getElementById("metal-opacity-val");
  if (opV) opV.textContent = _metalOpacity.toFixed(2);
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
const _modeSelect = document.getElementById("mode-select");
if (_modeSelect) {
  _modeSelect.addEventListener("change", () => applyMode(_modeSelect.value));
}

// Per-box motion dropdowns: rebuild the staged bodies (client-side, instant).
for (const id of ["cfgA", "axisA", "rollA", "cfgB", "axisB", "rollB"]) {
  document.getElementById(id)?.addEventListener("change", () => {
    if (_currentView === "motion") refreshMotion();
  });
}
// Power/polarity sliders rebuild live while dragging.
for (const id of ["powA", "powB"]) {
  document.getElementById(id)?.addEventListener("input", () => {
    if (_currentView === "motion") refreshMotion();
  });
}

document.getElementById("restart-btn")?.addEventListener("click", () => sendUIState());
document.getElementById("solve-btn")?.addEventListener("click", () => sendSolveBfield());

const _extGridCheckbox = document.getElementById("extgrid-checkbox");
if (_extGridCheckbox) {
  _extGridCheckbox.addEventListener("change", () => {
    if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
    setLoadStatus(`Rebuilding mesh (${_extGridCheckbox.checked ? "extended" : "normal"} grid)…`);
    setBusyFlag("mesh", true);
    _ws.send(JSON.stringify({ type: "extended_grid", on: _extGridCheckbox.checked }));
  });
}

const _configSelect = document.getElementById("config-select");
if (_configSelect) {
  _configSelect.addEventListener("change", () => {
    if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
    setLoadStatus(`Switching to ${_configSelect.value} config…`);
    _ws.send(JSON.stringify({ type: "config", config: _configSelect.value }));
  });
}

// Force the Strength slider to 1× (centre of the log slider, t=0.5) and refresh.
function setStrengthToOne() {
  const sl = document.getElementById("strength-slider");
  if (!sl) return;
  sl.value = 0.5;
  const val = document.getElementById("strength-val");
  if (val) val.textContent = _fmtStrength(_strength());
  updateDriveReadout();
  sendUIState();
}

const _buildFieldsBtn = document.getElementById("build-fields-btn");
if (_buildFieldsBtn) {
  _buildFieldsBtn.addEventListener("click", () => {
    if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
    // The button owns these preconditions: extended grid ON + strength 1×.
    const ext = document.getElementById("extgrid-checkbox");
    if (ext) ext.checked = true;
    setStrengthToOne();
    setBusyFlag("build", true);
    _setBuildStatus("Build: starting…");
    _ws.send(JSON.stringify({ type: "build_fields" }));
  });
}

function _setBuildStatus(text, color = "#d29922") {
  // Share the main solve-status line (under the Solve button).
  const el = document.getElementById("solve-status");
  if (!el) return;
  el.textContent = text;
  el.style.color = color;
}

// Track concurrent operations independently so a fast config switch (arrows only)
// cannot unlock buttons while a mesh rebuild or build sweep is still running.
const _busyFlags = new Set();

function setBusyFlag(name, on) {
  if (on) _busyFlags.add(name);
  else _busyFlags.delete(name);
  setButtonsBusy(_busyFlags.size > 0);
}

// Gray out every action button while ANY tracked operation is running, then
// restore them when idle. The build button is additionally gated to the
// 12-dipole scene via applyConfigUi.
function setButtonsBusy(busy) {
  const solveBtn = document.getElementById("solve-btn");
  const restartBtn = document.getElementById("restart-btn");
  const buildBtn = document.getElementById("build-fields-btn");
  const modeSel = document.getElementById("mode-select");
  const cfgSel = document.getElementById("config-select");
  if (busy) {
    if (solveBtn) solveBtn.disabled = true;
    if (restartBtn) restartBtn.disabled = true;
    if (buildBtn) buildBtn.disabled = true;
    // Lock the selectors too: a scene/config switch mid-solve would race the
    // mesh/solve on the server. (We still set config-select.value to track the
    // build's progress; a disabled select can be updated programmatically.)
    if (modeSel) modeSel.disabled = true;
    if (cfgSel) cfgSel.disabled = true;
  } else {
    if (solveBtn) solveBtn.disabled = false;
    if (restartBtn) restartBtn.disabled = false;
    if (modeSel) modeSel.disabled = false;
    applyConfigUi();   // re-gates config-select + build button to the 12-dipole scene
  }
}

function applyBuildFieldsStatus(data) {
  if (data.state === "start") {
    setBusyFlag("build", true);
    _setBuildStatus(`Build: grid rebuild + ${data.total} solves…`);
  } else if (data.state === "done") {
    setBusyFlag("build", false);
    _setBuildStatus(`✓ ${data.total} field files → /fields`, "#3fb950");
  } else if (data.state === "error") {
    setBusyFlag("build", false);
    _setBuildStatus(`Build error: ${data.error ?? "?"}`, "#f85149");
  }
}

function applyBuildFieldsProgress(data) {
  if (data.phase === "viewer_mesh") {
    setBusyFlag("mesh", true);
    _setBuildStatus(`Build: rebuilding extended grid for viewer…`);
    return;
  }
  if (data.phase === "mesh") {
    _setBuildStatus(`Build: rebuilding extended grid (1) + ${data.total} solves…`);
    return;
  }
  if (data.phase === "solving") {
    // Reflect the config currently being solved in the dropdown + status.
    const sel = document.getElementById("config-select");
    if (sel) sel.value = data.config;
    _setBuildStatus(`Build: solving ${data.index + 1}/${data.total} · ${data.config}…`);
    return;
  }
  if (data.phase === "solved") {
    _setBuildStatus(`Build: solved ${data.done}/${data.total} · ${data.config} (max|B|=${data.max_B_T} T)`);
  }
}

const _blineSlider = document.getElementById("bline-opacity-slider");
if (_blineSlider) {
  _blineSlider.addEventListener("input", () => {
    const v = parseFloat(_blineSlider.value);
    const val = document.getElementById("bline-opacity-val");
    if (val) val.textContent = v.toFixed(2);
    applyBlineVisibility();
    applyBsurfVisibility();
  });
}

const _bsurfSlider = document.getElementById("bsurf-slider");
if (_bsurfSlider) {
  _bsurfSlider.addEventListener("input", scheduleBsurf);
  updateBsurfReadout();
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

// ─── Render loop ──────────────────────────────────────────────────────────────
function tick() {
  requestAnimationFrame(tick);
  controls.update();
  renderer.render(scene, camera);
}
tick();
