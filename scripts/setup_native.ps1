$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run setup.cmd first to prepare Python, then run setup-native.cmd.' }
$taskProbe = [Net.Sockets.TcpClient]::new()
$taskBusy = $false
try { $taskProbe.Connect('127.0.0.1',18765); $taskBusy = $true } catch [Net.Sockets.SocketException] { } finally { $taskProbe.Dispose() }
if ($taskBusy) { throw 'Stop the running dashboard before installing or upgrading native sensors.' }
Write-Host 'Native mode installs a signed PawnIO driver and an on-demand elevated sensor task.'
Write-Host 'The dashboard remains unprivileged. This does not uninstall or change KANALI.'
Write-Host 'Google Platform-Tools terms: https://developer.android.com/tools/releases/platform-tools'
Write-Host 'PawnIO: https://pawnio.eu/   LibreHardwareMonitor: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor'
$taskConsent = Read-Host 'Download these components and request Windows administrator consent? [y/N]'
if ($taskConsent -notin @('y','Y','yes','YES')) { exit 0 }
& $taskPython (Join-Path $PSScriptRoot 'install_platform_tools.py')
if ($LASTEXITCODE -ne 0) { throw 'Platform-Tools preparation failed.' }
& $taskPython (Join-Path $PSScriptRoot 'prepare_native.py')
if ($LASTEXITCODE -ne 0) { throw 'Native sensor preparation failed.' }
$taskResult = Join-Path $taskRoot 'build\native\install-result.json'
if (Test-Path -LiteralPath $taskResult) { Remove-Item -LiteralPath $taskResult }
$taskSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$taskArgs = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'install_native.ps1') + '" -ExpectedUserSid "' + $taskSid + '"'
$taskProcess = Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -ArgumentList $taskArgs -WindowStyle Hidden -PassThru
$taskProcess.WaitForExit()
if (-not (Test-Path -LiteralPath $taskResult)) { throw 'Installation did not complete. Administrator consent may have been cancelled.' }
$taskInstalled = Get-Content -LiteralPath $taskResult -Raw | ConvertFrom-Json
if (-not $taskInstalled.ok) { throw $taskInstalled.error }
& $taskPython (Join-Path $taskRoot 'launcher.py') use-native
if ($LASTEXITCODE -ne 0) { throw 'Stop this dashboard, then run launcher.py use-native to finish switching the sensor backend.' }
& $taskPython (Join-Path $taskRoot 'launcher.py') configure
if ($LASTEXITCODE -ne 0) { throw 'Native sensors are installed, but the USB screen is not ready. Check USB and run setup.cmd again.' }
Write-Host 'Native setup complete. Start the dashboard. KANALI is not required to run.'
