<div align="center">

```
SYSTEM ARCHITECTURE · INDEX N° 001                          LOCAL ENGINE · 127.0.0.1:8000
WORKSPACE           · GL1NoMe5/minecraft-simple-server       STATUS       · PRODUCTION READY
```

# MSS // MINECRAFT SIMPLE SERVER
### Autonomous Local Web Control & Telemetry Suite for Minecraft Servers
*Engineered with FastAPI, Asynchronous RFC 6455 WebSockets, Pure Binary NBT Parsing, and Authentic Minecraft Edition UI.*

`focus`  ▸ **FastAPI 0.100+** • **Asynchronous Event Loop** • **Live WebSockets** • **Binary NBT & GZip**  
`deploy` ▸ **1-Click Standalone Exe** • **Automated Windows Batch** • **Paper / Purpur / Fabric / Forge / NeoForge**  
`status` ▸ **Production Ready** • **50/50 Tests Passing** • **Zero-Lag Telemetry** • **MIT Open Source**

────────────────────────────────────────────────────────────────────────────────────────────────────────────

**FASTAPI CORE · WEBSOCKETS IPC · PURE BINARY NBT · PIXEL SOUND ENGINE · PRODUCTION READY**

[OVERVIEW](#01-overview) &nbsp;·&nbsp; [SYSTEM MAP](#02-system-architecture--data-flow) &nbsp;·&nbsp; [QUICK INSTALLATION](#03-quick-installation--1-click-launchers) &nbsp;·&nbsp; [VISUAL SHOWCASE](#04-visual-showcase--interface-suite) &nbsp;·&nbsp; [PRESETS](#05-hardware-optimization-presets) &nbsp;·&nbsp; [JAVA MATRIX](#06-java-compatibility-matrix) &nbsp;·&nbsp; [TESTS](#07-verification--test-suite)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![WebSockets](https://img.shields.io/badge/WebSockets-RFC%206455-2563EB?style=for-the-badge&logo=socketdotio&logoColor=white)](https://websockets.readthedocs.io/)
[![Java](https://img.shields.io/badge/Java-8%20%7C%2017%20%7C%2021%20LTS-ED8B00?style=for-the-badge&logo=openjdk&logoColor=white)](https://adoptium.net/)
[![Tests](https://img.shields.io/badge/Tests-50%2F50%20Passing-55FF55?style=for-the-badge&logo=pytest&logoColor=black)](tests/)
[![License](https://img.shields.io/badge/License-MIT-A855F7?style=for-the-badge)](LICENSE)

</div>

---

```
┌────────────────────────┬──────────────────────────────────────────────────────────────────┐
│ TECHNICAL SPEC         │ ARCHITECTURAL IMPLEMENTATION                                     │
├────────────────────────┼──────────────────────────────────────────────────────────────────┤
│ Core Backend           │ Python 3.10+, FastAPI, Uvicorn (Asynchronous Event Loop)         │
│ Telemetry & Metrics    │ psutil hardware polling, Netty thread tracking, memory gauges    │
│ Stream Protocol        │ RFC 6455 WebSockets with heartbeat ping/pong & line buffering    │
│ Supported Engines      │ Paper, Purpur, Fabric, Forge, NeoForge, Vanilla (100+ releases)  │
│ Hardware Allocation    │ Dynamic RAM sliders (-Xms/-Xmx), CPU affinity, render distance   │
│ Memory Optimization    │ Automatic Aikar's Garbage Collector flags generator              │
│ Player Inspection      │ Pure binary SNBT & GZip playerdat parser with durability metrics │
│ Frontend Architecture  │ Vanilla ES6+, Tailwind CSS, Web Audio API, Canvas particle FX    │
│ Typography & Design    │ Authentic Minecraft block textures, 3D beveled slots, pixel type │
│ UI Localization        │ Built-in EN / RU bilingual toggle (accessible from top nav bar)  │
└────────────────────────┴──────────────────────────────────────────────────────────────────┘
```

---

## 01 OVERVIEW ───────────────────────────────────────────────────────────── ~/01-overview

**MSS (Minecraft Simple Server)** is a lightweight, zero-latency local web control panel engineered for running, configuring, and monitoring Minecraft servers directly on your personal computer.

Unlike bloated enterprise server management panels, MSS runs as a single lightweight background process that couples directly to the Java runtime process via asynchronous non-blocking pipes. It provides full control over hardware resource limits, server properties synchronization, real-time log streaming, hot plugin/mod deployment, and live player inventory inspection.

### Key Capabilities
- **Authentic Minecraft Edition UI**: Stone brick panels, oak wood navigation, 3D beveled inventory slots, dynamic biome particles, XP orbs, and Standard Galactic Alphabet floating enchantment runes.
- **Audio Synthesizer & Sound Effects**: Native Web Audio sound engine utilizing original Minecraft audio samples for clicks, sliders, tab transitions, and chest toggles.
- **Bi-directional WebSockets Console**: Low-overhead terminal pipe streaming Java runtime logs without page reloads, accompanied by instant command execution (`op`, `gamemode`, `stop`, `say`).
- **Live Player & Inventory Inspector**: Real-time NBT parser revealing exact player coordinates, health/hunger levels, experience levels, armor durability percentages, and Ender Chest contents.
- **1-Click Engine Deployment**: Automatic fetching and downloading of official server jars across Paper, Purpur, Fabric, Forge, NeoForge, and Mojang Vanilla.
- **Automated Aikar's GC Flags**: Hardware-tuned Java flags generated on the fly for optimal tick performance and zero Garbage Collection lag spikes.
- **Bilingual Interface**: Seamless instant toggling between English and Russian directly from the application header (`EN / RU` toggle button).

---

## 02 SYSTEM ARCHITECTURE & DATA FLOW ─────────────────────────────────────── ~/02-architecture

```
SYSTEM MAP — EVERYTHING FROM ONE PIPELINE                                        FIG. 01

  +───────────────────────────────────────────────────────────────────────────+
  |                           CLIENT BROWSER INTERFACE                        |
  |   (Vanilla ES6+ · Web Audio Engine · Biome Particle Canvas · Minecraft UI) |
  +─────────────────────▲───────────────────────────────▲─────────────────────+
                        │ REST Requests                 │ WebSockets (ws://)
                        │ (Config, Presets, Players)    │ (Live Console Feed)
  +─────────────────────▼───────────────────────────────▼─────────────────────+
  |                             FASTAPI CORE ENGINE                           |
  |                        (Uvicorn Async Event Loop)                         |
  +───────────┬───────────────────────┬───────────────────────┬───────────────+
              │                       │                       │
              ▼                       ▼                       ▼
  +──────────────────────+ +─────────────────────+ +─────────────────────+
  |   PROCESS MANAGER    | |   PLAYER SERVICE    | |  CONFIG & STORAGE   |
  |  - Async Subprocess  | |  - NBT/SNBT Parser  | |  - server.props sync|
  |  - STDIN Command Pipe| |  - Durability Math  | |  - Addon Dropzone   |
  |  - Live Log Broadcast| |  - Avatar Generator | |  - World Backups    |
  +───────────┬──────────+ +──────────┬──────────+ +──────────┬──────────+
              │                       │                       │
              ▼                       ▼                       ▼
  +──────────────────────+ +─────────────────────+ +─────────────────────+
  |    JAVA RUNTIME      | |   WORLD / PLAYER    | |   PLUGINS & MODS    |
  | (Paper/Fabric/Forge) | |  (playerdata/*.dat) | |  (server_data/mods) |
  +──────────────────────+ +─────────────────────+ +─────────────────────+
```
<p align="right"><em>DASHED LINES — DATA IN MOTION · FIG. 01</em></p>

---

## 03 QUICK INSTALLATION & 1-CLICK LAUNCHERS ──────────────────────────────── ~/03-installation

Choose the installation method that best matches your workflow:

### Method A: Standalone 1-Click Executable (.exe) — Fastest
No Python, Git, or terminal commands required.

1. Download or generate **`dist/MSS-Launcher.exe`**.
   - To build the executable from source at any time, simply double-click **`build_exe.bat`** (or run `python scripts/build_exe.py`).
2. Double-click **`MSS-Launcher.exe`**.
3. The executable starts the local server and automatically opens your web browser to:
   ```
   http://127.0.0.1:8000
   ```
*All configuration files and server data are stored cleanly beside the launcher executable.*

---

### Method B: Automated Windows Setup (`install.bat` & `run.bat`)
Recommended for users running directly from the source repository.

1. Clone or download this repository:
   ```powershell
   git clone https://github.com/GL1NoMe5/minecraft-simple-server.git
   cd minecraft-simple-server
   ```
2. Double-click **`install.bat`** (or simply double-click **`run.bat`**).
   - Automatically detects Python 3.10+ (supporting both `python` and `py` launcher);
   - Verifies Java runtime availability;
   - Sets up an isolated virtual environment (`venv/`);
   - Installs all dependencies with verification;
   - Pre-downloads authentic Minecraft sound assets;
   - Prompts for immediate launch.

For all subsequent starts, simply double-click **`run.bat`**.

---

### Method C: Manual Terminal Setup (CLI)
For developers and advanced users:

```powershell
# 1. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Cache Minecraft audio assets
python scripts/download_mc_sounds.py

# 4. Launch the application
python run.py
```

Navigate to: `http://127.0.0.1:8000`

---

## 04 VISUAL SHOWCASE & INTERFACE SUITE ──────────────────────────────────── ~/04-showcase

### 1. Main Telemetry Dashboard & Server Controls
The central command console gives you instant oversight of CPU utilization, RAM consumption, uptime counter, and real-time process controls (**Start Server**, **Stop**, **Restart**, **Kill**). Switch between pre-configured hardware presets with a single click.

<div align="center">
  <img src="docs/screenshots/01_overview_dashboard.png" alt="MSS Overview Dashboard" width="100%" />
  <p><em>FIG. 02 — Main Telemetry Dashboard with Real-Time Hardware Gauges, Engine Switcher &amp; Quick Presets</em></p>
</div>

---

### 2. Live WebSockets Terminal & Command Console
A high-performance interactive server terminal powered by WebSockets. Streams Java server logs line-by-line with zero delay and smooth auto-scrolling. Send console commands instantly (`op`, `gamemode`, `stop`, `say`) or use one-click macros (`list`, `tps`, `save-all`, `weather clear`).

<div align="center">
  <img src="docs/screenshots/02_live_console.png" alt="MSS Live Terminal Console" width="100%" />
  <p><em>FIG. 03 — Live WebSockets Terminal Console with Colorized Java Logs &amp; Quick Macros</em></p>
</div>

---

### 3. Hardware Resource Allocation & JVM Compiler Engine
Fine-tune minimum RAM (`-Xms`) and maximum RAM (`-Xmx`), CPU Netty worker threads, and chunk render distance (`view-distance`). The launch engine automatically generates optimal Aikar's Garbage Collector flags and validates your installed Java executable in real time.

<div align="center">
  <img src="docs/screenshots/03_core_resources.png" alt="MSS Core and Resources" width="100%" />
  <p><em>FIG. 04 — Core Resources, JVM Flag Generator, RAM/CPU Sliders &amp; Java Path Validator</em></p>
</div>

---

### 4. Drag & Drop Plugin and Mod Manager
Seamlessly install plugins and mods by dragging `.jar` files straight from Windows Explorer into the browser dropzone. The system automatically routes files to `plugins/` or `mods/` depending on the active engine, supporting one-click enable/disable (`.disabled`) and removal without restarting the panel.

<div align="center">
  <img src="docs/screenshots/04_plugins_manager.png" alt="MSS Plugins and Mods Manager" width="100%" />
  <p><em>FIG. 05 — Drag &amp; Drop Addon Dropzone with 1-Click State Toggles &amp; Delete Handlers</em></p>
</div>

---

### 5. Live Player & Binary NBT Inventory Inspector
Click any online or cached player to open the authentic Minecraft container GUI. Inspect Steve / Alex skins, hearts, hunger, XP levels, coordinates, full 27-slot inventory grid, 9-slot hotbar, armor column, offhand shield, and interactive Ender Chest contents with full item durability meters.

<div align="center">
  <img src="docs/screenshots/05_inventory_inspector.png" alt="MSS Inventory Inspector" width="100%" />
  <p><em>FIG. 06 — Authentic Minecraft Container GUI with Durability Meters &amp; Ender Chest</em></p>
</div>

---

## 05 HARDWARE OPTIMIZATION PRESETS ──────────────────────────────────────── ~/05-presets

MSS includes instant 1-click presets engineered to maximize ticks-per-second (TPS) and eliminate Garbage Collection lag spikes:

| Preset Name | Target Workload | Memory Limit | CPU Threads | View Distance | Recommended Engine |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Light Vanilla** | Clean vanilla gameplay (1–4 players) | 2 GB RAM | 2 Cores | 8 Chunks | Vanilla / Paper |
| **Optimized Paper** | High TPS, standard plugins (5–20 players) | 4 GB RAM | 4 Cores | 10 Chunks | Paper / Purpur |
| **Performance Fabric**| Modern lightweight modpacks & Sodium | 6 GB RAM | 4 Cores | 10 Chunks | Fabric |
| **Heavy Forge** | Extensive tech & magic modpacks | 8 GB RAM | 6 Cores | 12 Chunks | Forge / NeoForge |
| **Extreme Server** | Massive multi-world servers or heavy shaders | 16 GB RAM | 8+ Cores | 16 Chunks | Paper / Purpur |

---

## 06 JAVA COMPATIBILITY MATRIX ─────────────────────────────────────────── ~/06-compatibility

Minecraft server jars require specific Java LTS versions to execute properly. Configure your Java runtime via the MSS UI or directly in `server_config.json`:

```json
{
  "java_path": "java",
  "engine": "Paper",
  "version": "1.20.4",
  "min_ram": 4,
  "max_ram": 8,
  "cpu_threads": 4,
  "view_distance": 10,
  "allow_flight": true
}
```

| Minecraft Version | Required Java Version | Recommended OpenJDK Distribution |
| :--- | :--- | :--- |
| **1.20.5 – 1.21.x+** | **Java 21 LTS** | [Eclipse Adoptium Temurin 21](https://adoptium.net/) |
| **1.18.0 – 1.20.4** | **Java 17 LTS** | [Eclipse Adoptium Temurin 17](https://adoptium.net/) |
| **1.16.5 & Older** | **Java 8 / Java 11** | [Eclipse Adoptium Temurin 8](https://adoptium.net/) |

The web interface includes an integrated validation utility that verifies the Java binary version and displays compatibility status before launching the server.

---

## 07 VERIFICATION & TEST SUITE ──────────────────────────────────────────── ~/07-testing

The codebase includes an extensive automated test suite covering all critical subsystems:
- **Audio Synthesizer**: Synthesis fallback, frequency ranges, sound manifest schema;
- **Theme & Minecraft UI**: CSS custom properties, canvas particle lifecycle, local font fallbacks;
- **Player Actions & Gamemode**: WebSocket commands, payload normalization (`mode` / `value`);
- **Inventory & Flight**: GZip binary NBT parsing, durability calculations, `server.properties` synchronization;
- **Concurrency & Process Stability**: Heartbeat resilience, subprocess detachment handling.

Run the test suite:
```powershell
python -m unittest discover -s tests
```

Expected output:
```
Ran 50 tests in 1.248s

OK
```

---

## 08 PROJECT REPOSITORY STRUCTURE ───────────────────────────────────────── ~/08-structure

```
minecraft-simple-server/
├── app/
│   ├── config.py                 # Configuration manager and system specifications
│   ├── main.py                   # FastAPI REST API and WebSocket routes
│   ├── player_service.py         # Binary NBT deserializer and player avatar renderer
│   ├── server_manager.py         # Subprocess process controller and engine managers
│   └── static/                   # Static web assets
│       ├── assets/               # CSS styles, audio samples, pixel fonts, vendor libs
│       ├── icons/                # High-resolution Minecraft item sprites & textures
│       ├── app_logic.js          # Core frontend controller (WebSockets, UI, sounds)
│       └── index.html            # Primary single-page web dashboard
├── docs/
│   └── screenshots/              # High-resolution UI showcase preview images
│       ├── 01_overview_dashboard.png
│       ├── 02_live_console.png
│       ├── 03_core_resources.png
│       ├── 04_plugins_manager.png
│       └── 05_inventory_inspector.png
├── scripts/
│   ├── build_exe.py              # Standalone PyInstaller executable compilation script
│   ├── capture_screenshots.py    # Automated headless Chrome CDP screenshot generator
│   └── download_mc_sounds.py     # Local sound asset caching script
├── server_data/                  # Runtime server working directory (git-ignored)
│   ├── mods/                     # Fabric / Forge / NeoForge active mod directory
│   ├── plugins/                  # Paper / Purpur active plugin directory
│   ├── world/                    # Level save data and playerdata NBT files
│   └── server.properties         # Automatically synchronized server properties
├── tests/                        # 50 automated regression and unit tests
├── build_exe.bat                 # 1-click Windows executable builder
├── install.bat                   # Automated 1-click Windows setup script
├── run.bat                       # Smart Windows launcher (auto-invokes installer if needed)
├── run.py                        # Python server bootstrap with auto-opening browser
├── requirements.txt              # Production dependency specifications
└── README.md                     # Technical documentation & architecture index
```

---

## 09 LICENSE & ATTRIBUTIONS ─────────────────────────────────────────────── ~/09-license

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.

*Disclaimer: Minecraft is a registered trademark of Mojang Synergies AB / Microsoft Corporation. MSS (Minecraft Simple Server) is an open-source, independent tool and is not affiliated with, endorsed by, or associated with Mojang or Microsoft.*
