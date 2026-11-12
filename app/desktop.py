"""PR Explainer as a desktop app: its own window and icon (no browser).

    pythonw app/desktop.py          (or double-click "PR Explainer.lnk")

- Opens a native window (pywebview, which uses Windows' built-in WebView2) showing the same
  UI as http://127.0.0.1:8000.
- Starts Ollama in the background if it isn't running (the same Ollama and model as before).
- Runs the server inside this program on a free local port. If app/server.py is already
  running on port 8000 it reuses that one instead, because the local search index
  (qdrant_app/) can only be opened by one program at a time.
- Closing the window stops the server (Ollama keeps running, like when you start it yourself).
Chats are kept between launches (stored in %LOCALAPPDATA%\\PRExplainer).
"""
import ctypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import webview

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, "static", "icon.ico")
TITLE = "PR Explainer"
APP_ID = "ESP3201A.PRExplainer"          # own taskbar group + icon, not Python's
OLLAMA = "http://127.0.0.1:11434"
NO_WINDOW = 0x08000000 | 0x00000008      # CREATE_NO_WINDOW | DETACHED_PROCESS

LOADING = """<!doctype html><html><body style="margin:0;height:100vh;display:grid;place-items:center;
background:#16121c;color:#9a93a6;font:15px system-ui,Segoe UI,sans-serif">
<div style="text-align:center"><div style="width:56px;height:56px;margin:0 auto 18px;border-radius:50%;
background:radial-gradient(circle at 35% 30%,#f3d9ff,#b46cf0 28%,#5b1fa3 62%,#1b0b33);
box-shadow:0 0 40px 6px rgba(180,108,240,.35)"></div>
<div style="color:#ece9f1;font-size:18px;margin-bottom:6px">PR Explainer</div>
<div id="m">Starting…</div></div></body></html>"""


def reachable(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def start_ollama():
    if reachable(f"{OLLAMA}/api/version"):
        return
    exe = shutil.which("ollama") or os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
    if os.path.exists(exe):
        subprocess.Popen([exe, "serve"], creationflags=NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port):
    """Run app/server.py's FastAPI app in a background thread of this process."""
    import uvicorn
    sys.path.insert(0, HERE)
    import server                                      # loads the engine (can take a while)
    srv = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    return srv


def set_window_icon():
    """pywebview can't set the icon on Windows, so set it on the native window directly."""
    user32 = ctypes.windll.user32
    for _ in range(50):
        hwnd = user32.FindWindowW(None, TITLE)
        if hwnd:
            for size, which in ((16, 0), (32, 1)):      # ICON_SMALL, ICON_BIG
                h = user32.LoadImageW(None, ICON, 1, size, size, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
                if h:
                    user32.SendMessageW(hwnd, 0x0080, which, h)          # WM_SETICON
            return
        time.sleep(0.1)


def main():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    state = {"server": None}
    window = webview.create_window(TITLE, html=LOADING, width=1400, height=880, min_size=(420, 560),
                                   background_color="#16121c")

    def say(msg):
        try:
            window.evaluate_js(f"document.getElementById('m').textContent = {msg!r}")
        except Exception:
            pass

    def boot():
        set_window_icon()
        say("Starting Ollama…")
        threading.Thread(target=start_ollama, daemon=True).start()
        if reachable("http://127.0.0.1:8000/api/status", timeout=5):
            url = "http://127.0.0.1:8000/"                 # server already running: reuse it
        else:
            say("Starting the search engine (first start takes a minute)…")
            port = free_port()
            state["server"] = start_server(port)
            url = f"http://127.0.0.1:{port}/"
            for _ in range(600):
                if reachable(url + "api/status", timeout=2):
                    break
                time.sleep(0.2)
        window.load_url(url)

    webview.settings["ALLOW_DOWNLOADS"] = True              # Export (Markdown download)
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # "GitHub ↗" opens the browser
    storage = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "PRExplainer")
    webview.start(boot, private_mode=False, storage_path=storage)   # keeps chats between launches

    if state["server"] is not None:
        state["server"].should_exit = True
    os._exit(0)


if __name__ == "__main__":
    main()
