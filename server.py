#!/usr/bin/env python3
"""
server.py  -  Python driver for the rounded-cube NGSolve viewer

Messages  Python -> Browser:
  { "type": "fea_mesh", ... }             scene geometry (on connect / scene change)
  { "type": "bfield_lines", ... }         traced B-field lines after solve

Messages  Browser -> Python:
  { "type": "ui_state",  "spin": f, "damping": f, "strength": f }
  { "type": "scene",     "scene": "1dipole" | "12dipoles_ng" | "30coils_ng" | "potcore_ng" }
  { "type": "solve_bfield", "strength": f, "mu_r": f, "saturate": bool }

Install:  pip install websockets ngsolve netgen
Run:      python -u server.py
          then open http://localhost:5173/rounded-cube-viewer/
"""

import asyncio
import json
import os
import struct

import numpy as np
import websockets
from websockets import serve

import ng_config
from scene_registry import build_scene, get_scene_id, invalidate_all_caches, list_scenes

_FIELD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fields")


def _pack_field(cfg: str) -> bytes | None:
    """Read fields/12dipoles_<cfg>.npz and pack it into one binary frame:
    [uint32 header_len][utf-8 JSON header][Bx f32][By f32][Bz f32] (C-order).
    Returns None if the file is missing."""
    path = os.path.join(_FIELD_DIR, f"12dipoles_{cfg}.npz")
    if not os.path.exists(path):
        return None
    d = np.load(path)
    bx = np.ascontiguousarray(d["Bx"], dtype="<f4")
    by = np.ascontiguousarray(d["By"], dtype="<f4")
    bz = np.ascontiguousarray(d["Bz"], dtype="<f4")
    size = [int(x) for x in d["size"]]
    origin = [float(x) for x in d["origin_mm"]]
    spacing = float(d["spacing_mm"])
    bmag_max = float(np.sqrt(bx * bx + by * by + bz * bz).max())
    hdr = json.dumps({
        "config": cfg, "size": size, "origin_mm": origin,
        "spacing_mm": spacing, "max_B_T": bmag_max,
    }).encode("utf-8")
    return struct.pack("<I", len(hdr)) + hdr + bx.tobytes() + by.tobytes() + bz.tobytes()

# ── Shared state ──────────────────────────────────────────────────────────────
clients:      set  = set()
ui_state:     dict = {"strength": 1.0}
_active_scene: str  = get_scene_id()

_scene_json: str = ""

# NGSolve/Netgen native code is not thread-safe: two solves running at once
# (e.g. two browser tabs, or a manual Solve during a field-build sweep) can
# corrupt memory and crash the process with an access violation. Serialize all
# heavy solves through this lock.
_solve_lock = asyncio.Lock()


def _rebuild_scene_json(strength_scale: float = 1.0) -> str:
    global _scene_json
    invalidate_all_caches()
    scene = build_scene(force=True, strength_scale=strength_scale)
    _scene_json = json.dumps(scene, separators=(',', ':'))
    return _scene_json


def _patch_scene_coils(upd: dict) -> None:
    """Merge a no-remesh coil_update into the cached scene JSON so reconnecting
    clients see the current excitation (arrows / frame / drive) on the same mesh."""
    global _scene_json
    try:
        scene = json.loads(_scene_json)
    except Exception:
        return
    for k in ("cu", "frame_config", "voxel_size"):
        if k in upd:
            scene[k] = upd[k]
    scene.setdefault("meta", {}).update(upd.get("meta", {}))
    _scene_json = json.dumps(scene)


def _set_scene(scene_id: str, strength_scale: float = 1.0) -> None:
    global _active_scene
    sid = (scene_id or "1dipole").strip().lower()
    if sid not in {s for s, _ in list_scenes()}:
        sid = "1dipole"
    ng_config.NG_SCENE_ID = sid
    _active_scene = sid
    _rebuild_scene_json(strength_scale=strength_scale)


