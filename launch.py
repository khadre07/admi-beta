"""Point d'entrée pour l'exécutable autonome (PyInstaller).

Lance le serveur Streamlit depuis l'intérieur du bundle et ouvre le navigateur.
"""
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

PORT = "8533"


def _notify(message: str):
    """Notification macOS best-effort (feedback pendant le démarrage à froid)."""
    if sys.platform != "darwin":
        return
    try:
        subprocess.Popen(
            ["osascript", "-e", f'display notification "{message}" with title "ADMI"'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _app_dir() -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "admi_app")


def _open_browser_when_ready():
    url = f"http://localhost:{PORT}"
    for _ in range(160):
        try:
            with urllib.request.urlopen(url + "/_stcore/health", timeout=1) as r:
                if r.status == 200 and b"ok" in r.read():
                    break
        except Exception:
            pass
        time.sleep(0.5)
    if not os.environ.get("ADMI_NO_BROWSER"):   # désactivé en CI / serveur
        webbrowser.open(url)


def main():
    # En mode fenêtré (Windows/macOS sans console), stdout/stderr peuvent être
    # None -> certaines libs plantent. On les redirige vers os.devnull.
    for _stream in ("stdout", "stderr"):
        if getattr(sys, _stream) is None:
            setattr(sys, _stream, open(os.devnull, "w", encoding="utf-8"))

    app_dir = _app_dir()
    os.chdir(app_dir)
    sys.path.insert(0, app_dir)

    _notify("Démarrage du tableau de bord ADMI…")
    threading.Thread(target=_open_browser_when_ready, daemon=True).start()

    sys.argv = [
        "streamlit", "run", os.path.join(app_dir, "app.py"),
        f"--server.port={PORT}", "--server.headless=true",
        "--browser.gatherUsageStats=false", "--global.developmentMode=false",
    ]
    from streamlit.web import cli as stcli
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
