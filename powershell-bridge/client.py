"""
PowerShell Bridge Client — Drop-in replacement for subprocess.run(powershell...)

Usage:
    from client import ps_exec, run_powershell

    # Fast path (via bridge):
    result = ps_exec("Get-Process | Select -First 5")
    print(result.stdout)

    # Drop-in replacement (auto-fallback if bridge is down):
    result = run_powershell("Get-Date")
    print(result.stdout)

CLI:
    python3 client.py test         # Quick connectivity test
    python3 client.py benchmark    # Compare bridge vs direct subprocess
    python3 client.py exec "cmd"   # Execute a command
"""

import json
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Optional

BRIDGE_HOST = "127.0.0.1"  # bridge.py runs inside WSL, so localhost works
BRIDGE_PORT = 15776
CONNECT_TIMEOUT = 0.5  # Fast fail if bridge is down
READ_TIMEOUT = 60


@dataclass
class PSResult:
    """Result from a PowerShell command execution."""
    stdout: str
    stderr: str
    success: bool
    duration_ms: float
    via_bridge: bool

    @property
    def returncode(self) -> int:
        """Compatibility with subprocess.CompletedProcess."""
        return 0 if self.success else 1


def _bridge_available() -> bool:
    """Quick check if the bridge is listening."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        sock.connect((BRIDGE_HOST, BRIDGE_PORT))
        sock.close()
        return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


def ps_exec(command: str, timeout: int = 30) -> PSResult:
    """
    Execute a PowerShell command via the bridge.
    Raises ConnectionError if bridge is unavailable.
    """
    request = {
        "id": str(uuid.uuid4())[:8],
        "command": command,
        "timeout": timeout,
    }

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(CONNECT_TIMEOUT)

    try:
        sock.connect((BRIDGE_HOST, BRIDGE_PORT))
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        sock.close()
        raise ConnectionError(f"PowerShell bridge not available: {e}")

    sock.settimeout(timeout + 5)  # Extra margin beyond command timeout

    try:
        payload = json.dumps(request) + "\n"
        sock.sendall(payload.encode("utf-8"))

        # Read response (one line of JSON)
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk

        if not data:
            raise ConnectionError("Bridge closed connection without response")

        response = json.loads(data.decode("utf-8").strip())

        return PSResult(
            stdout=response.get("stdout", ""),
            stderr=response.get("stderr", ""),
            success=response.get("success", False),
            duration_ms=response.get("duration_ms", 0),
            via_bridge=True,
        )
    finally:
        sock.close()


def _direct_powershell(command: str, timeout: int = 30) -> PSResult:
    """Fallback: run via direct subprocess (slow, ~4.4s overhead)."""
    start = time.time()
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = (time.time() - start) * 1000
        return PSResult(
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            success=(result.returncode == 0),
            duration_ms=elapsed,
            via_bridge=False,
        )
    except subprocess.TimeoutExpired:
        elapsed = (time.time() - start) * 1000
        return PSResult(
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            success=False,
            duration_ms=elapsed,
            via_bridge=False,
        )


def run_powershell(command: str, timeout: int = 30) -> PSResult:
    """
    Execute PowerShell command with automatic fallback.
    Tries bridge first; if unavailable, falls back to direct subprocess.
    """
    try:
        return ps_exec(command, timeout)
    except ConnectionError:
        return _direct_powershell(command, timeout)


def ping() -> Optional[float]:
    """Ping the bridge. Returns round-trip ms or None if unavailable."""
    try:
        start = time.time()
        ps_exec("__ping__", timeout=5)
        # Ping is handled specially by server — but let's just measure the round trip
        elapsed = (time.time() - start) * 1000
        return elapsed
    except ConnectionError:
        return None


def _cmd_test():
    """Quick connectivity test."""
    print("PowerShell Bridge - Connection Test")
    print("=" * 40)

    # Test ping
    latency = ping()
    if latency is not None:
        print(f"  Bridge: CONNECTED ({latency:.0f}ms ping)")
    else:
        print("  Bridge: NOT AVAILABLE")
        print("  Start with: powershell.exe -NoProfile -File server.ps1")
        return

    # Test actual command
    print()
    result = ps_exec("Write-Output 'Hello from PowerShell Bridge!'")
    print("  Command: Write-Output 'Hello from PowerShell Bridge!'")
    print(f"  Output:  {result.stdout}")
    print(f"  Success: {result.success}")
    print(f"  Time:    {result.duration_ms:.0f}ms (server-side)")
    print(f"  Via:     {'bridge' if result.via_bridge else 'subprocess'}")

    # Test Get-Date
    print()
    result = ps_exec("[DateTime]::Now.ToString('o')")
    print("  Command: [DateTime]::Now.ToString('o')")
    print(f"  Output:  {result.stdout}")
    print(f"  Time:    {result.duration_ms:.0f}ms")


def _cmd_benchmark():
    """Compare bridge vs direct subprocess performance."""
    print("PowerShell Bridge - Benchmark")
    print("=" * 40)

    test_cmd = "Write-Output 'benchmark'"
    iterations = 5

    # Bridge
    print(f"\n  Bridge ({iterations} iterations):")
    bridge_times = []
    for i in range(iterations):
        try:
            start = time.time()
            result = ps_exec(test_cmd)
            elapsed = (time.time() - start) * 1000
            bridge_times.append(elapsed)
            print(f"    #{i+1}: {elapsed:.0f}ms (server: {result.duration_ms:.0f}ms)")
        except ConnectionError:
            print(f"    #{i+1}: BRIDGE NOT AVAILABLE")
            break

    if bridge_times:
        avg_bridge = sum(bridge_times) / len(bridge_times)
        print(f"    Average: {avg_bridge:.0f}ms")
    else:
        avg_bridge = None

    # Direct subprocess
    print(f"\n  Direct subprocess ({iterations} iterations):")
    direct_times = []
    for i in range(iterations):
        start = time.time()
        result = _direct_powershell(test_cmd)
        elapsed = (time.time() - start) * 1000
        direct_times.append(elapsed)
        print(f"    #{i+1}: {elapsed:.0f}ms")

    avg_direct = sum(direct_times) / len(direct_times)
    print(f"    Average: {avg_direct:.0f}ms")

    # Summary
    print("\n  Summary:")
    print(f"    Direct subprocess: {avg_direct:.0f}ms avg")
    if avg_bridge:
        speedup = avg_direct / avg_bridge
        print(f"    Bridge:            {avg_bridge:.0f}ms avg")
        print(f"    Speedup:           {speedup:.0f}x faster")
    else:
        print("    Bridge:            not available")


def _cmd_exec(command: str):
    """Execute a command via run_powershell (with fallback)."""
    result = run_powershell(command)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 client.py {test|benchmark|exec <command>}")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "test":
        _cmd_test()
    elif cmd == "benchmark":
        _cmd_benchmark()
    elif cmd == "exec" and len(sys.argv) >= 3:
        _cmd_exec(" ".join(sys.argv[2:]))
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 client.py {test|benchmark|exec <command>}")
        sys.exit(1)
