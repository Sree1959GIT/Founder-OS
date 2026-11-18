# FounderOS: is anything already listening on the ports run.bat needs? Names the process that holds each one.
# Usage (run.bat calls it): powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check_ports.ps1 8000 3000
# Exit code 0 when every port is free, 1 when one is taken (the message says which process and how to stop it).
param([int[]]$Ports = @(8000, 3000))

$busy = $false
foreach ($port in $Ports) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { continue }
    $busy = $true
    $procId = $conn.OwningProcess
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue
    $name = if ($proc) { $proc.Name } else { "unknown process" }
    $cmd = if ($proc -and $proc.CommandLine) { $proc.CommandLine } else { "" }
    $what = "process"
    if ($cmd -match "app\.main:create_app") { $what = "an old FounderOS backend" }
    elseif ($cmd -match "vite") { $what = "an old FounderOS frontend (Vite)" }
    Write-Host "[ERROR] Port $port is already in use by $what`: $name (PID $procId)."
    if ($cmd) {
        $short = if ($cmd.Length -gt 160) { $cmd.Substring(0, 160) + "..." } else { $cmd }
        Write-Host "        Command line: $short"
    }
    Write-Host "        Close its window, or stop it with:  Stop-Process -Id $procId"
}
if ($busy) {
    Write-Host "        Then run run.bat again. (An old backend would answer with old code.)"
    exit 1
}
exit 0
