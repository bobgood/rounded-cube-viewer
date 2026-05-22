#!/usr/bin/env python3
"""
server.py  —  Python driver for the rounded-cube viewer
────────────────────────────────────────────────────────
Connects to the Three.js viewer over WebSocket on port 8765.

Messages  Python → Browser:
  { "type": "frame",
    "cubes": [
      { "id": "a",
        "pos":   [x, y, z],
        "quat":  [qx, qy, qz, qw],   # unit quaternion
        "coils": [[p]*9, [p]*9, [p]*9, [p]*9, [p]*9, [p]*9]  # 6 faces × 9 coils, p ∈ [-1, 1]
      }, ...
    ]
  }

Messages  Browser → Python:
  { "type": "ui",     "spin": f, "damping": f, "strength": f }
  { "type": "button", "id": "restart" | "demo" }

Install:  pip install websockets
Run:      python server.py
          then open http://localhost:5173/rounded-cube-viewer/
"""

import asyncio
import json
import math

import websockets
from websockets.server import serve

# ── shared state ──────────────────────────────────────────────────────────────
clients: set = set()
ui_state: dict = {}          # last UI values received from browser


# ── demo scene builder ────────────────────────────────────────────────────────
def make_quat(ax, ay, az, angle: float) -> list[float]:
    """Axis-angle → unit quaternion [qx, qy, qz, qw]."""
    s = math.sin(angle / 2)
    return [ax * s, ay * s, az * s, math.cos(angle / 2)]


def build_frame(t: float) -> dict:
    """
    First-pass demo: two cubes sitting still, slowly spinning on different axes,
    with all coil powers rippling sinusoidally so you can verify the widget IDs.
    Replace this function with your magnetic model.
    """
    def ripple_coils(phase_offset: float) -> list[list[float]]:
        """Each coil oscillates independently so you can watch the labels."""
        return [
            [0.5 + 0.5 * math.sin(t * 1.1 + fi * 0.9 + ci * 0.4 + phase_offset)
             for ci in range(9)]
            for fi in range(6)
        ]

    return {
        "type": "frame",
        "cubes": [
            {
                "id":    "a",
                "pos":   [-1.2, 0.0, 0.0],
                "quat":  make_quat(0, 1, 0,  t * 0.4),   # spin around Y
                "coils": ripple_coils(0.0),
            },
            {
                "id":    "b",
                "pos":   [ 1.2, 0.0, 0.0],
                "quat":  make_quat(1, 0, 0, -t * 0.3),   # spin around X (opposite)
                "coils": ripple_coils(math.pi),            # out of phase with cube a
            },
        ],
    }


# ── WebSocket handler ─────────────────────────────────────────────────────────
async def handler(ws):
    clients.add(ws)
    print(f"[+] browser connected   (active: {len(clients)})")
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
                if msg.get("type") == "ui":
                    ui_state.update(msg)
                    print(f"[ui]  spin={msg.get('spin')}  "
                          f"damp={msg.get('damping')}  "
                          f"strength={msg.get('strength')}")
                elif msg.get("type") == "button":
                    print(f"[btn] {msg['id']}")
            except (json.JSONDecodeError, KeyError):
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(ws)
        print(f"[-] browser disconnected (active: {len(clients)})")


# ── broadcast loop ─────────────────────────────────────────────────────────────
async def broadcast_loop(fps: int = 60):
    t   = 0.0
    dt  = 1.0 / fps
    while True:
        if clients:
            frame = json.dumps(build_frame(t))
            results = await asyncio.gather(
                *[c.send(frame) for c in list(clients)],
                return_exceptions=True,
            )
            # silently drop stale connections that errored
            for c, r in zip(list(clients), results):
                if isinstance(r, Exception):
                    clients.discard(c)
        t  += dt
        await asyncio.sleep(dt)


# ── entry point ───────────────────────────────────────────────────────────────
async def main():
    print("─" * 52)
    print("  Cube viewer Python server")
    print("  WebSocket : ws://localhost:8765")
    print("  Browser   : http://localhost:5173/rounded-cube-viewer/")
    print("─" * 52)
    async with serve(handler, "localhost", 8765):
        await broadcast_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
