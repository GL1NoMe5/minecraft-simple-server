import asyncio
import mimetypes
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, List, Optional, Union

# Ensure standard font MIME types are recognized on Windows
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import (
    load_config, save_config, ServerConfig,
    TOTAL_SYSTEM_RAM_GB, TOTAL_SYSTEM_CORES, SERVER_DIR
)
from app.server_manager import server_manager, SERVER_PRESETS
from app.player_service import get_player_avatar, get_item_icon, is_valid_username

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        loop = asyncio.get_running_loop()
        server_manager.set_event_loop(loop)
    except Exception:
        pass
    server_manager._start_metrics_worker()
    yield
    server_manager.graceful_shutdown()

app = FastAPI(title="MSS (Minecraft Simple Server)", version="2.0.0", lifespan=lifespan)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith(".js") or path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    STATIC_DIR = Path(sys._MEIPASS) / "app" / "static"
else:
    STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

class CommandRequest(BaseModel):
    command: str

class DownloadJarRequest(BaseModel):
    engine: str
    version: str

class JavaCheckRequest(BaseModel):
    java_path: str

class ApplyPresetRequest(BaseModel):
    preset_id: str

class AutosaveIntervalRequest(BaseModel):
    seconds: Optional[int] = None
    minutes: Optional[int] = None

class PlayerActionRequest(BaseModel):
    action: str
    player: str
    target: Optional[Union[str, int]] = None
    mode: Optional[Union[str, int]] = None
    reason: Optional[Union[str, int]] = None
    value: Optional[Union[str, int]] = None

# API Endpoints
@app.get("/api/system")
def get_system_info():
    return {
        "total_ram_gb": TOTAL_SYSTEM_RAM_GB,
        "total_cpu_cores": TOTAL_SYSTEM_CORES,
        "server_dir": str(SERVER_DIR.resolve())
    }

@app.get("/api/presets")
def get_presets():
    return SERVER_PRESETS

@app.get("/api/versions")
def get_versions(engine: str = Query("Paper")):
    versions = server_manager.get_available_versions(engine)
    return {"engine": engine, "versions": versions}

@app.get("/api/config")
def get_config():
    cfg = load_config()
    return cfg.model_dump()

@app.post("/api/config")
def update_config(cfg: ServerConfig):
    save_config(cfg)
    server_manager.update_server_properties(cfg)
    if cfg.autosave_interval_seconds is not None:
        server_manager.set_autosave_interval(cfg.autosave_interval_seconds)
    return {"success": True, "config": cfg.model_dump()}

@app.get("/api/status")
def get_server_status():
    st = server_manager.get_status()
    cfg = load_config()
    core_info = server_manager.get_installed_core_info(cfg)
    st.update(core_info)
    st["view_distance"] = cfg.view_distance
    st["autosave_seconds"] = cfg.autosave_interval_seconds
    return st

@app.post("/api/server/start")
async def start_server():
    if not server_manager.loop or not server_manager.loop.is_running():
        server_manager.set_event_loop(asyncio.get_running_loop())
    cfg = load_config()
    res = server_manager.start_server(cfg)
    return res

@app.post("/api/server/stop")
async def stop_server():
    return server_manager.stop_server()

@app.post("/api/server/kill")
async def kill_server():
    return server_manager.kill_server()

@app.post("/api/server/restart")
async def restart_server():
    if not server_manager.loop or not server_manager.loop.is_running():
        server_manager.set_event_loop(asyncio.get_running_loop())
    cfg = load_config()
    return server_manager.restart_server(cfg)

@app.post("/api/server/autosave-interval")
async def set_autosave_interval(req: AutosaveIntervalRequest):
    if req.seconds is not None:
        sec = req.seconds
    elif req.minutes is not None:
        sec = req.minutes * 60
    else:
        sec = 900
    res = server_manager.set_autosave_interval(sec)
    if res.get("success"):
        try:
            cfg = load_config()
            cfg.autosave_interval_seconds = sec
            cfg.autosave_interval_minutes = max(1, round(sec / 60))
            save_config(cfg)
        except Exception:
            pass
    return res

@app.post("/api/server/command")
def send_command(req: CommandRequest):
    return server_manager.send_command(req.command)

@app.get("/api/server/eula")
def get_eula():
    eula_file = SERVER_DIR / "eula.txt"
    accepted = False
    if eula_file.exists():
        try:
            with open(eula_file, "r", encoding="utf-8") as f:
                content = f.read().lower()
                accepted = "eula=true" in content
        except Exception:
            pass
    return {"exists": eula_file.exists(), "accepted": accepted}

@app.post("/api/server/eula/accept")
def accept_eula():
    server_manager.write_eula()
    return {"success": True, "message": "EULA принята"}

@app.get("/api/server/properties")
def get_properties():
    props = server_manager.read_server_properties()
    cfg = load_config()
    if "view-distance" not in props:
        props["view-distance"] = str(cfg.view_distance)
    if "allow-flight" not in props:
        props["allow-flight"] = "true" if getattr(cfg, "allow_flight", True) else "false"
    return props

@app.post("/api/server/properties")
def save_properties(props: dict):
    prop_file = SERVER_DIR / "server.properties"
    with open(prop_file, "w", encoding="utf-8") as f:
        f.write("# Minecraft server properties (Managed by Local MC Server Manager)\n")
        for k, v in sorted(props.items()):
            f.write(f"{k}={v}\n")
    
    # Also sync view_distance & allow_flight to ServerConfig if present
    try:
        cfg = load_config()
        changed = False
        if "view-distance" in props:
            cfg.view_distance = int(props["view-distance"])
            changed = True
        if "allow-flight" in props:
            cfg.allow_flight = str(props["allow-flight"]).strip().lower() == "true"
            changed = True
        if changed:
            save_config(cfg)
    except Exception:
        pass

    return {"success": True}

