import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

SCREENSHOT_DIR = BASE_DIR / "docs" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HOST = "127.0.0.1"
PORT = 8765
CDP_PORT = 9333


def build_mock_server_script():
    script_path = BASE_DIR / "scripts" / "_screenshot_server.py"
    code = '''import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.main import app
import app.config as app_config_module
from app.config import ServerConfig
from app.server_manager import server_manager
import uvicorn

# Set Paper 1.20.4 config
mock_cfg = ServerConfig(
    engine="Paper",
    version="1.20.4",
    min_ram=4,
    max_ram=8,
    cpu_threads=4,
    view_distance=10,
    allow_flight=True,
    server_port=25565,
    java_path="java",
    autosave_interval_seconds=900
)
app_config_module.load_config = lambda: mock_cfg

# Set active server state to Paper 1.20.4 Running
server_manager.status = "RUNNING"
server_manager.get_status = lambda: {
    "status": "RUNNING",
    "is_running": True,
    "installed": True,
    "has_core": True,
    "core_installed": True,
    "stats": {
        "cpu_percent": 14.8,
        "memory_mb": 3840.0,
        "memory_str": "3,840 MB",
        "memory_percent": 24.0,
        "uptime_seconds": 15502
    }
}
server_manager.get_installed_core_info = lambda cfg: {
    "installed": True,
    "has_core": True,
    "core_installed": True,
    "jar_name": "paper-1.20.4-496.jar",
    "size_mb": 48.2
}

logs = [
    "[14:00:01 INFO]: Loading Minecraft Simple Server v2.0.0...",
    "[14:00:02 INFO]: Starting minecraft server version 1.20.4 (Paper)",
    "[14:00:03 INFO]: Loading properties from server.properties",
    "[14:00:03 INFO]: Default game type: SURVIVAL, view-distance: 10, allow-flight: true",
    "[14:00:04 INFO]: Generating keypair...",
    "[14:00:05 INFO]: Starting Minecraft server on *:25565",
    "[14:00:06 INFO]: [Vault] Enabling Vault v1.7.3-b131",
    "[14:00:06 INFO]: [LuckPerms] Loading configuration & permissions database...",
    "[14:00:07 INFO]: [WorldEdit] WorldEdit v7.2.15 enabled.",
    "[14:00:07 INFO]: [Essentials] Using standard NBT player data",
    "[14:00:08 INFO]: Preparing level 'world' (Overworld)...",
    "[14:00:09 INFO]: Preparing spawn area: 100% complete",
    "[14:00:10 INFO]: Time elapsed: 1845 ms",
    "[14:00:10 INFO]: Done (4.215s)! For help, type 'help'",
    "[14:00:35 INFO]: McDemon[/127.0.0.1:54321] logged in with entity id 142 at (184.5, 68.0, -212.3)",
    "[14:00:36 INFO]: <McDemon> Server performance is ultra-smooth, zero lag!",
    "[14:01:02 INFO]: Auto-saving world chunks to disk (0.04s)...",
]
server_manager.log_history.extend(logs)

# Mock get_players_list
def mock_get_players_list(refresh=False):
    return {
        "is_running": True,
        "server_running": True,
        "online_count": 1,
        "total_known": 2,
        "max_players": 20,
        "players": [
            {
                "name": "McDemon",
                "uuid": "5e8052fb-4874-383d-a3f8-53d8c7bc1dac",
                "online": True,
                "gamemode": "survival",
                "has_nbt": True,
                "health": 20.0,
                "max_health": 20.0,
                "food": 20,
                "max_food": 20,
                "xp_level": 42,
                "dimension": "minecraft:overworld",
                "position": [184.5, 68.0, -212.3],
                "inventory_count": 24,
                "ping": 18,
                "avatar_url": "/api/players/McDemon/avatar"
            }
        ],
        "online": [
            {
                "name": "McDemon",
                "uuid": "5e8052fb-4874-383d-a3f8-53d8c7bc1dac",
                "online": True,
                "gamemode": "survival",
                "has_nbt": True,
                "health": 20.0,
                "max_health": 20.0,
                "food": 20,
                "max_food": 20,
                "xp_level": 42,
                "dimension": "minecraft:overworld",
                "position": [184.5, 68.0, -212.3],
                "inventory_count": 24,
                "ping": 18,
                "avatar_url": "/api/players/McDemon/avatar"
            }
        ],
        "offline_players": [
            {
                "name": "Dragomir",
                "uuid": "b3f742cf-8ee7-3b5a-a153-416cbfcf6f7a",
                "online": False,
                "gamemode": "survival",
                "has_nbt": True,
                "health": 18.0,
                "max_health": 20.0,
                "food": 16,
                "max_food": 20,
                "xp_level": 15,
                "dimension": "minecraft:overworld",
                "position": [0, 64, 0],
                "inventory_count": 10,
                "ping": 0,
                "avatar_url": "/api/players/Dragomir/avatar"
            }
        ],
        "offline": []
    }
server_manager.get_players_list = mock_get_players_list

# Mock get_player_detailed_data
def mock_get_player_detailed_data(username):
    return {
        "name": username,
        "uuid": "5e8052fb-4874-383d-a3f8-53d8c7bc1dac",
        "online": True,
        "gamemode": "survival",
        "health": 20.0,
        "max_health": 20.0,
        "food": 20,
        "max_food": 20,
        "xp_level": 42,
        "dimension": "minecraft:overworld",
        "position": [184.5, 68.0, -212.3],
        "ping": 18,
        "inventory": {
            "total_items": 24,
            "armor": {
                "helmet": {"id": "minecraft:netherite_helmet", "name": "Netherite Helmet", "count": 1, "damage": 18, "max_damage": 407, "durability_percent": 95},
                "chestplate": {"id": "minecraft:netherite_chestplate", "name": "Netherite Chestplate", "count": 1, "damage": 50, "max_damage": 592, "durability_percent": 91},
                "leggings": {"id": "minecraft:netherite_leggings", "name": "Netherite Leggings", "count": 1, "damage": 24, "max_damage": 555, "durability_percent": 95},
                "boots": {"id": "minecraft:netherite_boots", "name": "Netherite Boots", "count": 1, "damage": 12, "max_damage": 481, "durability_percent": 97}
            },
            "offhand": {"id": "minecraft:shield", "name": "Shield", "count": 1, "damage": 10, "max_damage": 336, "durability_percent": 97},
            "hotbar": [
                {"id": "minecraft:netherite_sword", "name": "Netherite Sword", "count": 1, "damage": 46, "max_damage": 2031, "durability_percent": 97},
                {"id": "minecraft:netherite_pickaxe", "name": "Netherite Pickaxe", "count": 1, "damage": 85, "max_damage": 2031, "durability_percent": 95},
                {"id": "minecraft:netherite_axe", "name": "Netherite Axe", "count": 1, "damage": 30, "max_damage": 2031, "durability_percent": 98},
                {"id": "minecraft:golden_apple", "name": "Golden Apple", "count": 32},
                {"id": "minecraft:cooked_beef", "name": "Cooked Beef", "count": 64},
                {"id": "minecraft:firework_rocket", "name": "Firework Rocket", "count": 64},
                {"id": "minecraft:totem_of_undying", "name": "Totem of Undying", "count": 1},
                {"id": "minecraft:water_bucket", "name": "Water Bucket", "count": 1},
                {"id": "minecraft:bow", "name": "Bow", "count": 1, "damage": 25, "max_damage": 384, "durability_percent": 93}
            ],
            "main": [
                {"id": "minecraft:diamond", "name": "Diamond", "count": 64},
                {"id": "minecraft:diamond_block", "name": "Block of Diamond", "count": 16},
                {"id": "minecraft:emerald", "name": "Emerald", "count": 48},
                {"id": "minecraft:obsidian", "name": "Obsidian", "count": 64},
                {"id": "minecraft:ender_pearl", "name": "Ender Pearl", "count": 16},
                {"id": "minecraft:elytra", "name": "Elytra", "count": 1, "damage": 110, "max_damage": 432, "durability_percent": 74},
                {"id": "minecraft:enchanted_golden_apple", "name": "Enchanted Golden Apple", "count": 8},
                {"id": "minecraft:experience_bottle", "name": "Bottle o' Enchanting", "count": 64},
                {"id": "minecraft:iron_ingot", "name": "Iron Ingot", "count": 64},
                None, None, None, None, None, None, None, None, None,
                None, None, None, None, None, None, None, None, None
            ],
            "ender_chest": [
                {"id": "minecraft:shulker_box", "name": "Shulker Box", "count": 1},
                {"id": "minecraft:totem_of_undying", "name": "Totem of Undying", "count": 3},
                {"id": "minecraft:enchanted_book", "name": "Enchanted Book", "count": 1},
                {"id": "minecraft:netherite_ingot", "name": "Netherite Ingot", "count": 12},
                {"id": "minecraft:beacon", "name": "Beacon", "count": 2},
                None, None, None, None, None, None, None, None, None,
                None, None, None, None, None, None, None, None, None,
                None, None, None, None
            ]
        }
    }
server_manager.get_player_detailed_data = mock_get_player_detailed_data

# Mock list_addons
def mock_list_addons(engine):
    return {
        "folder": "plugins",
        "path": "server_data/plugins",
        "items": [
            {"filename": "EssentialsX-2.20.1.jar", "size_str": "4.2 MB", "size_bytes": 4404019, "enabled": True, "mtime": 1729252800},
            {"filename": "LuckPerms-Bukkit-5.4.102.jar", "size_str": "8.1 MB", "size_bytes": 8493465, "enabled": True, "mtime": 1729252900},
            {"filename": "WorldEdit-Bukkit-7.2.15.jar", "size_str": "5.6 MB", "size_bytes": 5872025, "enabled": True, "mtime": 1729253000},
            {"filename": "Vault.jar", "size_str": "340 KB", "size_bytes": 348160, "enabled": True, "mtime": 1729253100},
            {"filename": "Chunky-1.3.92.jar.disabled", "size_str": "1.1 MB", "size_bytes": 1153433, "enabled": False, "mtime": 1729253200}
        ]
    }
server_manager.list_addons = mock_list_addons

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
'''
    script_path.write_text(code, encoding="utf-8")
    return script_path


