# Keeps the order book collector running, and restarts it if it dies.
#
# The collector is a local process: it stops when the machine sleeps and does not come back on
# its own. The data it gathers cannot be bought later -- a minute not sampled is gone -- so the
# cost of it being quietly dead for a week is the week.
#
# Registered as a Scheduled Task that fires at logon, so waking the laptop is all it takes.
# Idempotent: if an instance is already collecting, this exits rather than starting a second one
# that would double every row.

$ErrorActionPreference = 'Stop'
$repo   = 'C:\Users\NEW TECH\Documents\Nextbigthing-restore'
$python = 'C:\Python312\python.exe'
$script = 'jobs/crypto_orderbook.py'
$logDir = Join-Path $repo '.cache\foundation\orderbook'

# Already running? A second collector would write the same snapshots twice.
$running = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*crypto_orderbook*' }
if ($running) {
    Write-Output "already collecting (pid $($running.ProcessId))"
    exit 0
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir '_service.log'
$err = Join-Path $logDir '_service.err'

Start-Process -FilePath $python `
    -ArgumentList '-u', $script, '--loop', '60' `
    -WorkingDirectory $repo `
    -RedirectStandardOutput $log `
    -RedirectStandardError $err `
    -WindowStyle Hidden
Write-Output "collector started"
