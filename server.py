#!/usr/bin/env python3
"""
server.py  -  Python driver for the rounded-cube FEA viewer

Messages  Python -> Browser:
  { "type": "voxel_scene", ... }          experiment geometry (on connect / scene change)
  { "type": "frame", "cubes": [...] }     spinning-cubes animation (streamed at ~30 fps)

Messages  Browser -> Python:
  { "type": "ui_state",  "spin": f, "damping": f, "strength": f }
  { "type": "view",      "view": "cylinder" | "spinning_cubes" }
  { "type": "scene",     "scene": "frame" | "dipole" }
  { "type": "fea_start", "strength": f }
  { "type": "solve_bfield", "strength": f, "mu_r": f }

Install:  pip install websockets
Run:      python -u server.py
          then open http://localhost:5173/rounded-cube-viewer/
"""

import asyncio
import json
import math

import websockets
from websockets import serve

from fea_config import FEA_SCENE_ID
from fea_model import build_bfield_lines
from scene_registry import build_scene, get_scene_id, invalidate_all_caches, list_scenes

# ── Shared state ──────────────────────────────────────────────────────────────
clients:      set  = set()
ui_state:     dict = {"spin": 0.8, "damping": 0.985, "strength": 0.4}
current_view: str  = "cylinder"
_active_scene: str  = get_scene_id()

_voxel_scene_json: str = ""


def _rebuild_scene_json(fea_strength_scale: float = 1.0) -> str:
    global _voxel_scene_json
    invalidate_all_caches()
    scene = build_scene(force=True, fea_strength_scale=fea_strength_scale)
    _voxel_scene_json = json.dumps(scene, separators=(',', ':'))
    return _voxel_scene_json


def _set_scene(scene_id: str, fea_strength_scale: float = 1.0) -> None:
    global _active_scene
    import fea_config

    sid = (scene_id or "frame").strip().lower()
    if sid not in {s for s, _ in list_scenes()}:
        sid = "frame"
    fea_config.FEA_SCENE_ID = sid
    _active_scene = sid
    _rebuild_scene_json(fea_strength_scale=fea_strength_scale)


# Pre-build at startup
_set_scene(FEA_SCENE_ID)


# ── Spinning-cubes demo ───────────────────────────────────────────────────────

def _make_quat(ax, ay, az, angle):
    s = math.sin(angle / 2)
    return [ax * s, ay * s, az * s, math.cos(angle / 2)]


def _build_frame(t):
    def ripple(phase):
        return [
            [0.5 + 0.5 * math.sin(t * 1.1 + fi * 0.9 + ci * 0.4 + phase)
             for ci in range(9)]
            for fi in range(6)
        ]
    return {
        "type": "frame",
        "cubes": [
            {"id": "a", "pos": [-1.2, 0.0, 0.0],
             "quat": _make_quat(0, 1, 0,  t * 0.4),  "coils": ripple(0.0)},
            {"id": "b", "pos": [ 1.2, 0.0, 0.0],
             "quat": _make_quat(1, 0, 0, -t * 0.3),  "coils": ripple(math.pi)},
        ],
    }


# ── WebSocket handler ─────────────────────────────────────────────────────────

async def handler(ws):
    global current_view
    clients.add(ws)
    print(f"[+] browser connected   (active: {len(clients)})")
    try:
        # Default client mode is cylinder; always offer voxel payload on connect.
        if _voxel_scene_json:
            await ws.send(_voxel_scene_json)
        await ws.send(json.dumps({
            "type": "scene_list",
            "active": _active_scene,
            "scenes": [{"id": sid, "label": lbl} for sid, lbl in list_scenes()],
        }))

        async for raw in ws:
            try:
                msg = json.loads(raw)
                t   = msg.get("type")

                if t == "ui_state":
                    ui_state.update(msg)
                    print(f"[ui]  spin={msg.get('spin')}  "
                          f"damp={msg.get('damping')}  "
                          f"strength={msg.get('strength')}")

                elif t == "scene":
                    sid = msg.get("scene", "frame")
                    print(f"[scene] {sid}")
                    # Use coil_init table at full weight; Strength slider -> fea_start only.
                    _set_scene(sid, fea_strength_scale=1.0)
                    if current_view == "cylinder":
                        await ws.send(_voxel_scene_json)
                    await ws.send(json.dumps({
                        "type": "scene_list",
                        "active": _active_scene,
                        "scenes": [{"id": s, "label": l} for s, l in list_scenes()],
                    }))

                elif t == "fea_start":
                    scale = float(msg.get("strength", ui_state.get("strength", 1.0)))
                    print(f"[fea] start  scene={_active_scene}  strength_scale={scale}")
                    _rebuild_scene_json(fea_strength_scale=scale)
                    if current_view == "cylinder":
                        await ws.send(_voxel_scene_json)

                elif t == "solve_bfield":
                    scale = float(msg.get("strength", ui_state.get("strength", 1.0)))
                    mu_r = float(msg.get("mu_r", 1.0))
                    print(f"[fea] solve_bfield  scene={_active_scene}  "
                          f"strength_scale={scale}  mu_r={mu_r:g}")
                    await ws.send(json.dumps({"type": "bfield_status", "state": "solving"}))
                    try:
                        payload = await asyncio.to_thread(
                            build_bfield_lines, fea_strength_scale=scale, mu_r=mu_r
                        )
                        await ws.send(json.dumps(payload, separators=(',', ':')))
                    except Exception as exc:  # noqa: BLE001
                        print(f"[fea] solve_bfield FAILED: {type(exc).__name__}: {exc}")
                        await ws.send(json.dumps({
                            "type": "bfield_status", "state": "error",
                            "message": f"{type(exc).__name__}: {exc}",
                        }))

                elif t == "view":
                    current_view = msg.get("view", "cylinder")
                    print(f"[view] {current_view}")
                    if current_view == "cylinder":
                        await ws.send(_voxel_scene_json)

            except (json.JSONDecodeError, KeyError):
                pass

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(ws)
        print(f"[-] browser disconnected (active: {len(clients)})")


# ── Broadcast loop ─────────────────────────────────────────────────────────────

async def broadcast_loop(fps=30):
    t  = 0.0
    dt = 1.0 / fps
    while True:
        if clients and current_view == "spinning_cubes":
            frame = json.dumps(_build_frame(t))
            await asyncio.gather(
                *[c.send(frame) for c in list(clients)],
                return_exceptions=True,
            )
        t  += dt
        await asyncio.sleep(dt)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    print("-" * 52)
    print("  Cube viewer Python server")
    print("  WebSocket : ws://localhost:8765")
    print("  Browser   : http://localhost:5173/rounded-cube-viewer/")
    print(f"  Scene     : {_active_scene}  (coil_init.py per scene; restart after edits)")
    print("-" * 52)
    async with serve(handler, "localhost", 8765):
        await broadcast_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")