@app.get("/api/addons")
def list_addons():
    cfg = load_config()
    return server_manager.list_addons(cfg.engine)

@app.post("/api/addons/upload")
async def upload_addons(files: List[UploadFile] = File(...)):
    cfg = load_config()
    target_dir = server_manager.get_target_addon_dir(cfg.engine)
    saved_files = []

    for file in files:
        if not file.filename.lower().endswith(".jar"):
            continue
        dest_path = target_dir / file.filename
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file.filename)

    return {
        "success": True,
        "saved_count": len(saved_files),
        "folder": target_dir.name,
        "files": saved_files
    }

@app.delete("/api/addons/{filename}")
def delete_addon(filename: str):
    cfg = load_config()
    ok = server_manager.delete_addon(cfg.engine, filename)
    if not ok:
        raise HTTPException(status_code=404, detail="Файл не найден или ошибка доступа")
    return {"success": True}

@app.post("/api/addons/{filename}/toggle")
def toggle_addon(filename: str):
    cfg = load_config()
    res = server_manager.toggle_addon(cfg.engine, filename)
    return res

@app.post("/api/server/download-jar")
def download_server_jar(req: DownloadJarRequest):
    return server_manager.download_server_jar(req.engine, req.version)

@app.post("/api/server/upload-jar")
async def upload_server_jar(file: UploadFile = File(...)):
    dest = SERVER_DIR / "server.jar"
    with open(dest, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"success": True, "message": "server.jar успешно загружен"}

@app.delete("/api/server/core")
def delete_server_core():
    return server_manager.delete_server_core()

@app.post("/api/java/check")
def check_java(req: JavaCheckRequest):
    return server_manager.check_java(req.java_path)

@app.get("/api/console/logs")
def get_console_logs(since: int = 0):
    logs = list(server_manager.log_history)
    if since > 0 and since < len(logs):
        return {"total": len(logs), "logs": logs[since:]}
    return {"total": len(logs), "logs": logs}

# WebSockets
@app.websocket("/ws/console")
async def websocket_console(websocket: WebSocket):
    await websocket.accept()
    if not server_manager.loop or not server_manager.loop.is_running():
        server_manager.set_event_loop(asyncio.get_running_loop())

    server_manager.connected_websockets.add(websocket)

    # Immediately stream entire log buffer to client as a batch
    history_logs = list(server_manager.log_history)
    try:
        await websocket.send_json({"type": "history", "data": history_logs})
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "command":
                cmd = data.get("data", "")
                if cmd:
                    server_manager.send_command(cmd)
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        server_manager.connected_websockets.discard(websocket)

@app.delete("/api/world")
def delete_world():
    return server_manager.delete_world()

@app.post("/api/world/upload")
async def upload_world(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Только ZIP архивы поддерживаются")
    
    # Save temp zip
    temp_zip = SERVER_DIR / "temp_upload.zip"
    try:
        with open(temp_zip, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return server_manager.upload_world(temp_zip)
    finally:
        if temp_zip.exists():
            temp_zip.unlink()

# ---------------- PLAYERS API ----------------
@app.get("/api/players")
async def get_players(refresh: bool = Query(default=False)):
    return await asyncio.to_thread(server_manager.get_players_list, refresh)

@app.get("/api/players/{player_name}/data")
async def get_player_data(player_name: str):
    if not is_valid_username(player_name):
        raise HTTPException(status_code=400, detail="Некорректное имя игрока")
    try:
        return await asyncio.to_thread(server_manager.get_player_detailed_data, player_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/players/action")
async def perform_player_action(req: PlayerActionRequest):
    if not is_valid_username(req.player):
        raise HTTPException(status_code=400, detail="Некорректное имя игрока")
    act = (req.action or "").strip().lower()
    mode = str(req.mode).strip() if (req.mode is not None and str(req.mode).strip()) else (str(req.value).strip() if (act == "gamemode" and req.value is not None and str(req.value).strip()) else None)
    reason = str(req.reason).strip() if (req.reason is not None and str(req.reason).strip()) else (str(req.value).strip() if (act == "kick" and req.value is not None and str(req.value).strip()) else None)
    target = str(req.target).strip() if (req.target is not None and str(req.target).strip()) else (str(req.value).strip() if (act == "teleport" and req.value is not None and str(req.value).strip()) else None)
    val = str(req.value).strip() if (req.value is not None and str(req.value).strip()) else None
    return await asyncio.to_thread(
        server_manager.execute_player_action,
        req.action,
        req.player,
        target,
        mode,
        reason,
        val
    )

@app.get("/api/players/{username}/avatar")
async def get_avatar(username: str, refresh: bool = Query(default=False)):
    if not is_valid_username(username):
        raise HTTPException(status_code=400, detail="Некорректное имя игрока")
    png_bytes = await asyncio.to_thread(get_player_avatar, username, refresh)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"}
    )

@app.get("/api/items/{item_id:path}/icon")
async def get_item_icon_endpoint(item_id: str):
    png_bytes = await asyncio.to_thread(get_item_icon, item_id)
    if not png_bytes:
        raise HTTPException(status_code=404, detail="Item icon not found")
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"}
    )

# Frontend UI
@app.get("/")
def get_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(
                content=f.read(),
                media_type="text/html; charset=utf-8",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
            )
    return HTMLResponse("<h1>MSS (Minecraft Simple Server) UI not found</h1>", media_type="text/html; charset=utf-8")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

