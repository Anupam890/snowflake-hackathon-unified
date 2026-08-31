"""
Background Server Manager.
Ensures that the FastAPI backend API is automatically started in a background daemon thread
whenever the Streamlit application is launched. Eliminates the need for running multiple servers manually.
"""
import os
import sys
import socket
import time
import threading
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_server_thread: Optional[threading.Thread] = None
_server_lock = threading.Lock()
_is_started = False


def is_port_open(host: str, port: int, timeout: float = 0.8) -> bool:
    """Checks if a TCP port is currently open and listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False


def _run_uvicorn(host: str, port: int):
    """Worker function to run uvicorn server in a daemon thread."""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        import uvicorn
        from main import app
        
        config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False
        )
        server = uvicorn.Server(config)
        loop.run_until_complete(server.serve())
    except Exception as e:
        print(f"[ServerManager] Background server error: {e}")


def ensure_backend_server(host: str = "127.0.0.1", port: int = 8001) -> bool:
    """
    Ensures the FastAPI backend server is running on the specified host and port.
    If already running or port is open, returns True immediately.
    Otherwise, spawns the server in a background daemon thread.
    """
    global _server_thread, _is_started
    
    # 1. Quick check if port is already active
    if is_port_open(host, port):
        _is_started = True
        return True

    with _server_lock:
        if _is_started and is_port_open(host, port):
            return True

        if _server_thread is not None and _server_thread.is_alive():
            return is_port_open(host, port)

        print(f"[ServerManager] Starting background FastAPI backend on http://{host}:{port}...")
        _server_thread = threading.Thread(
            target=_run_uvicorn,
            args=(host, port),
            daemon=True,
            name="FastAPIBackendDaemon"
        )
        _server_thread.start()

        # Wait briefly for server to bind
        for _ in range(20):
            time.sleep(0.15)
            if is_port_open(host, port):
                _is_started = True
                print(f"✅ [ServerManager] Background FastAPI backend is active and ready on http://{host}:{port}")
                return True

        print(f"⚠️ [ServerManager] Server spawned in background thread (listening check pending).")
        return True


def get_backend_url(default_url: str = "http://127.0.0.1:8001") -> str:
    """Returns the live backend URL after ensuring it is running."""
    ensure_backend_server()
    return default_url
