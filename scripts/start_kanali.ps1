$ErrorActionPreference = 'Stop'
if (Get-Process -Name KANALI -ErrorAction SilentlyContinue) { exit 0 }
$task = Get-ScheduledTask -TaskName 'StartKANALI' -ErrorAction SilentlyContinue
if ($task -and $task.Settings.Enabled -and $task.Actions.Count -eq 1) {
    $target = $task.Actions[0].Execute.Trim('"')
    if ([IO.Path]::GetFileName($target) -ieq 'KANALI.exe' -and (Test-Path -LiteralPath $target)) {
        Start-ScheduledTask -InputObject $task
        exit 0
    }
}
# Different KANALI installations may use other startup arrangements. Leave them
# untouched and let the user start KANALI through its own UI.
exit 1
