#!/usr/bin/env python3
"""
server.py  -  Python driver for the rounded-cube FEA viewer

Messages  Python -> Browser:
  { "type": "voxel_scene", ... }          cylinder view geometry (sent once on connect/view-switch)
  { "type": "frame", "cubes": [...] }     spinning-cubes animation (streamed at ~30 fps)

Messages  Browser -> Python:
  { "type": "ui_state",  "spin": f, "damping": f, "strength": f }
  { "type": "view",      "view": "cylinder" | "spinning_cubes" }

Install:  pip install websockets
Run:      python -u server.py
          then open http://localhost:5173/rounded-cube-viewer/
"""

import asyncio
import json
import math

import websockets
from websockets import serve

from fea_model import build_voxel_scene

# ── Shared state ──────────────────────────────────────────────────────────────
clients:      set  = set()
ui_state:     dict = {"spin": 0.8, "damping": 0.985, "strength": 0.4}
current_view: str  = "cylinder"

# Pre-build and serialise the FEA scene at startup (takes a few seconds)
_voxel_scene_json: str = json.dumps(build_voxel_scene(), separators=(',', ':'))


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
        async for raw in ws:
            try:
                msg = json.loads(raw)
                t   = msg.get("type")

                if t == "ui_state":
                    ui_state.update(msg)
                    print(f"[ui]  spin={msg.get('spin')}  "
                          f"damp={msg.get('damping')}  "
                          f"strength={msg.get('strength')}")

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
    print("-" * 52)
    async with serve(handler, "localhost", 8765):
        await broadcast_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
