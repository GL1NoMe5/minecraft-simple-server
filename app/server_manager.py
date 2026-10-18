import asyncio
import collections
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Set, Union
from fastapi import WebSocket
import psutil

from app.config import SERVER_DIR, ServerConfig, save_config, load_config

# Cached version lists to ensure fast loading
VERSION_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 3600  # 1 hour

FALLBACK_VERSIONS = [
    "1.21.4", "1.21.3", "1.21.1", "1.21", 
    "1.20.6", "1.20.4", "1.20.2", "1.20.1", "1.20",
    "1.19.4", "1.19.3", "1.19.2", "1.19.1", "1.19",
    "1.18.2", "1.18.1", "1.18",
    "1.17.1", "1.17",
    "1.16.5", "1.16.4", "1.16.3", "1.16.2", "1.16.1",
    "1.15.2", "1.14.4", "1.13.2", "1.12.2", "1.8.9", "1.7.10"
]

SERVER_PRESETS = {
    "vanilla_light": {
        "name": "Легкий Vanilla",
        "description": "2 GB RAM, 2 ядра, прорисовка 8 чанков. Идеально для ванильной игры с друзьями.",
        "engine": "Vanilla",
        "min_ram": 2,
        "max_ram": 2,
        "cpu_cores": 2,
        "view_distance": 8,
        "custom_flags": "-XX:+UseG1GC"
    },
    "paper_optimized": {
        "name": "Оптимизированный Paper (Aikar)",
        "description": "4 GB RAM, 4 ядра, прорисовка 10 чанков. Флаги оптимизации сборщика мусора Aikar.",
        "engine": "Paper",
        "min_ram": 2,
        "max_ram": 4,
        "cpu_cores": 4,
        "view_distance": 10,
        "custom_flags": "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:+AlwaysPreTouch -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1"
    },
    "fabric_perf": {
        "name": "Производительный Fabric",
        "description": "6 GB RAM, 4 ядра, прорисовка 10 чанков. Для сборок с модами на оптимизацию (Lithium, FerriteCore).",
        "engine": "Fabric",
        "min_ram": 3,
        "max_ram": 6,
        "cpu_cores": 4,
        "view_distance": 10,
        "custom_flags": "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:+AlwaysPreTouch"
    },
    "forge_heavy": {
        "name": "Тяжелый Forge (Модпаки)",
        "description": "8 GB RAM, 6 ядер, прорисовка 12 чанков. Для крупных индустриальных и магических сборок.",
        "engine": "Forge",
        "min_ram": 4,
        "max_ram": 8,
        "cpu_cores": 6,
        "view_distance": 12,
        "custom_flags": "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:+AlwaysPreTouch -Dfml.readTimeout=180"
    },
    "neoforge_modpack": {
        "name": "Современный NeoForge",
        "description": "8 GB RAM, 6 ядер, прорисовка 12 чанков. Для современных сборок модов на NeoForge (1.20.1–1.21.4).",
        "engine": "NeoForge",
        "min_ram": 4,
        "max_ram": 8,
        "cpu_cores": 6,
        "view_distance": 12,
        "custom_flags": "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:+AlwaysPreTouch"
    },
    "extreme_server": {
        "name": "Экстремальный сервер",
        "description": "16 GB RAM, 8 ядер, прорисовка 16 чанков. Для высоконагруженных серверов со множеством игроков.",
        "engine": "Paper",
        "min_ram": 8,
        "max_ram": 16,
        "cpu_cores": 8,
        "view_distance": 16,
        "custom_flags": "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=100 -XX:+AlwaysPreTouch"
    }
}

