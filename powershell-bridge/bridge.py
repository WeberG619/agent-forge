"""
PowerShell Bridge — TCP Server + Subprocess Manager

Runs inside WSL. Starts a persistent powershell.exe subprocess
and exposes it via TCP on 127.0.0.1:15776 (WSL-local).

This avoids WSL2 NAT networking issues — the TCP server and all
clients run on the same (WSL) network stack.

Usage:
    python3 bridge.py           # Run in foreground
    python3 bridge.py --daemon  # Run as daemon (background)
"""

import json
import os
import signal
import socketserver
import subprocess
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PS1 = os.path.join(SCRIPT_DIR, "server.ps1")
# Convert WSL path to Windows path for PowerShell
import re as _re
def _wsl_to_win(path):
    m = _re.match(r'/mnt/([a-z])/(.*)', path)
    if m:
        return f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\")
    return path.replace("/", "\\")
SERVER_PS1_WIN = _wsl_to_win(SERVER_PS1)
PID_FILE = os.path.join(SCRIPT_DIR, "bridge.pid")
HEALTH_FILE = os.path.join(SCRIPT_DIR, "health.json")

HOST = "127.0.0.1"
PORT = 15776


class PowerShellProcess:
    """Manages a persistent powershell.exe subprocess."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._ps_pid: int | None = None
        self._request_count = 0
        self._start_time = time.time()

    def start(self) -> bool:
        """Start the PowerShell subprocess."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return True  # Already running

            try:
                self._proc = subprocess.Popen(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-WindowStyle", "Hidden",
                        "-ExecutionPolicy", "Bypass",
                        "-File", SERVER_PS1_WIN,
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
            except FileNotFoundError:
                print("ERROR: powershell.exe not found", file=sys.stderr)
                return False

            # Wait for ready signal
            try:
                ready_line = self._proc.stdout.readline().decode("utf-8").strip()
                ready = json.loads(ready_line)
                if ready.get("ready"):
                    self._ps_pid = ready.get("pid")
                    self._start_time = time.time()
                    print(f"PowerShell subprocess ready (PID {self._ps_pid})")
                    return True
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"ERROR: Bad ready signal: {e}", file=sys.stderr)

            self._proc.kill()
            self._proc = None
            return False

    def execute(self, request: dict) -> dict:
        """Send a command to PowerShell and get the response. Thread-safe."""
        with self._lock:
            if not self._proc or self._proc.poll() is not None:
                # Try to restart
                if not self.start():
                    return {
                        "id": request.get("id", "error"),
                        "success": False,
                        "stdout": "",
                        "stderr": "PowerShell subprocess not available",
                        "duration_ms": 0,
                    }

            try:
                line = json.dumps(request) + "\n"
                self._proc.stdin.write(line.encode("utf-8"))
                self._proc.stdin.flush()

                resp_line = self._proc.stdout.readline().decode("utf-8").strip()
                if not resp_line:
                    raise IOError("Empty response from PowerShell")

                self._request_count += 1
                return json.loads(resp_line)

            except (IOError, json.JSONDecodeError, BrokenPipeError) as e:
                # Subprocess crashed — kill and let next call restart it
                try:
                    self._proc.kill()
                except Exception:
                    pass
                self._proc = None
                return {
                    "id": request.get("id", "error"),
                    "success": False,
                    "stdout": "",
                    "stderr": f"PowerShell subprocess error: {e}",
                    "duration_ms": 0,
                }

    def stop(self):
        """Stop the PowerShell subprocess."""
        with self._lock:
            if self._proc:
                try:
                    self._proc.stdin.close()
                except Exception:
                    pass
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=3)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None

    @property
    def stats(self) -> dict:
        return {
            "ps_pid": self._ps_pid,
            "alive": self._proc is not None and self._proc.poll() is None,
            "requests": self._request_count,
            "uptime_s": int(time.time() - self._start_time),
        }


# Global PowerShell process
ps = PowerShellProcess()


class BridgeHandler(socketserver.StreamRequestHandler):
    """Handle one TCP connection: read JSON request, relay to PS, return response."""

    def handle(self):
        try:
            line = self.rfile.readline().decode("utf-8").strip()
            if not line:
                return

            request = json.loads(line)
            response = ps.execute(request)

            resp_bytes = (json.dumps(response) + "\n").encode("utf-8")
            self.wfile.write(resp_bytes)
            self.wfile.flush()

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            err = json.dumps({
                "id": "error",
                "success": False,
                "stdout": "",
                "stderr": f"Bridge protocol error: {e}",
                "duration_ms": 0,
            }) + "\n"
            self.wfile.write(err.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            pass


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def write_health(status: str):
    """Write health file."""
    stats = ps.stats
    health = {
        "status": status,
        "bridge_pid": os.getpid(),
        "ps_pid": stats["ps_pid"],
        "port": PORT,
        "requests": stats["requests"],
        "uptime_s": stats["uptime_s"],
    }
    try:
        with open(HEALTH_FILE, "w") as f:
            json.dump(health, f)
    except IOError:
        pass


def cleanup(signum=None, frame=None):
    """Clean shutdown."""
    print("\nShutting down bridge...")
    ps.stop()
    write_health("stopped")
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    sys.exit(0)


def main():
    # Write PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # Signal handlers
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Start PowerShell subprocess
    if not ps.start():
        print("ERROR: Failed to start PowerShell subprocess", file=sys.stderr)
        sys.exit(1)

    # Start TCP server
    server = ThreadedTCPServer((HOST, PORT), BridgeHandler)
    print(f"Bridge TCP server on {HOST}:{PORT} (PID {os.getpid()})")
    write_health("running")

    # Health writer thread
    def health_loop():
        while True:
            time.sleep(30)
            write_health("running")

    t = threading.Thread(target=health_loop, daemon=True)
    t.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        cleanup()


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        # Fork to background
        if os.fork() > 0:
            sys.exit(0)
        os.setsid()
        if os.fork() > 0:
            sys.exit(0)
        # Redirect stdio
        sys.stdin = open(os.devnull)
        log = open(os.path.join(SCRIPT_DIR, "bridge.log"), "a")
        sys.stdout = log
        sys.stderr = log
    main()
