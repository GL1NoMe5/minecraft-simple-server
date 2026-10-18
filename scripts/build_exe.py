"""
MSS Standalone Executable Builder
Builds a single-file portable Windows executable (MSS-Launcher.exe) using PyInstaller.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def build():
    print("=" * 65)
    print("  MSS (Minecraft Simple Server) - Standalone Executable Builder")
    print("=" * 65)
    print()

    # 1. Ensure PyInstaller is installed
    try:
        import PyInstaller
        print(f"[+] Found PyInstaller v{PyInstaller.__version__}")
    except ImportError:
        print("[*] PyInstaller not detected. Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    static_dir = BASE_DIR / "app" / "static"
    run_file = BASE_DIR / "run.py"

    if not static_dir.exists():
        print(f"[-] Error: static directory not found at {static_dir}")
        sys.exit(1)

    print("[*] Compiling standalone executable with PyInstaller...")
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name=MSS-Launcher",
        f"--add-data={static_dir};app/static",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespans",
        "--hidden-import=uvicorn.lifespans.on",
        "--hidden-import=fastapi",
        "--hidden-import=websockets",
        "--hidden-import=psutil",
        "--hidden-import=PIL",
        "--hidden-import=nbtlib",
        str(run_file)
    ]

    subprocess.check_call(cmd, cwd=str(BASE_DIR))

    print()
    print("=" * 65)
    print("  [+] Build completed successfully!")
    print(f"  [+] Output executable: {BASE_DIR / 'dist' / 'MSS-Launcher.exe'}")
    print("=" * 65)


if __name__ == "__main__":
    build()
