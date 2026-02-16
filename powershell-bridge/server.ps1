# ============================================
# PERSISTENT POWERSHELL BRIDGE - STDIN/STDOUT
# ============================================
# Reads JSON command requests from stdin, executes them,
# writes JSON responses to stdout. One line per request/response.
#
# Launched by bridge.py — not directly by users.
# ============================================

$ErrorActionPreference = "Continue"

# Runspace pool for command execution
$runspacePool = [System.Management.Automation.Runspaces.RunspaceFactory]::CreateRunspacePool(1, 4)
$runspacePool.Open()

# Signal ready
[Console]::Out.WriteLine('{"ready":true,"pid":' + $PID + '}')
[Console]::Out.Flush()

function Invoke-BridgeCommand {
    param(
        [string]$Command,
        [int]$Timeout = 30
    )

    $ps = [System.Management.Automation.PowerShell]::Create()
    $ps.RunspacePool = $runspacePool
    [void]$ps.AddScript($Command)

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $asyncResult = $ps.BeginInvoke()

    if (-not $asyncResult.AsyncWaitHandle.WaitOne($Timeout * 1000)) {
        $ps.Stop()
        $sw.Stop()
        $ps.Dispose()
        return @{
            success     = $false
            stdout      = ""
            stderr      = "Command timed out after ${Timeout}s"
            duration_ms = $sw.ElapsedMilliseconds
        }
    }

    try {
        $output = $ps.EndInvoke($asyncResult)
        $sw.Stop()

        $stdout = ($output | Out-String).TrimEnd()
        $stderr = ""
        if ($ps.Streams.Error.Count -gt 0) {
            $stderr = ($ps.Streams.Error | ForEach-Object { $_.ToString() }) -join "`n"
        }

        return @{
            success     = ($ps.Streams.Error.Count -eq 0)
            stdout      = $stdout
            stderr      = $stderr
            duration_ms = $sw.ElapsedMilliseconds
        }
    } catch {
        $sw.Stop()
        return @{
            success     = $false
            stdout      = ""
            stderr      = $_.Exception.Message
            duration_ms = $sw.ElapsedMilliseconds
        }
    } finally {
        $ps.Dispose()
    }
}

# Main loop: read JSON line from stdin, execute, write JSON line to stdout
while ($true) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) { break }
    $line = $line.Trim()
    if ($line -eq "") { continue }

    try {
        $request = $line | ConvertFrom-Json
    } catch {
        $errResp = @{ id = "parse_error"; success = $false; stdout = ""; stderr = "Invalid JSON"; duration_ms = 0 } | ConvertTo-Json -Compress
        [Console]::Out.WriteLine($errResp)
        [Console]::Out.Flush()
        continue
    }

    # Ping
    if ($request.command -eq "__ping__") {
        $resp = @{ id = $request.id; success = $true; stdout = "pong"; stderr = ""; duration_ms = 0 } | ConvertTo-Json -Compress
        [Console]::Out.WriteLine($resp)
        [Console]::Out.Flush()
        continue
    }

    # Execute
    $timeout = if ($request.timeout) { $request.timeout } else { 30 }
    $result = Invoke-BridgeCommand -Command $request.command -Timeout $timeout

    $resp = @{
        id          = $request.id
        success     = $result.success
        stdout      = $result.stdout
        stderr      = $result.stderr
        duration_ms = $result.duration_ms
    } | ConvertTo-Json -Compress

    [Console]::Out.WriteLine($resp)
    [Console]::Out.Flush()
}

# Cleanup
$runspacePool.Close()
$runspacePool.Dispose()
