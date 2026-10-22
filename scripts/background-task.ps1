param([Parameter(Mandatory=$true)][string]$Root, [Parameter(Mandatory=$true)][string]$PythonPath,
    [ValidateSet('Start','Stop','Remove')][string]$Mode = 'Start')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
trap { Write-Output $_.Exception.Message; exit 1 }
$Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
$taskScript = Join-Path $Root 'background.py'
if (-not (Test-Path -LiteralPath $taskScript) -or -not (Test-Path -LiteralPath $PythonPath)) { throw 'Dashboard runtime is missing.' }
$taskSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$taskHash = [Security.Cryptography.SHA256]::Create()
try { $taskId = ([BitConverter]::ToString($taskHash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Root.ToLowerInvariant())))).Replace('-','').Substring(0,16) }
finally { $taskHash.Dispose() }
$taskName = 'TRYX Dashboard-' + $taskSid + '-' + $taskId
$taskArguments = '"' + $taskScript + '"'
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder = $service.GetFolder('\')
$existing = $null
try { $existing = $folder.GetTask($taskName) } catch { if ($_.Exception.HResult -ne -2147024894) { throw } }
if ($existing) {
    $definition = $existing.Definition
    $taskOwner = $definition.Principal.UserId
    if ($taskOwner -notlike 'S-1-*') {
        $taskOwner = ([Security.Principal.NTAccount]::new($taskOwner)).Translate([Security.Principal.SecurityIdentifier]).Value
    }
    if ($definition.Actions.Count -ne 1 -or $definition.Actions.Item(1).Arguments -ne $taskArguments -or
        $taskOwner -ne $taskSid -or $definition.Principal.RunLevel -ne 0) {
        throw 'Task identity mismatch; refusing to change another task.'
    }
    if ($Mode -eq 'Stop') {
        if ($existing.State -eq 4) { $existing.Stop(0) }
        'stopped'; exit 0
    }
    if ($Mode -eq 'Remove') {
        if ($existing.State -eq 4) { throw 'Stop the dashboard before removing its background task.' }
        $folder.DeleteTask($taskName,0)
        'removed'; exit 0
    }
    if ($existing.State -eq 4) { 'running'; exit 0 }
}
if ($Mode -ne 'Start') { 'not installed'; exit 0 }
$definition = $service.NewTask(0)
$definition.RegistrationInfo.Description = 'TRYX dashboard background process for ' + $Root + '. On demand; normal user privileges; no password stored.'
$definition.Principal.UserId = $taskSid
$definition.Principal.LogonType = 3 # InteractiveToken, current signed-in user only.
$definition.Principal.RunLevel = 0 # LUA, never elevate the dashboard.
$definition.Settings.Enabled = $true
$definition.Settings.AllowDemandStart = $true
$definition.Settings.DisallowStartIfOnBatteries = $false
$definition.Settings.StopIfGoingOnBatteries = $false
$definition.Settings.ExecutionTimeLimit = 'PT0S'
$definition.Settings.MultipleInstances = 2 # IgnoreNew.
$definition.Settings.Priority = 4
$action = $definition.Actions.Create(0)
$action.Path = $PythonPath
$action.Arguments = $taskArguments
$action.WorkingDirectory = $Root
$registered = $folder.RegisterTaskDefinition($taskName, $definition, 6, $taskSid, $null, 3, $null)
$null = $registered.Run($null)
'started'
