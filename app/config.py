import json
import os
import sys
import psutil
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

SERVER_DIR = BASE_DIR / "server_data"
CONFIG_FILE = BASE_DIR / "server_config.json"

SERVER_DIR.mkdir(parents=True, exist_ok=True)
(SERVER_DIR / "mods").mkdir(parents=True, exist_ok=True)
(SERVER_DIR / "plugins").mkdir(parents=True, exist_ok=True)

TOTAL_SYSTEM_RAM_GB = max(2, round(psutil.virtual_memory().total / (1024**3)))
TOTAL_SYSTEM_CORES = max(1, psutil.cpu_count(logical=True) or 4)

class ServerConfig(BaseModel):
    engine: str = Field(default="Paper", description="Vanilla, Paper, Fabric, Forge")
    version: str = Field(default="1.20.4")
    min_ram: int = Field(default=2, ge=1, le=32)
    max_ram: int = Field(default=4, ge=1, le=32)
    cpu_cores: int = Field(default=min(4, TOTAL_SYSTEM_CORES), ge=1, le=64)
    view_distance: int = Field(default=10, ge=2, le=32)
    preset: str = Field(default="paper_optimized")
    java_path: str = Field(default="java")
    server_jar: str = Field(default="server.jar")
    auto_eula: bool = Field(default=True)
    custom_flags: str = Field(default="-XX:+UseG1GC")
    server_port: int = Field(default=25565)
    motd: str = Field(default="A Minecraft Server managed by Local MC")
    online_mode: bool = Field(default=False)
    difficulty: str = Field(default="normal")
    gamemode: str = Field(default="survival")
    max_players: int = Field(default=20)
    pvp: bool = Field(default=True)
    allow_flight: bool = Field(default=True)
    autosave_interval_seconds: int = Field(default=900, ge=0)
    autosave_interval_minutes: int = Field(default=15, ge=1, le=180) # Deprecated

def load_config() -> ServerConfig:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "autosave_interval_seconds" not in data and "autosave_interval_minutes" in data:
                    data["autosave_interval_seconds"] = int(data["autosave_interval_minutes"]) * 60
                return ServerConfig(**data)
        except Exception:
            pass
    cfg = ServerConfig()
    save_config(cfg)
    return cfg

def save_config(cfg: ServerConfig) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg.model_dump(), f, indent=2, ensure_ascii=False)
