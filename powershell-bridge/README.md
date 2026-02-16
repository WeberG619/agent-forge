# PowerShell Bridge

100x faster PowerShell execution from WSL. A persistent TCP bridge that keeps a PowerShell process alive, eliminating the ~500ms subprocess startup overhead on every call.

## Why

Every `subprocess.run(["powershell.exe", ...])` from WSL takes ~500ms just to start PowerShell. When tools make dozens of calls per session, this adds up to minutes of waiting. The bridge keeps one PowerShell process alive and routes commands through TCP, reducing each call to ~5ms.

## Architecture

```
WSL Python Client  -->  TCP (127.0.0.1:15776)  -->  bridge.py  -->  stdin/stdout  -->  server.ps1  -->  PowerShell Runspace Pool
```

## Files

| File | Purpose |
|------|---------|
| `bridge.py` | TCP server + PowerShell subprocess manager |
| `client.py` | Client library with auto-fallback |
| `server.ps1` | PowerShell worker (runspace pool, JSON protocol) |
| `manage.py` | Lifecycle management (start/stop/status/restart) |

## Quick Start

```bash
# Start the bridge
python3 manage.py start

# Test it
python3 client.py test

# Benchmark bridge vs direct subprocess
python3 client.py benchmark
```

## Usage in Your Code

```python
from powershell_bridge.client import run_powershell

# Automatic fallback if bridge is down
result = run_powershell("Get-Process | Select -First 5")
print(result.stdout)
print(f"Via bridge: {result.via_bridge}, Time: {result.duration_ms:.0f}ms")
```

## Management

```bash
python3 manage.py start     # Start bridge daemon
python3 manage.py stop      # Stop bridge
python3 manage.py status    # Check health
python3 manage.py restart   # Restart bridge
```

## Performance

| Method | Avg Latency | Overhead |
|--------|-------------|----------|
| Direct `subprocess.run()` | ~500ms | PowerShell startup each time |
| Bridge | ~5ms | Persistent process, TCP routing |
| **Speedup** | **~100x** | |

## Notes

- Requires Windows with PowerShell (WSL environment)
- TCP server runs on `127.0.0.1:15776` (WSL-local only)
- Auto-restarts PowerShell subprocess if it crashes
- Health monitoring with `health.json`
- Daemon mode: `python3 bridge.py --daemon`