class ServerManager:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.status: str = "STOPPED"  # STOPPED, STARTING, RUNNING, STOPPING, RESTARTING
        self.log_history: collections.deque = collections.deque(maxlen=3000)
        self.connected_websockets: Set[WebSocket] = set()
        self.lock = threading.Lock()
        self.reader_thread: Optional[threading.Thread] = None
        self.start_time: Optional[float] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.autosave_task: Optional[asyncio.Task] = None
        try:
            cfg = load_config()
            self.autosave_interval: int = getattr(cfg, "autosave_interval_seconds", 900)
        except Exception:
            self.autosave_interval: int = 900
        self._proc_cache: Dict[int, psutil.Process] = {}
        self.last_stats: Dict[str, Any] = {
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
            "memory_str": "0 MB",
            "memory_percent": 0.0,
            "uptime_seconds": 0
        }
        self.download_progress: Dict[str, Any] = {
            "is_downloading": False,
            "status": "idle",
            "percent": 0,
            "message": ""
        }
        self.online_players: Dict[str, Dict[str, Any]] = {}
        self._list_event = threading.Event()
        self._last_list_query: float = 0.0
        self._silent_list_pending: int = 0
        self._entity_data_events: Dict[str, threading.Event] = {}
        self._entity_snbt_cache: Dict[str, str] = {}
        self._stop_metrics_event = threading.Event()
        self._metrics_thread: Optional[threading.Thread] = None
        self._start_metrics_worker()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def _start_metrics_worker(self):
        if self._metrics_thread is None or not self._metrics_thread.is_alive():
            self._stop_metrics_event.clear()
            self._metrics_thread = threading.Thread(target=self._metrics_worker_loop, daemon=True, name="LMC-Metrics")
            self._metrics_thread.start()

    def _stop_metrics_worker(self):
        self._stop_metrics_event.set()
        if self._metrics_thread and self._metrics_thread.is_alive():
            self._metrics_thread.join(timeout=1.0)
        self._metrics_thread = None

    def _metrics_worker_loop(self):
        while not self._stop_metrics_event.is_set():
            try:
                if self.process is not None and self.process.poll() is None:
                    self._update_process_metrics()
            except Exception:
                pass
            self._stop_metrics_event.wait(2.0)

    def _update_process_metrics(self):
        with self.lock:
            proc = self.process
            start_time = self.start_time

        if not proc or proc.poll() is not None or not start_time:
            with self.lock:
                self._proc_cache.clear()
                self.online_players.clear()
                self.last_stats = {
                    "cpu_percent": 0.0,
                    "memory_mb": 0.0,
                    "memory_str": "0 MB",
                    "memory_percent": 0.0,
                    "uptime_seconds": 0
                }
            return

        uptime = int(time.time() - start_time)
        try:
            parent = self._proc_cache.get(proc.pid)
            if parent is None or not parent.is_running():
                parent = psutil.Process(proc.pid)
                parent.cpu_percent(interval=None)
                self._proc_cache[proc.pid] = parent

            children = parent.children(recursive=True)
            processes = [parent] + children

            active_pids = set()
            total_rss = 0
            total_mem_percent = 0.0
            total_cpu_percent = 0.0

            for p in processes:
                try:
                    pid = p.pid
                    active_pids.add(pid)
                    cached_proc = self._proc_cache.get(pid)
                    if cached_proc is None:
                        p.cpu_percent(interval=None)
                        self._proc_cache[pid] = p
                        cached_proc = p

                    mem_info = cached_proc.memory_info()
                    total_rss += mem_info.rss
                    total_mem_percent += cached_proc.memory_percent()
                    total_cpu_percent += cached_proc.cpu_percent(interval=None)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            # Clean stale PIDs from cache
            for stale_pid in list(self._proc_cache.keys()):
                if stale_pid not in active_pids:
                    self._proc_cache.pop(stale_pid, None)

            num_cpus = psutil.cpu_count() or 1
            normalized_cpu = total_cpu_percent / num_cpus
            normalized_cpu = min(100.0, max(0.0, round(normalized_cpu, 1)))

            mem_mb = round(total_rss / (1024 * 1024), 1)
            with self.lock:
                self.last_stats["uptime_seconds"] = uptime
                self.last_stats["memory_mb"] = mem_mb
                self.last_stats["memory_str"] = self.format_memory(mem_mb)
                self.last_stats["memory_percent"] = round(total_mem_percent, 1)
                self.last_stats["cpu_percent"] = normalized_cpu
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    @staticmethod
    def format_memory(memory_mb: float) -> str:
        if memory_mb >= 1024:
            return f"{memory_mb / 1024:.1f} GB"
        return f"{int(round(memory_mb))} MB"

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            # Check if process died unexpectedly
            if self.process is not None:
                poll = self.process.poll()
                if poll is not None:
                    self.status = "STOPPED"
                    self.process = None
                    self._proc_cache.clear()
                    self.online_players.clear()
                    self._stop_autosave_task()
                    self.last_stats = {
                        "cpu_percent": 0.0,
                        "memory_mb": 0.0,
                        "memory_str": "0 MB",
                        "memory_percent": 0.0,
                        "uptime_seconds": 0
                    }

            if self.process and self.start_time:
                self.last_stats["uptime_seconds"] = int(time.time() - self.start_time)

            return {
                "status": self.status,
                "is_running": self.process is not None and self.process.poll() is None,
                "pid": self.process.pid if self.process else None,
                "stats": dict(self.last_stats),
                "download": self.download_progress,
                "online_players_count": len(self.online_players),
                "autosave_seconds": self.autosave_interval
            }

    async def broadcast_log(self, text: str):
        dead_sockets = set()
        payload = json.dumps({"type": "log", "data": text})
        for ws in list(self.connected_websockets):
            try:
                await ws.send_text(payload)
            except Exception:
                dead_sockets.add(ws)
        if dead_sockets:
            self.connected_websockets.difference_update(dead_sockets)

    def _sync_broadcast(self, text: str):
        # Appends to history
        self.log_history.append(text)
        # Schedule broadcast on the main event loop
        if self.loop and self.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.broadcast_log(text), self.loop)
            except Exception:
                pass

    def write_eula(self):
        eula_path = SERVER_DIR / "eula.txt"
        with open(eula_path, "w", encoding="utf-8") as f:
            f.write("# By changing the setting below to TRUE you are indicating your agreement to our EULA (https://aka.ms/MinecraftEULA).\n")
            f.write("eula=true\n")

    def update_server_properties(self, cfg: ServerConfig):
        prop_file = SERVER_DIR / "server.properties"
        props = {}
        if prop_file.exists():
            try:
                with open(prop_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            props[k.strip()] = v.strip()
            except Exception:
                pass

        # Update key settings
        props["server-port"] = str(cfg.server_port)
        props["motd"] = cfg.motd
        props["online-mode"] = "true" if cfg.online_mode else "false"
        props["difficulty"] = cfg.difficulty
        props["gamemode"] = cfg.gamemode
        props["max-players"] = str(cfg.max_players)
        props["pvp"] = "true" if cfg.pvp else "false"
        props["allow-flight"] = "true" if getattr(cfg, "allow_flight", True) else "false"
        props["view-distance"] = str(cfg.view_distance)

        with open(prop_file, "w", encoding="utf-8") as f:
            f.write("# Minecraft server properties (Managed by Local MC Server Manager)\n")
            for k, v in sorted(props.items()):
                f.write(f"{k}={v}\n")

    def read_server_properties(self) -> Dict[str, str]:
        prop_file = SERVER_DIR / "server.properties"
        props = {}
        if prop_file.exists():
            try:
                with open(prop_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            props[k.strip()] = v.strip()
            except Exception:
                pass
        return props

    def check_java(self, java_path: str) -> Dict[str, Any]:
        cmd = [java_path, "-version"]
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5
            )
            output = res.stderr if res.stderr else res.stdout
            first_line = output.splitlines()[0] if output.splitlines() else "Unknown Java version"
            return {"valid": True, "version": first_line, "path": java_path}
        except Exception as e:
            return {"valid": False, "error": str(e), "path": java_path}

    def find_forge_args_file(self) -> Optional[Path]:
        lib_dir = SERVER_DIR / "libraries" / "net"
        if not lib_dir.exists():
            return None
        target_name = "win_args.txt" if os.name == "nt" else "unix_args.txt"
        for p in sorted(lib_dir.rglob(target_name), reverse=True):
            if p.is_file():
                return p
        return None

    def get_installed_core_info(self, cfg: ServerConfig) -> Dict[str, Any]:
        jar_path = SERVER_DIR / cfg.server_jar
        forge_args = self.find_forge_args_file()
        if forge_args is not None:
            ver_folder = forge_args.parent.name
            path_str = str(forge_args).replace("\\", "/").lower()
            core_type = "NeoForge" if "neoforged" in path_str else "Forge"
            return {
                "jar_exists": True,
                "jar_size_mb": 0,
                "core_label": f"{core_type} {ver_folder}"
            }
        if jar_path.exists():
            size_mb = round(jar_path.stat().st_size / (1024 * 1024), 1)
            return {
                "jar_exists": True,
                "jar_size_mb": size_mb,
                "core_label": f"server.jar · {size_mb} MB"
            }
        return {
            "jar_exists": False,
            "jar_size_mb": 0,
            "core_label": "нет ядра"
        }

    def _clean_core_files(self):
        for folder_name in ("libraries", "versions", "cache"):
            d = SERVER_DIR / folder_name
            if d.exists() and d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
        for item in SERVER_DIR.iterdir():
            if item.is_file():
                if (
                    item.suffix.lower() in (".jar", ".download")
                    or item.name in ("run.bat", "run.sh", "win_args.txt", "unix_args.txt", "user_jvm_args.txt")
                    or item.name.endswith("installer.jar.log")
                ):
                    item.unlink(missing_ok=True)

    def delete_server_core(self) -> Dict[str, Any]:
        with self.lock:
            if self.process and self.process.poll() is None:
                return {"success": False, "message": "Сначала остановите сервер перед удалением ядра"}
            try:
                self._clean_core_files()
                self._sync_broadcast("--- [Local MC] Старые файлы ядра и библиотек удалены из server_data ---")
                return {"success": True, "message": "Ядро сервера и библиотеки (Forge/NeoForge/Vanilla/Paper/Fabric) успешно удалены"}
            except Exception as e:
                return {"success": False, "message": f"Ошибка удаления ядра: {str(e)}"}

    def build_command(self, cfg: ServerConfig) -> List[str]:
        extra_flags = [f.strip() for f in cfg.custom_flags.split() if f.strip()]
        base_cmd = [
            cfg.java_path,
            f"-Xms{cfg.min_ram}G",
            f"-Xmx{cfg.max_ram}G",
            f"-XX:ActiveProcessorCount={cfg.cpu_cores}",
            "-Dfile.encoding=UTF-8",
            *extra_flags,
        ]
        if "forge" in cfg.engine.lower():
            forge_args = self.find_forge_args_file()
            if forge_args is not None:
                rel_args = forge_args.relative_to(SERVER_DIR)
                return [*base_cmd, f"@{rel_args}", "nogui"]

        jar_path = SERVER_DIR / cfg.server_jar
        return [*base_cmd, "-jar", str(jar_path), "nogui"]

    def start_server(self, cfg: ServerConfig) -> Dict[str, Any]:
        with self.lock:
            if self.process and self.process.poll() is None:
                return {"success": False, "message": "Сервер уже запущен"}

            # Verify Java
            java_check = self.check_java(cfg.java_path)
            if not java_check["valid"]:
                return {
                    "success": False,
                    "message": f"Java не найдена по пути '{cfg.java_path}'. Установите Java (JDK 17/21) или укажите правильный путь в настройках."
                }

            # Verify JAR or Forge args exist
            jar_path = SERVER_DIR / cfg.server_jar
            forge_args = self.find_forge_args_file() if "forge" in cfg.engine.lower() else None
            if not jar_path.exists() and forge_args is None:
                return {
                    "success": False,
                    "message": f"Файл ядра '{cfg.server_jar}' (или библиотеки Forge) не найден в server_data. Скачайте ядро через менеджер или загрузите .jar файл вручную."
                }

            if cfg.auto_eula:
                self.write_eula()

            self.update_server_properties(cfg)

            cmd = self.build_command(cfg)
            cmd_str = " ".join(cmd)
            self._sync_broadcast(f"\n--- [Local MC] Запуск сервера: {cmd_str} ---\n")

            self.status = "STARTING"
            try:
                creation_flags = 0
                if os.name == 'nt':
                    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

                self.process = subprocess.Popen(
                    cmd,
                    cwd=str(SERVER_DIR),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=creation_flags,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1
                )
                self.start_time = time.time()
                self.status = "RUNNING"

                # Start reader thread
                self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
                self.reader_thread.start()

                # Start periodic auto-save background task with configured interval
                self.autosave_interval = getattr(cfg, "autosave_interval_seconds", getattr(cfg, "autosave_interval_minutes", 15) * 60)
                if self.autosave_interval > 0:
                    self._start_autosave_task()

                return {"success": True, "message": "Сервер успешно запущен", "pid": self.process.pid}
            except Exception as e:
                self.status = "STOPPED"
                self.process = None
                self._stop_autosave_task()
                return {"success": False, "message": f"Ошибка запуска процесса: {str(e)}"}

    async def _autosave_loop(self):
        """Асинхронная фоновая задача автоматического сохранения мира."""
        try:
            while True:
                if self.autosave_interval <= 0:
                    break
                await asyncio.sleep(self.autosave_interval)

                with self.lock:
                    proc = self.process
                    is_active = (
                        proc is not None
                        and proc.poll() is None
                        and self.status in ("STARTING", "RUNNING")
                    )

                if not is_active:
                    break

                try:
                    if proc and proc.pid:
                        ps_proc = psutil.Process(proc.pid)
                        if not ps_proc.is_running():
                            break

                    if proc and proc.stdin and proc.poll() is None:
                        proc.stdin.write("save-all\n")
                        proc.stdin.flush()
                        time_str = datetime.now().strftime('%H:%M:%S')
                        say_cmd = f"say §a[Server] World saved! Time: {time_str}\n"
                        proc.stdin.write(say_cmd)
                        proc.stdin.flush()
                        self._sync_broadcast(f"[AutoSave] Автоматическое сохранение мира выполнено ({time_str})")
                except (BrokenPipeError, psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError):
                    break
                except Exception as e:
                    self._sync_broadcast(f"[AutoSave] Ошибка автосохранения: {str(e)}")
        except asyncio.CancelledError:
            pass

    def set_autosave_interval(self, seconds: int) -> Dict[str, Any]:
        if seconds < 0 or seconds > 10800:
            return {"success": False, "message": "Интервал должен быть от 0 до 10800 секунд"}

        self.autosave_interval = seconds

        with self.lock:
            is_running = self.process is not None and self.process.poll() is None and self.status in ("STARTING", "RUNNING")

        if is_running:
            if seconds > 0:
                self._start_autosave_task()
                self._sync_broadcast(f"[AutoSave] Интервал автосохранения изменен на {seconds} сек. Таймер перезапущен.")
            else:
                self._stop_autosave_task()
                self._sync_broadcast(f"[AutoSave] Автосохранение отключено.")

        return {
            "success": True,
            "seconds": self.autosave_interval,
            "message": f"Интервал автосохранения установлен на {seconds} сек."
        }

    def _start_autosave_task(self):
        self._stop_autosave_task()
        self._autosave_generation = getattr(self, '_autosave_generation', 0) + 1
        current_gen = self._autosave_generation

        def _create():
            if self.loop and self.loop.is_running() and getattr(self, '_autosave_generation', 0) == current_gen:
                if self.autosave_task and not self.autosave_task.done():
                    self.autosave_task.cancel()
                self.autosave_task = self.loop.create_task(self._autosave_loop())

        try:
            running_loop = asyncio.get_running_loop()
            if self.loop is None:
                self.loop = running_loop
            if self.autosave_task and not self.autosave_task.done():
                self.autosave_task.cancel()
            self.autosave_task = running_loop.create_task(self._autosave_loop())
        except RuntimeError:
            if self.loop and self.loop.is_running():
                self.loop.call_soon_threadsafe(_create)

    def _stop_autosave_task(self):
        self._autosave_generation = getattr(self, '_autosave_generation', 0) + 1
        task = self.autosave_task
        self.autosave_task = None
        if task is None:
            return

        def _cancel():
            if not task.done():
                task.cancel()

        try:
            asyncio.get_running_loop()
            _cancel()
        except RuntimeError:
            if self.loop and self.loop.is_running():
                self.loop.call_soon_threadsafe(_cancel)

    def _handle_console_line_for_players(self, line_str: str) -> bool:
        from app.player_service import is_valid_username

        # 1. Entity data response: "<Player> has the following entity data: {...}"
        m_data = re.search(r":\s+([A-Za-z0-9_.\-]{1,32})\s+has the following entity data:\s*(\{.*\})\s*$", line_str)
        if m_data:
            uname = m_data.group(1)
            snbt_str = m_data.group(2)
            self._entity_snbt_cache[uname.lower()] = snbt_str
            ev = self._entity_data_events.get(uname.lower())
            if ev:
                ev.set()
                return True  # Suppress internal SNBT query dump from console

        # 2. List response: "There are X of a max of Y players online: p1, p2"
        m_list = re.search(r"There are (\d+) of a max of (\d+) players online:(.*)", line_str)
        if m_list:
            raw_names = m_list.group(3).strip()
            names = [n.strip() for n in raw_names.split(",") if n.strip() and is_valid_username(n.strip())]
            with self.lock:
                updated: Dict[str, Dict[str, Any]] = {}
                for n in names:
                    existing = self.online_players.get(n) or next(
                        (v for k, v in self.online_players.items() if k.lower() == n.lower()),
                        None
                    )
                    updated[n] = existing or {
                        "name": n,
                        "joined_at": time.time(),
                        "gamemode": None,
                        "ping": 12
                    }
                self.online_players = updated
            self._list_event.set()
            if self._silent_list_pending > 0:
                self._silent_list_pending -= 1
                return True

        # 3. Player joined
        m_join = re.search(r":\s+([A-Za-z0-9_.\-]{1,32})\s+joined the game", line_str)
        if m_join:
            uname = m_join.group(1)
            if is_valid_username(uname):
                with self.lock:
                    if uname not in self.online_players:
                        self.online_players[uname] = {
                            "name": uname,
                            "joined_at": time.time(),
                            "gamemode": None,
                            "ping": 12
                        }

        # 4. Player left
        m_leave = re.search(r":\s+([A-Za-z0-9_.\-]{1,32})\s+left the game", line_str)
        if m_leave:
            uname = m_leave.group(1)
            with self.lock:
                self.online_players.pop(uname, None)
                for k in list(self.online_players.keys()):
                    if k.lower() == uname.lower():
                        self.online_players.pop(k, None)

        # 5. Gamemode change log
        m_gm = re.search(r"Set ([A-Za-z0-9_.\-]{1,32})'s game mode to ([A-Za-z]+)", line_str, re.IGNORECASE)
        m_gm_own = None
        if not m_gm:
            m_gm_own = re.search(r":\s+\[?([A-Za-z0-9_.\-]{1,32})(?::\s+|\s+)Set own game mode to ([A-Za-z]+)", line_str, re.IGNORECASE)
        m_gm_ru = None
        if not m_gm and not m_gm_own:
            m_gm_ru = re.search(r"(?:Игровой режим игрока|Установлен игровой режим для)\s+([A-Za-z0-9_.\-]{1,32}).*?(выживание|креатив|творческий|приключение|наблюдатель|спектейтор|survival|creative|adventure|spectator)", line_str, re.IGNORECASE)

        match_gm = m_gm or m_gm_own or m_gm_ru
        if match_gm:
            uname = match_gm.group(1)
            raw_gm = match_gm.group(2).strip().lower()
            if "survival" in raw_gm or "выживание" in raw_gm:
                gmode = "survival"
            elif "creative" in raw_gm or "креатив" in raw_gm or "творческий" in raw_gm:
                gmode = "creative"
            elif "adventure" in raw_gm or "приключение" in raw_gm:
                gmode = "adventure"
            elif "spectator" in raw_gm or "наблюдатель" in raw_gm or "спектейтор" in raw_gm:
                gmode = "spectator"
            else:
                gmode = "survival"
            with self.lock:
                found = False
                for k, v in self.online_players.items():
                    if k.lower() == uname.lower():
                        v["gamemode"] = gmode
                        found = True
                if not found:
                    self.online_players[uname] = {
                        "name": uname,
                        "gamemode": gmode,
                        "ping": 12,
                        "joined_at": time.time(),
                    }

        return False

    def _read_output(self):
        proc = self.process
        if not proc or not proc.stdout:
            return

        try:
            for line in proc.stdout:
                line_str = line.rstrip("\r\n")
                if "Done (" in line_str and "For help, type" in line_str:
                    self.status = "RUNNING"
                suppress = self._handle_console_line_for_players(line_str)
                if not suppress:
                    self._sync_broadcast(line_str)
        except Exception as e:
            self._sync_broadcast(f"[Local MC Manager Error]: {str(e)}")
        finally:
            if proc.stdout:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
            with self.lock:
                self.status = "STOPPED"
                self.process = None
                self.online_players.clear()
                self._stop_autosave_task()
                self._sync_broadcast("--- [Local MC] Процесс сервера остановлен ---\n")

    def send_silent_command(self, command: str) -> bool:
        with self.lock:
            if not self.process or self.process.poll() is not None or not self.process.stdin:
                return False
            try:
                clean_cmd = command.strip()
                self.process.stdin.write(clean_cmd + "\n")
                self.process.stdin.flush()
                return True
            except Exception:
                return False

    def send_command(self, command: str) -> Dict[str, Any]:
        with self.lock:
            if not self.process or self.process.poll() is not None:
                return {"success": False, "message": "Сервер не запущен"}

            try:
                clean_cmd = command.strip()
                if self.process.stdin:
                    self.process.stdin.write(clean_cmd + "\n")
                    self.process.stdin.flush()
                    if clean_cmd.lower() == "save-all":
                        time_str = datetime.now().strftime('%H:%M:%S')
                        self.process.stdin.write(f"say §a[Server] World saved! Time: {time_str}\n")
                        self.process.stdin.flush()
                        self._sync_broadcast(f"[AutoSave] Сохранение мира выполнено ({time_str})")
                    self._sync_broadcast(f"> {clean_cmd}")
                    return {"success": True, "message": "Команда отправлена"}
                else:
                    return {"success": False, "message": "Поток stdin недоступен"}
            except Exception as e:
                return {"success": False, "message": f"Ошибка отправки команды: {str(e)}"}

    # ---------------- PLAYERS MANAGEMENT ----------------
    def get_players_list(self, force_refresh: bool = False) -> Dict[str, Any]:
        import nbtlib
        from app.config import load_config
        from app.player_service import (
            load_usercache,
            parse_nbt_to_player_data,
            read_player_data_from_disk,
            resolve_player_uuid,
        )

        cfg = load_config()
        is_running = self.process is not None and self.process.poll() is None

        if is_running and self.status == "RUNNING":
            now = time.time()
            if force_refresh or (now - self._last_list_query > 3.5):
                self._list_event.clear()
                self._silent_list_pending += 1
                self._last_list_query = now
                if self.send_silent_command("list"):
                    self._list_event.wait(timeout=0.35)
                else:
                    self._silent_list_pending = max(0, self._silent_list_pending - 1)

        with self.lock:
            online_snapshot = dict(self.online_players)

        online_list: List[Dict[str, Any]] = []
        online_names_lower = set()

        for uname, meta in online_snapshot.items():
            online_names_lower.add(uname.lower())
            uuid_str = resolve_player_uuid(uname)

            # Use cached live SNBT if available, otherwise disk playerdata
            snbt_raw = self._entity_snbt_cache.get(uname.lower())
            pdata = None
            if snbt_raw:
                try:
                    nbt_root = nbtlib.parse_nbt(snbt_raw)
                    pdata = parse_nbt_to_player_data(uname, uuid_str, nbt_root, source="live_console")
                except Exception:
                    pdata = None
            if pdata is None:
                pdata = read_player_data_from_disk(uname)

            has_nbt = pdata is not None
            gm = meta.get("gamemode") or (pdata.get("gamemode") if pdata else None) or cfg.gamemode or "survival"
            inv_obj = (pdata.get("inventory") if pdata else None) or {}
            online_list.append({
                "name": uname,
                "uuid": uuid_str,
                "online": True,
                "gamemode": gm,
                "has_nbt": has_nbt,
                "health": pdata.get("health") if pdata else None,
                "max_health": pdata.get("max_health", 20.0) if pdata else 20.0,
                "food": pdata.get("food") if pdata else None,
                "max_food": pdata.get("max_food", 20) if pdata else 20,
                "xp_level": pdata.get("xp_level") if pdata else None,
                "dimension": pdata.get("dimension") if pdata else None,
                "position": pdata.get("position") if pdata else None,
                "inventory_count": inv_obj.get("total_items", 0) if isinstance(inv_obj, dict) else 0,
                "ping": meta.get("ping", 12),
                "avatar_url": f"/api/players/{uname}/avatar",
            })

        # Also gather known offline players ONLY if their real .dat file exists in world/playerdata
        offline_list: List[Dict[str, Any]] = []
        seen_offline = set()
        playerdata_dir = SERVER_DIR / "world" / "playerdata"

        if playerdata_dir.exists() and playerdata_dir.is_dir():
            uuid_to_name: Dict[str, str] = {}
            for entry in load_usercache():
                u = str(entry.get("uuid", "")).strip().lower()
                n = str(entry.get("name", "")).strip()
                if u and n:
                    uuid_to_name[u] = n

            for dat_file in sorted(playerdata_dir.glob("*.dat")):
                raw_stem = dat_file.stem.lower()
                uname = uuid_to_name.get(raw_stem)
                if not uname:
                    for entry in load_usercache():
                        if str(entry.get("name", "")).lower() == raw_stem:
                            uname = str(entry["name"])
                            break
                    if not uname:
                        uname = raw_stem

                if uname.lower() in online_names_lower or uname.lower() in seen_offline:
                    continue
                seen_offline.add(uname.lower())

                pdata = read_player_data_from_disk(uname)
                if not pdata:
                    continue

                inv_obj = pdata.get("inventory") or {}
                offline_list.append({
                    "name": uname,
                    "uuid": pdata.get("uuid") or raw_stem,
                    "online": False,
                    "gamemode": pdata.get("gamemode") or cfg.gamemode or "survival",
                    "has_nbt": True,
                    "health": pdata.get("health"),
                    "max_health": pdata.get("max_health", 20.0),
                    "food": pdata.get("food"),
                    "max_food": pdata.get("max_food", 20),
                    "xp_level": pdata.get("xp_level"),
                    "dimension": pdata.get("dimension"),
                    "position": pdata.get("position"),
                    "inventory_count": inv_obj.get("total_items", 0) if isinstance(inv_obj, dict) else 0,
                    "ping": 0,
                    "avatar_url": f"/api/players/{uname}/avatar",
                })

        return {
            "is_running": is_running,
            "server_running": is_running,
            "online_count": len(online_list),
            "total_known": len(online_list) + len(offline_list),
            "max_players": cfg.max_players,
            "players": online_list,
            "online": online_list,
            "offline_players": offline_list,
            "offline": offline_list,
        }

    def get_player_detailed_data(self, username: str) -> Dict[str, Any]:
        import nbtlib
        from app.player_service import (
            is_valid_username,
            parse_nbt_to_player_data,
            read_player_data_from_disk,
            resolve_player_uuid,
            default_player_data,
        )

        if not is_valid_username(username):
            raise ValueError("Некорректное имя игрока")

        uname_lower = username.lower()
        uuid_str = resolve_player_uuid(username)
        is_running = self.process is not None and self.process.poll() is None

        with self.lock:
            is_online = any(k.lower() == uname_lower for k in self.online_players)
            tracked_meta = next((v for k, v in self.online_players.items() if k.lower() == uname_lower), None)

        # If server is running and player is online, query live entity NBT via console
        if is_running and is_online:
            ev = threading.Event()
            self._entity_data_events[uname_lower] = ev
            if self.send_silent_command(f"data get entity {username}"):
                ev.wait(timeout=0.7)
            self._entity_data_events.pop(uname_lower, None)

        snbt_raw = self._entity_snbt_cache.get(uname_lower) if is_online else None
        pdata = None
        if snbt_raw:
            try:
                nbt_root = nbtlib.parse_nbt(snbt_raw)
                pdata = parse_nbt_to_player_data(username, uuid_str, nbt_root, source="live_console")
            except Exception:
                pdata = None

        if pdata is None:
            pdata = read_player_data_from_disk(username)

        if pdata is None:
            pdata = default_player_data(username, uuid_str)

        if tracked_meta and tracked_meta.get("gamemode"):
            pdata["gamemode"] = tracked_meta["gamemode"]

        pdata["online"] = is_online
        pdata["ping"] = tracked_meta.get("ping", 12) if is_online and tracked_meta else 0
        pdata["avatar_url"] = f"/api/players/{username}/avatar"
        return pdata

    def execute_player_action(
        self,
        action: str,
        player: str,
        target: Optional[Union[str, int]] = None,
        mode: Optional[Union[str, int]] = None,
        reason: Optional[Union[str, int]] = None,
        value: Optional[Union[str, int]] = None
    ) -> Dict[str, Any]:
        from app.player_service import is_valid_username, resolve_player_uuid

        if not is_valid_username(player):
            return {"success": False, "message": "Некорректное имя игрока"}

        if not self.process or self.process.poll() is not None:
            return {"success": False, "message": "Сервер должен быть запущен для выполнения этого действия"}

        act = (action or "").strip().lower()

        if act == "gamemode":
            allowed_modes = {"survival", "creative", "adventure", "spectator"}
            gamemode_aliases = {
                "survival": "survival",
                "0": "survival",
                "s": "survival",
                "surv": "survival",
                "выживание": "survival",
                "режим выживания": "survival",
                "creative": "creative",
                "1": "creative",
                "c": "creative",
                "creat": "creative",
                "креатив": "creative",
                "режим креатива": "creative",
                "творческий": "creative",
                "режим творчества": "creative",
                "adventure": "adventure",
                "2": "adventure",
                "a": "adventure",
                "adv": "adventure",
                "приключение": "adventure",
                "режим приключения": "adventure",
                "spectator": "spectator",
                "3": "spectator",
                "sp": "spectator",
                "spec": "spectator",
                "spectate": "spectator",
                "наблюдатель": "spectator",
                "режим наблюдателя": "spectator",
                "спектейтор": "spectator"
            }
            gamemode_to_id = {
                "survival": 0,
                "creative": 1,
                "adventure": 2,
                "spectator": 3,
            }
            raw_mode = mode if (mode is not None and str(mode).strip()) else value
            clean_raw = str(raw_mode).strip().lower() if raw_mode is not None else ""
            clean_mode = gamemode_aliases.get(clean_raw, clean_raw)
            if clean_mode not in allowed_modes:
                return {"success": False, "message": f"Недопустимый режим игры: {raw_mode}"}

            res = self.send_command(f"gamemode {clean_mode} {player}")
            if res.get("success"):
                with self.lock:
                    for k, v in self.online_players.items():
                        if k.lower() == player.lower():
                            v["gamemode"] = clean_mode

                # Also update player's .dat file on disk if it exists
                try:
                    uuid_str = resolve_player_uuid(player)
                    playerdata_dir = SERVER_DIR / "world" / "playerdata"
                    dat_file = playerdata_dir / f"{uuid_str}.dat"
                    if dat_file.exists():
                        import nbtlib
                        nbt_file = nbtlib.load(dat_file)
                        root = nbt_file.root if hasattr(nbt_file, "root") else nbt_file
                        root["playerGameType"] = nbtlib.Int(gamemode_to_id[clean_mode])
                        nbt_file.save()
                except Exception:
                    pass

                return {"success": True, "message": f"Режим игрока {player} изменен на {clean_mode.capitalize()}"}
            return res

        elif act == "teleport":
            target_player = target if (target is not None and str(target).strip()) else value
            if not target_player or not is_valid_username(str(target_player)):
                return {"success": False, "message": "Некорректное имя целевого игрока для телепортации"}
            res = self.send_command(f"tp {player} {target_player}")
            if res.get("success"):
                return {"success": True, "message": f"Игрок {player} телепортирован к {target_player}"}
            return res

        elif act == "kick":
            raw_reason = reason if (reason is not None and str(reason).strip()) else value
            kick_reason = str(raw_reason).strip() if raw_reason is not None and str(raw_reason).strip() else "Исключен администратором сервера"
            safe_reason = re.sub(r"[\r\n;]", " ", kick_reason).strip()[:80]
            res = self.send_command(f"kick {player} {safe_reason}")
            if res.get("success"):
                return {"success": True, "message": f"Игрок {player} кикнут с сервера"}
            return res

        elif act == "heal":
            res1 = self.send_command(f"effect give {player} minecraft:instant_health 1 10 true")
            self.send_command(f"effect give {player} minecraft:saturation 1 10 true")
            if res1.get("success"):
                return {"success": True, "message": f"Здоровье и сытость игрока {player} восстановлены"}
            return res1

        return {"success": False, "message": f"Неизвестное действие: {action}"}

    def stop_server(self, timeout: int = 15) -> Dict[str, Any]:
        self._stop_autosave_task()
        with self.lock:
            if not self.process or self.process.poll() is not None:
                self.status = "STOPPED"
                return {"success": True, "message": "Сервер уже остановлен"}

            self.status = "STOPPING"
            self._sync_broadcast("--- [Local MC] Отправка команды 'stop' серверу... ---")

        # Send stop command outside lock
        try:
            if self.process and self.process.stdin:
                self.process.stdin.write("stop\n")
                self.process.stdin.flush()
        except Exception:
            pass

        def waiter():
            start_wait = time.time()
            while time.time() - start_wait < timeout:
                if self.process is None or self.process.poll() is not None:
                    return
                time.sleep(0.5)

            if self.process and self.process.poll() is None:
                self._sync_broadcast("--- [Local MC] Время ожидания истекло, принудительное завершение... ---")
                try:
                    parent = psutil.Process(self.process.pid)
                    for child in parent.children(recursive=True):
                        try:
                            child.terminate()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    parent.terminate()
                except Exception:
                    try:
                        self.process.terminate()
                    except Exception:
                        pass

        threading.Thread(target=waiter, daemon=True).start()
        return {"success": True, "message": "Команда остановки отправлена"}

    def kill_server(self) -> Dict[str, Any]:
        self._stop_autosave_task()
        with self.lock:
            if not self.process or self.process.poll() is not None:
                self.status = "STOPPED"
                return {"success": True, "message": "Сервер не запущен"}

            try:
                try:
                    parent = psutil.Process(self.process.pid)
                    for child in parent.children(recursive=True):
                        try:
                            child.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    parent.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    self.process.kill()

                self._proc_cache.clear()
                self._sync_broadcast("--- [Local MC] Сервер принудительно убит (SIGKILL) ---")
                self.status = "STOPPED"
                self.process = None
                return {"success": True, "message": "Сервер принудительно остановлен"}
            except Exception as e:
                return {"success": False, "message": f"Ошибка принудительной остановки: {str(e)}"}

    def restart_server(self, cfg: ServerConfig) -> Dict[str, Any]:
        if self.process and self.process.poll() is None:
            self.status = "RESTARTING"
            self.stop_server(timeout=10)

            def restart_worker():
                for _ in range(30):
                    if self.process is None or self.process.poll() is not None:
                        break
                    time.sleep(0.5)
                time.sleep(1)
                self.start_server(cfg)

            threading.Thread(target=restart_worker, daemon=True).start()
            return {"success": True, "message": "Перезапуск инициирован"}
        else:
            return self.start_server(cfg)

    def graceful_shutdown(self, timeout: int = 15) -> Dict[str, Any]:
        """Плавная синхронная остановка сервера при закрытии веб-панели."""
        self._stop_metrics_worker()
        self._stop_autosave_task()

        with self.lock:
            proc = self.process
            if not proc or proc.poll() is not None:
                self.status = "STOPPED"
                self.process = None
                return {"success": True, "message": "Сервер уже остановлен"}

            self.status = "STOPPING"
            self._sync_broadcast("--- [Local MC] Завершение работы веб-панели. Остановка сервера Minecraft... ---")

        # Send stop command to server stdin
        try:
            if proc.stdin and proc.poll() is None:
                proc.stdin.write("stop\n")
                proc.stdin.flush()
        except Exception:
            pass

        # Synchronously wait for process exit
        start_wait = time.time()
        while time.time() - start_wait < timeout:
            if proc.poll() is not None:
                break
            time.sleep(0.3)

        # Force terminate if still running to guarantee port 25565 release
        if proc.poll() is None:
            self._sync_broadcast("--- [Local MC] Время ожидания истекло, принудительное завершение зависшего процесса... ---")
            try:
                parent = psutil.Process(proc.pid)
                for child in parent.children(recursive=True):
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                parent.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                try:
                    proc.kill()
                except Exception:
                    pass

        with self.lock:
            self.status = "STOPPED"
            self.process = None
            self._proc_cache.clear()
            self.online_players.clear()
            self.last_stats = {
                "cpu_percent": 0.0,
                "memory_mb": 0.0,
                "memory_str": "0 MB",
                "memory_percent": 0.0,
                "uptime_seconds": 0
            }

        return {"success": True, "message": "Сервер Minecraft штатно остановлен"}

    # ---------------- MODS & PLUGINS ----------------
    def get_target_addon_dir(self, engine: str) -> Path:
        engine_lower = engine.lower()
        if "paper" in engine_lower or "spigot" in engine_lower or "purpur" in engine_lower:
            target = SERVER_DIR / "plugins"
        else:
            target = SERVER_DIR / "mods"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def list_addons(self, engine: str) -> Dict[str, Any]:
        target = self.get_target_addon_dir(engine)
        folder_type = "plugins" if target.name == "plugins" else "mods"
        items = []

        if target.exists():
            for p in target.iterdir():
                if p.is_file() and (p.suffix.lower() == ".jar" or p.name.endswith(".jar.disabled")):
                    size_kb = round(p.stat().st_size / 1024, 1)
                    size_mb = round(p.stat().st_size / (1024 * 1024), 2)
                    size_str = f"{size_mb} MB" if size_mb >= 1.0 else f"{size_kb} KB"
                    items.append({
                        "filename": p.name,
                        "size_str": size_str,
                        "size_bytes": p.stat().st_size,
                        "enabled": not p.name.endswith(".disabled"),
                        "mtime": int(p.stat().st_mtime)
                    })

        items.sort(key=lambda x: x["filename"].lower())
        return {"folder": folder_type, "path": str(target), "items": items}

    def delete_addon(self, engine: str, filename: str) -> bool:
        target = self.get_target_addon_dir(engine)
        file_path = (target / filename).resolve()
        if target.resolve() in file_path.parents and file_path.exists():
            file_path.unlink()
            return True
        return False

    def toggle_addon(self, engine: str, filename: str) -> Dict[str, Any]:
        target = self.get_target_addon_dir(engine)
        file_path = (target / filename).resolve()
        if not (target.resolve() in file_path.parents and file_path.exists()):
            return {"success": False, "message": "Файл не найден"}

        if filename.endswith(".disabled"):
            new_name = filename[:-9]
        else:
            new_name = filename + ".disabled"

        new_path = target / new_name
        file_path.rename(new_path)
        return {"success": True, "new_filename": new_name}

    # ---------------- VERSIONS FETCHER ----------------
    def get_available_versions(self, engine: str) -> List[str]:
        engine_lower = engine.lower()
        now = time.time()
        
        # Check cache
        if engine_lower in VERSION_CACHE:
            cached = VERSION_CACHE[engine_lower]
            if now - cached["timestamp"] < CACHE_TTL:
                return cached["versions"]

        versions = []
        try:
            if "vanilla" in engine_lower:
                req = urllib.request.Request(
                    "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    versions = [v["id"] for v in data.get("versions", []) if v.get("type") == "release"]

            elif "paper" in engine_lower:
                req = urllib.request.Request(
                    "https://api.purpurmc.org/v2/purpur",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    raw_vers = data.get("versions", [])
                    versions = list(reversed(raw_vers))

            elif "fabric" in engine_lower:
                req = urllib.request.Request(
                    "https://meta.fabricmc.net/v2/versions/game",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    versions = [x["version"] for x in data if x.get("stable")]

            elif "neoforge" in engine_lower:
                req = urllib.request.Request(
                    "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    nf_vers = data.get("versions", [])
                    mc_list = []
                    for v in nf_vers:
                        parts = v.split(".")
                        if len(parts) >= 2 and parts[0] in ("20", "21") and parts[1].isdigit():
                            mc_v = f"1.{parts[0]}" if parts[1] == "0" else f"1.{parts[0]}.{parts[1]}"
                            if mc_v not in mc_list:
                                mc_list.append(mc_v)
                    versions = list(reversed(mc_list))
                    if "1.20.1" not in versions:
                        versions.append("1.20.1")

            elif "forge" in engine_lower:
                # Mojang releases filtered
                versions = FALLBACK_VERSIONS

        except Exception as e:
            pass

        if not versions:
            if "neoforge" in engine_lower:
                versions = ["1.21.4", "1.21.3", "1.21.1", "1.21", "1.20.6", "1.20.4", "1.20.2", "1.20.1"]
            else:
                versions = FALLBACK_VERSIONS

        VERSION_CACHE[engine_lower] = {
            "timestamp": now,
            "versions": versions
        }
        return versions

    # ---------------- JAR DOWNLOADER ----------------
    def download_server_jar(self, engine: str, version: str) -> Dict[str, Any]:
        if self.download_progress["is_downloading"]:
            return {"success": False, "message": "Загрузка уже выполняется"}

        def download_task():
            self.download_progress["is_downloading"] = True
            self.download_progress["status"] = "starting"
            self.download_progress["percent"] = 5
            self.download_progress["message"] = f"Поиск ядра {engine} {version}..."
            self._sync_broadcast(f"\n--- [Local MC] Начало загрузки ядра {engine} {version} ---")

            try:
                dest = SERVER_DIR / "server.jar"
                engine_lower = engine.lower()

                # Clean old core files before installing the new core
                self._clean_core_files()

                if "vanilla" in engine_lower:
                    req = urllib.request.Request(
                        "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json",
                        headers={"User-Agent": "LocalMCManager/1.0"}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        manifest = json.loads(resp.read().decode("utf-8"))

                    ver_info = next((v for v in manifest["versions"] if v["id"] == version), None)
                    if not ver_info:
                        raise ValueError(f"Версия Minecraft {version} не найдена в манифесте Mojang")

                    self.download_progress["percent"] = 25
                    self.download_progress["message"] = f"Получение ссылки для Vanilla {version}..."

                    req_v = urllib.request.Request(ver_info["url"], headers={"User-Agent": "LocalMCManager/1.0"})
                    with urllib.request.urlopen(req_v, timeout=10) as resp:
                        v_data = json.loads(resp.read().decode("utf-8"))

                    server_download = v_data.get("downloads", {}).get("server")
                    if not server_download or "url" not in server_download:
                        raise ValueError(f"Для версии {version} нет официального серверного JAR")

                    jar_url = server_download["url"]
                    self._download_file(jar_url, dest, "Vanilla Server")

                elif "paper" in engine_lower:
                    self.download_progress["percent"] = 20
                    self.download_progress["message"] = f"Запрос Purpur/Paper для {version}..."
                    purpur_url = f"https://api.purpurmc.org/v2/purpur/{version}/latest/download"
                    self._download_file(purpur_url, dest, f"Paper/Purpur {version}")

                elif "fabric" in engine_lower:
                    self.download_progress["percent"] = 20
                    self.download_progress["message"] = f"Поиск загрузчика Fabric для {version}..."
                    req = urllib.request.Request(
                        f"https://meta.fabricmc.net/v2/versions/loader/{version}",
                        headers={"User-Agent": "LocalMCManager/1.0"}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        loaders = json.loads(resp.read().decode("utf-8"))

                    if not loaders:
                        raise ValueError(f"Fabric не поддерживает версию Minecraft {version}")

                    loader_ver = loaders[0]["loader"]["version"]
                    installer_ver = "1.0.1"
                    jar_url = f"https://meta.fabricmc.net/v2/versions/loader/{version}/{loader_ver}/{installer_ver}/server/jar"
                    self._download_file(jar_url, dest, f"Fabric Server {version}")

                elif "neoforge" in engine_lower:
                    self.download_progress["percent"] = 15
                    self.download_progress["message"] = f"Поиск версии NeoForge для {version}..."

                    if version == "1.20.1":
                        api_url = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/forge"
                        req = urllib.request.Request(api_url, headers={"User-Agent": "LocalMCManager/1.0"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            vers = json.loads(resp.read().decode("utf-8")).get("versions", [])
                        matches = [v for v in vers if v.startswith("1.20.1-")]
                        if not matches:
                            raise ValueError("NeoForge для 1.20.1 не найден в репозитории")
                        nf_ver = matches[-1]
                        installer_url = f"https://maven.neoforged.net/releases/net/neoforged/forge/{nf_ver}/forge-{nf_ver}-installer.jar"
                    else:
                        api_url = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
                        req = urllib.request.Request(api_url, headers={"User-Agent": "LocalMCManager/1.0"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            vers = json.loads(resp.read().decode("utf-8")).get("versions", [])

                        if version.startswith("1."):
                            parts = version.split(".")
                            prefix = f"{parts[1]}.0." if len(parts) == 2 else f"{parts[1]}.{parts[2]}."
                            matches = [v for v in vers if v.startswith(prefix)]
                            if not matches:
                                raise ValueError(f"NeoForge не поддерживает версию Minecraft {version}")
                            stable = [v for v in matches if "beta" not in v]
                            nf_ver = (stable or matches)[-1]
                        else:
                            # Direct NeoForge version provided
                            nf_ver = version

                        installer_url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{nf_ver}/neoforge-{nf_ver}-installer.jar"

                    installer_path = SERVER_DIR / "neoforge-installer.jar"
                    self._download_file(installer_url, installer_path, f"NeoForge Installer {nf_ver}")
                    self.download_progress["percent"] = 85
                    self.download_progress["message"] = f"Установка NeoForge {nf_ver} (--installServer)..."
                    self._sync_broadcast(f"--- [Local MC] Запуск установки NeoForge {nf_ver} (--installServer)... ---")

                    from app.config import load_config
                    java_exec = load_config().java_path or "java"
                    proc = subprocess.Popen(
                        [java_exec, "-jar", str(installer_path), "--installServer"],
                        cwd=str(SERVER_DIR),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace"
                    )
                    if proc.stdout:
                        for line in proc.stdout:
                            line_str = line.rstrip("\r\n")
                            if line_str:
                                self._sync_broadcast(f"[NeoForge Installer] {line_str}")
                    proc.wait()

                    installer_path.unlink(missing_ok=True)
                    (SERVER_DIR / "neoforge-installer.jar.log").unlink(missing_ok=True)

                    if proc.returncode != 0:
                        raise ValueError(f"Ошибка установки NeoForge (код возврата {proc.returncode})")

                elif "forge" in engine_lower:
                    self.download_progress["percent"] = 15
                    self.download_progress["message"] = f"Поиск версии Forge для {version}..."
                    req = urllib.request.Request(
                        "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json",
                        headers={"User-Agent": "LocalMCManager/1.0"}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        promos_data = json.loads(resp.read().decode("utf-8")).get("promos", {})

                    forge_ver = promos_data.get(f"{version}-recommended") or promos_data.get(f"{version}-latest")
                    if not forge_ver:
                        raise ValueError(f"Forge не найден для версии Minecraft {version}")

                    full_ver = f"{version}-{forge_ver}"
                    installer_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{full_ver}/forge-{full_ver}-installer.jar"
                    installer_path = SERVER_DIR / "forge-installer.jar"

                    self._download_file(installer_url, installer_path, f"Forge Installer {full_ver}")
                    self.download_progress["percent"] = 85
                    self.download_progress["message"] = f"Установка Forge {full_ver} (--installServer)..."
                    self._sync_broadcast(f"--- [Local MC] Запуск установки Forge {full_ver} (--installServer)... ---")

                    from app.config import load_config
                    java_exec = load_config().java_path or "java"
                    proc = subprocess.Popen(
                        [java_exec, "-jar", str(installer_path), "--installServer"],
                        cwd=str(SERVER_DIR),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace"
                    )
                    if proc.stdout:
                        for line in proc.stdout:
                            line_str = line.rstrip("\r\n")
                            if line_str:
                                self._sync_broadcast(f"[Forge Installer] {line_str}")
                    proc.wait()

                    installer_path.unlink(missing_ok=True)
                    (SERVER_DIR / "forge-installer.jar.log").unlink(missing_ok=True)

                    if proc.returncode != 0:
                        raise ValueError(f"Ошибка установки Forge (код возврата {proc.returncode})")

                    # For older Forge (<=1.16.5) that generates a universal/forge jar in root, rename to server.jar
                    if self.find_forge_args_file() is None and not dest.exists():
                        for candidate in SERVER_DIR.glob("forge-*.jar"):
                            if "installer" not in candidate.name.lower():
                                candidate.rename(dest)
                                break

                else:
                    raise ValueError(f"Неизвестный тип ядра: {engine}")

                self.download_progress["status"] = "done"
                self.download_progress["percent"] = 100
                self.download_progress["message"] = f"Ядро {engine} {version} успешно установлено!"
                self._sync_broadcast(f"--- [Local MC] Ядро {engine} {version} успешно установлено! ---")

            except Exception as e:
                self.download_progress["status"] = "error"
                self.download_progress["message"] = str(e)
                self._sync_broadcast(f"[Local MC Ошибка загрузки]: {str(e)}")
            finally:
                self.download_progress["is_downloading"] = False

        threading.Thread(target=download_task, daemon=True).start()
        return {"success": True, "message": "Загрузка запущена в фоновом режиме"}

    def _download_file(self, url: str, dest_path: Path, name: str):
        req = urllib.request.Request(url, headers={"User-Agent": "LocalMCManager/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total_size = int(resp.headers.get("content-length", 0))
            chunk_size = 64 * 1024
            downloaded = 0
            temp_path = dest_path.with_suffix(".download")

            with open(temp_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = int(25 + (downloaded / total_size) * 70)
                        self.download_progress["percent"] = min(pct, 98)
                        mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        self.download_progress["message"] = f"Загрузка {name}: {mb:.1f}/{total_mb:.1f} MB ({pct}%)"

            if dest_path.exists():
                dest_path.unlink()
            temp_path.rename(dest_path)


    def delete_world(self) -> Dict[str, Any]:
        world_dir = SERVER_DIR / "world"
        if world_dir.exists():
            try:
                shutil.rmtree(world_dir)
                return {"success": True, "message": "Мир успешно удален"}
            except Exception as e:
                return {"success": False, "message": f"Ошибка удаления мира: {str(e)}"}
        return {"success": True, "message": "Папка мира не существует"}

    def upload_world(self, zip_path: Path) -> Dict[str, Any]:
        world_dir = SERVER_DIR / "world"
        temp_extract = SERVER_DIR / "temp_world_extract"
        
        if temp_extract.exists():
            shutil.rmtree(temp_extract)
        
        try:
            import zipfile
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract)
            
            # Find level.dat
            level_dat_path = None
            for root, dirs, files in os.walk(temp_extract):
                if "level.dat" in files:
                    level_dat_path = Path(root)
                    break
            
            if not level_dat_path:
                shutil.rmtree(temp_extract)
                return {"success": False, "message": "В архиве не найден файл level.dat. Это не похоже на сохранение мира Minecraft."}
            
            # Delete old world
            if world_dir.exists():
                shutil.rmtree(world_dir)
                
            # Move the correct folder to 'world'
            shutil.move(str(level_dat_path), str(world_dir))
            
            # Cleanup
            if temp_extract.exists():
                shutil.rmtree(temp_extract)
                
            return {"success": True, "message": "Мир успешно загружен и установлен"}
        except Exception as e:
            if temp_extract.exists():
                shutil.rmtree(temp_extract)
            return {"success": False, "message": f"Ошибка распаковки мира: {str(e)}"}

server_manager = ServerManager()

