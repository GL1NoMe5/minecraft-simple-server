import sys
import webbrowser
import uvicorn

if __name__ == "__main__":
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

    uvicorn.run("app.main:app", host=host, port=port, reload=False, log_level="info")