async def cdp_call(ws, method, params=None, msg_id=1):
    payload = {"id": msg_id, "method": method}
    if params:
        payload["params"] = params
    await ws.send(json.dumps(payload))
    while True:
        resp = await ws.recv()
        data = json.loads(resp)
        if data.get("id") == msg_id:
            return data


async def evaluate_js(ws, script, msg_id=1):
    return await cdp_call(ws, "Runtime.evaluate", {"expression": script, "awaitPromise": True}, msg_id=msg_id)


async def capture_tab_screenshot(ws, output_filename, msg_id_start=100):
    await asyncio.sleep(0.9)
    res = await cdp_call(ws, "Page.captureScreenshot", {"format": "png"}, msg_id=msg_id_start)
    if "result" in res and "data" in res["result"]:
        img_bytes = base64.b64decode(res["result"]["data"])
        out_path = SCREENSHOT_DIR / output_filename
        out_path.write_bytes(img_bytes)
        print(f"Captured: {out_path.name} ({len(img_bytes):,} bytes)", flush=True)
        return True
    else:
        print(f"Failed to capture {output_filename}: {res}", flush=True)
        return False


async def run_pipeline():
    import websockets

    server_script = build_mock_server_script()
    uv_proc = subprocess.Popen([sys.executable, str(server_script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for server
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/api/config", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            await asyncio.sleep(0.15)

    tmp_dir = tempfile.mkdtemp(prefix="chrome_cdp_")
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        f"--user-data-dir={tmp_dir}",
        f"--remote-debugging-port={CDP_PORT}",
        "--disable-gpu",
        "--window-size=1440,900",
        "--hide-scrollbars",
        "about:blank"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        await asyncio.sleep(2.0)
        tab_ws_url = None
        for _ in range(20):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=1) as resp:
                    tabs = json.loads(resp.read().decode("utf-8"))
                    for t in tabs:
                        if t.get("type") == "page" and "webSocketDebuggerUrl" in t:
                            tab_ws_url = t["webSocketDebuggerUrl"]
                            break
                    if tab_ws_url:
                        break
            except Exception:
                await asyncio.sleep(0.2)

        if not tab_ws_url:
            raise RuntimeError("Could not find page tab in Chrome CDP")

        async with websockets.connect(tab_ws_url, max_size=25_000_000) as ws:
            await cdp_call(ws, "Page.enable", msg_id=1)
            await cdp_call(ws, "Runtime.enable", msg_id=2)

            # Navigate to MSS
            await cdp_call(ws, "Page.navigate", {"url": f"http://{HOST}:{PORT}/"}, msg_id=3)
            await asyncio.sleep(3.0)

            # Ensure English language and dark mode
            await evaluate_js(ws, """
                localStorage.setItem('mss_lang', 'en');
                if (typeof applyLanguage === 'function') applyLanguage();
            """, msg_id=10)
            await asyncio.sleep(0.5)

            # 1. Overview Dashboard
            await evaluate_js(ws, "switchTab('all');", msg_id=12)
            await capture_tab_screenshot(ws, "01_overview_dashboard.png", msg_id_start=101)

            # 2. Live Console
            await evaluate_js(ws, "switchTab('console');", msg_id=13)
            await capture_tab_screenshot(ws, "02_live_console.png", msg_id_start=102)

            # 3. Core & Resources Tab
            await evaluate_js(ws, "switchTab('resources');", msg_id=14)
            await capture_tab_screenshot(ws, "03_core_resources.png", msg_id_start=103)

            # 4. Plugins & Mods Manager
            await evaluate_js(ws, "switchTab('addons'); if (typeof loadAddonsList === 'function') loadAddonsList();", msg_id=15)
            await capture_tab_screenshot(ws, "04_plugins_manager.png", msg_id_start=104)

            # 5. Players & Live Inventory Inspector Modal with active inspected item
            await evaluate_js(ws, """
                switchTab('players');
                if (typeof openPlayerInspectModal === 'function') {
                    openPlayerInspectModal('McDemon');
                    setTimeout(() => {
                        if (typeof onSlotClicked === 'function') {
                            onSlotClicked('hotbar_0');
                        }
                    }, 500);
                }
            """, msg_id=16)
            await asyncio.sleep(1.5)
            await capture_tab_screenshot(ws, "05_inventory_inspector.png", msg_id_start=105)

    finally:
        chrome_proc.terminate()
        uv_proc.terminate()
        server_script.unlink(missing_ok=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run_pipeline())
