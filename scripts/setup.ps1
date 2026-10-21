param([switch]$NoShortcuts)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskVenv = Join-Path $taskRoot '.venv'
$taskPython = Join-Path $taskVenv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    $taskCreated = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $ErrorActionPreference = 'Continue'
        & py -3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
        $ErrorActionPreference = 'Stop'
        if ($LASTEXITCODE -eq 0) {
            & py -3 -m venv $taskVenv
            $taskCreated = $LASTEXITCODE -eq 0
        }
    }
    if (-not $taskCreated -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
        if ($LASTEXITCODE -eq 0) {
            & python -m venv $taskVenv
            $taskCreated = $LASTEXITCODE -eq 0
        }
    }
    if (-not $taskCreated) { throw 'Install Python 3.10 or newer from python.org, then run setup.cmd again.' }
}
& $taskPython -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 or newer is required"'
if ($LASTEXITCODE -ne 0) { throw 'Unsupported Python version.' }
& $taskPython -c 'import tkinter'
if ($LASTEXITCODE -ne 0) { throw 'Install the Tcl/Tk component of Python to use the desktop controller.' }
& $taskPython -m pip install --only-binary=:all: -r (Join-Path $taskRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check internet/PyPI access and retry.' }
& $taskPython (Join-Path $taskRoot 'launcher.py') configure
if ($LASTEXITCODE -ne 0) { throw 'Hardware configuration could not be completed; check the message above.' }
if (-not $NoShortcuts) {
    & $taskPython (Join-Path $taskRoot 'launcher.py') install-shortcuts
    if ($LASTEXITCODE -ne 0) { throw 'Could not install desktop shortcuts. You can still use control.cmd, start.cmd and stop.cmd.' }
}
Write-Host 'Setup complete. Open the desktop controller or control.cmd. Enable automatic startup there if desired.'
