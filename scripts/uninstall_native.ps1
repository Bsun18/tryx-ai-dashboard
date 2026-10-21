$ErrorActionPreference = 'Stop'
$taskIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($taskIdentity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run this script as administrator to remove the sensor host.' }
$taskName = 'TRYX AI Sensors-' + $taskIdentity.User.Value
$taskExpected = [IO.Path]::GetFullPath((Join-Path $env:ProgramFiles 'TRYX AI Dashboard Sensors'))
$taskExecutable = Join-Path $taskExpected 'SensorHost.exe'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    if ($task.Actions.Count -ne 1 -or $task.Actions[0].Execute.Trim('"') -ine $taskExecutable) { throw 'Task identity differs; no changes made.' }
    Stop-ScheduledTask -InputObject $task
    Unregister-ScheduledTask -InputObject $task -Confirm:$false
}
Start-Sleep -Milliseconds 700
# Other users may also have a task referencing the shared protected host.
$taskOther = @(Get-ScheduledTask | Where-Object { $_.Actions.Execute -contains $taskExecutable })
if ($taskOther.Count -eq 0 -and (Test-Path -LiteralPath $taskExpected)) {
    Get-CimInstance Win32_Process -Filter "Name='SensorHost.exe'" | ForEach-Object {
        if ($_.ExecutablePath -ieq $taskExecutable) {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Wait-Process -Id $_.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
        }
    }
    $taskResolved = (Resolve-Path -LiteralPath $taskExpected).Path
    if ($taskResolved -ine $taskExpected -or [IO.Path]::GetDirectoryName($taskResolved) -ine [IO.Path]::GetFullPath($env:ProgramFiles)) { throw 'Refusing unexpected uninstall path.' }
    if (@(Get-Item -LiteralPath $taskResolved; Get-ChildItem -LiteralPath $taskResolved -Recurse -Force) | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'Refusing a reparse point in the sensor directory.' }
    Remove-Item -LiteralPath $taskResolved -Recurse -Force
}
Write-Host 'Sensor host removed. PawnIO is shared with other monitoring apps; remove it separately in Windows Installed Apps only if it is no longer needed.'
