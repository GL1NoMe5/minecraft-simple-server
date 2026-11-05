import logging
import os
import sys
import webbrowser
import uvicorn
from app.main import app, install_quiet_access_log_filter


def configure_windows_console() -> None:
    """
    On Windows cmd.exe / conhost.exe:
    1. Disables QuickEdit Mode (0x0040) on stdin so accidental mouse clicks
       inside the console window never freeze stdout and block the asyncio loop.
    2. Enables Virtual Terminal Processing (0x0004) on stdout/stderr so ANSI
       color codes render properly instead of printing raw escape sequences.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32

        # STD_INPUT_HANDLE = -10
        # ENABLE_QUICK_EDIT_MODE = 0x0040, ENABLE_EXTENDED_FLAGS = 0x0080
        h_in = kernel32.GetStdHandle(-10)
        if h_in and h_in != -1:
            mode_in = ctypes.c_uint32()
            if kernel32.GetConsoleMode(h_in, ctypes.byref(mode_in)):
                new_mode_in = (mode_in.value & ~0x0040) | 0x0080
                kernel32.SetConsoleMode(h_in, new_mode_in)

        # STD_OUTPUT_HANDLE = -11, STD_ERROR_HANDLE = -12
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        for std_id in (-11, -12):
            h_out = kernel32.GetStdHandle(std_id)
            if h_out and h_out != -1:
                mode_out = ctypes.c_uint32()
                if kernel32.GetConsoleMode(h_out, ctypes.byref(mode_out)):
                    kernel32.SetConsoleMode(h_out, mode_out.value | 0x0004)
    except Exception:
        pass


if __name__ == "__main__":
    configure_windows_console()
    install_quiet_access_log_filter()

    host = "127.0.0.1"
    port = 8000
    url = f"http://{host}:{port}"
    print("=" * 60)
    print("  MSS (Minecraft Simple Server)")
    print(f"  Web Panel / Веб-панель: {url}")
    print("=" * 60)
    
    # Auto open browser
    try:
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")