# Pre-build at startup
_set_scene(get_scene_id())


# ── WebSocket handler ─────────────────────────────────────────────────────────

async def handler(ws):
    clients.add(ws)
    print(f"[+] browser connected   (active: {len(clients)})")
    try:
        if _scene_json:
            await ws.send(_scene_json)
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
                    print(f"[ui]  strength={msg.get('strength')}")

                elif t == "motion_meta":
                    import scene_ng12dipoles
                    pw = await asyncio.to_thread(scene_ng12dipoles.power_by_config)
                    mass = await asyncio.to_thread(scene_ng12dipoles.cube_mass)
                    await ws.send(json.dumps({
                        "type": "motion_meta", "power_W": pw, "mass_g": mass,
                    }))
                    print(f"[motion] sent power_by_config ({len(pw)} configs), "
                          f"mass={mass['total_mass_g']:.1f} g")

                elif t == "load_field":
                    cfg = str(msg.get("config", "face")).strip().lower()
                    payload = await asyncio.to_thread(_pack_field, cfg)
                    if payload is None:
                        await ws.send(json.dumps({"type": "field_error", "config": cfg,
                                                  "error": "field file not found"}))
                        print(f"[field] MISSING {cfg}")
                    else:
                        await ws.send(payload)
                        print(f"[field] sent {cfg} ({len(payload):,} bytes)")

                elif t == "scene":
                    sid = msg.get("scene", "1dipole")
                    print(f"[scene] {sid}")
                    _set_scene(sid, strength_scale=1.0)
                    await ws.send(_scene_json)
                    await ws.send(json.dumps({
                        "type": "scene_list",
                        "active": _active_scene,
                        "scenes": [{"id": s, "label": l} for s, l in list_scenes()],
                    }))

                elif t == "extended_grid":
                    on = bool(msg.get("on", False))
                    ng_config.NG_EXTENDED_GRID = on
                    print(f"[grid] extended={'on' if on else 'off'} -> rebuild {_active_scene}")
                    await asyncio.to_thread(_rebuild_scene_json)
                    await ws.send(_scene_json)

                elif t == "config":
                    name = str(msg.get("config", "face")).strip().lower()
                    if name in ng_config.NG12_CONFIGS:
                        ng_config.NG12_CONFIG_ACTIVE = name
                    if _active_scene == "12dipoles_ng":
                        import scene_ng12dipoles
                        upd = scene_ng12dipoles.coil_update()
                        scene_ng12dipoles.invalidate_cache()
                        _patch_scene_coils(upd)
                        print(f"[config] {ng_config.NG12_CONFIG_ACTIVE} (no re-mesh)")
                        await ws.send(json.dumps(upd))
                    else:
                        print(f"[config] {ng_config.NG12_CONFIG_ACTIVE} (ignored: {_active_scene})")

                elif t == "build_fields":
                    # Turn on the extended grid, force strength 1, push the enlarged
                    # mesh to the viewer FIRST, then solve every config and write files.
                    ng_config.NG_EXTENDED_GRID = True
                    ui_state["strength"] = 1.0
                    orig_cfg = ng_config.NG12_CONFIG_ACTIVE
                    names = list(ng_config.NG12_CONFIGS.keys())
                    total = len(names)
                    print(f"[fields] start: {total} configs (extended grid, strength 1, linear)")
                    await ws.send(json.dumps({"type": "build_fields_status",
                                              "state": "start", "total": total}))
                    try:
                        # Rebuild + broadcast viewer mesh so the ext grid is visible
                        # before the (slow) solve sweep begins.
                        print("[fields] rebuilding viewer mesh (extended grid)…")
                        await ws.send(json.dumps({"type": "build_fields_progress",
                                                  "phase": "viewer_mesh", "total": total}))
                        await asyncio.to_thread(_rebuild_scene_json)
                        for c in list(clients):
                            try:
                                await c.send(_scene_json)
                            except Exception:  # noqa: BLE001
                                pass

                        from ngsolve_solve import export_ng12_field_files
                        gen = export_ng12_field_files(strength=1.0, mu_r=1.0, saturate=False)

                        def _step():
                            try:
                                return next(gen)
                            except StopIteration:
                                return None

                        files = []
                        async with _solve_lock:
                            while True:
                                step = await asyncio.to_thread(_step)
                                if step is None:
                                    break
                                if step.get("phase") == "solved":
                                    files.append(step)
                                await ws.send(json.dumps({"type": "build_fields_progress",
                                                          **step}))

                            # Restore the original config and push the (extended) mesh.
                            ng_config.NG12_CONFIG_ACTIVE = orig_cfg
                            await asyncio.to_thread(_rebuild_scene_json)
                        for c in list(clients):
                            try:
                                await c.send(_scene_json)
                            except Exception:  # noqa: BLE001
                                pass
                        await ws.send(json.dumps({"type": "build_fields_status",
                                                  "state": "done", "total": total,
                                                  "files": files}))
                        print(f"[fields] done: {len(files)} files")
                    except Exception as exc:  # noqa: BLE001
                        print(f"[fields] FAILED: {type(exc).__name__}: {exc}")
                        await ws.send(json.dumps({"type": "build_fields_status",
                                                  "state": "error",
                                                  "error": f"{type(exc).__name__}: {exc}"}))

                elif t == "solve_bfield":
                    scale = float(msg.get("strength", ui_state.get("strength", 1.0)))
                    mu_r = float(msg.get("mu_r", 1.0))
                    saturate = bool(msg.get("saturate", True))
                    print(f"[ng] solve_bfield  scene={_active_scene}  "
                          f"strength_scale={scale}  mu_r={mu_r:g}  saturate={saturate}")
                    await ws.send(json.dumps({"type": "bfield_status", "state": "solving"}))
                    try:
                        async with _solve_lock:
                            if _active_scene == "1dipole":
                                from ngsolve_solve import solve_ng_bfield
                                payload = await asyncio.to_thread(
                                    solve_ng_bfield, mu_r=mu_r, fea_strength_scale=scale,
                                    saturate=saturate,
                                )
                            elif _active_scene == "12dipoles_ng":
                                from ngsolve_solve import solve_ng12_bfield
                                payload = await asyncio.to_thread(
                                    solve_ng12_bfield, mu_r=mu_r, fea_strength_scale=scale,
                                    saturate=saturate,
                                )
                            elif _active_scene == "potcore_ng":
                                from ngsolve_solve import solve_potcore_bfield
                                payload = await asyncio.to_thread(
                                    solve_potcore_bfield, mu_r=mu_r, fea_strength_scale=scale,
                                    saturate=saturate,
                                )
                            else:
                                from ngsolve_solve import solve_ng30_bfield
                                payload = await asyncio.to_thread(
                                    solve_ng30_bfield, mu_r=mu_r, fea_strength_scale=scale,
                                    saturate=saturate,
                                )
                        await ws.send(json.dumps(payload, separators=(',', ':')))
                    except Exception as exc:  # noqa: BLE001
                        print(f"[ng] solve_bfield FAILED: {type(exc).__name__}: {exc}")
                        await ws.send(json.dumps({
                            "type": "bfield_status", "state": "error",
                            "message": f"{type(exc).__name__}: {exc}",
                        }))

            except (json.JSONDecodeError, KeyError):
                pass

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(ws)
        print(f"[-] browser disconnected (active: {len(clients)})")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    print("-" * 52)
    print("  Cube viewer Python server")
    print("  WebSocket : ws://localhost:8765")
    print("  Browser   : http://localhost:5173/rounded-cube-viewer/")
    print(f"  Scene     : {_active_scene}  (ng_config.py; restart after edits)")
    print("-" * 52)
    async with serve(handler, "localhost", 8765):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
