param(
    [Parameter(Mandatory=$true)][ValidateSet('Install','Enable','Disable','Query')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [string]$DesktopDirectory = [Environment]::GetFolderPath('Desktop'),
    [string]$StartupDirectory = [Environment]::GetFolderPath('Startup')
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskShell = New-Object -ComObject WScript.Shell
$taskStartup = Join-Path $StartupDirectory 'TRYX AI Dashboard.lnk'
$taskLauncher = Join-Path $taskRoot 'launcher.py'
$taskControl = Join-Path $taskRoot 'control_panel.py'

function Test-OwnedShortcut([string]$Destination) {
    if (-not (Test-Path -LiteralPath $Destination)) { return $false }
    $link = $taskShell.CreateShortcut($Destination)
    return ($link.TargetPath -eq $PythonPath -and
        ($link.Arguments.StartsWith('"' + $taskLauncher + '" ') -or $link.Arguments -eq ('"' + $taskControl + '"')))
}
function Assert-Available([string]$Destination) {
    if ((Test-Path -LiteralPath $Destination) -and -not (Test-OwnedShortcut $Destination)) {
        throw 'A shortcut with this name belongs to another installation. Disable/remove its shortcuts first.'
    }
}
function Write-Link([string]$Destination, [string]$Script, [string]$Arguments, [string]$Description) {
    Assert-Available $Destination
    $link = $taskShell.CreateShortcut($Destination)
    $link.TargetPath = $PythonPath
    $link.Arguments = '"' + (Join-Path $taskRoot $Script) + '"' + $(if ($Arguments) { ' ' + $Arguments } else { '' })
    $link.WorkingDirectory = $taskRoot
    $link.WindowStyle = 7
    $link.Description = $Description
    $link.IconLocation = (Join-Path $taskRoot 'assets/dashboard.ico') + ',0'
    $link.Save()
}
if ($Mode -eq 'Query') {
    $enabled = Test-OwnedShortcut $taskStartup
    if ($enabled -and $StartupDirectory -eq [Environment]::GetFolderPath('Startup')) {
        $approved = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder' -Name 'TRYX AI Dashboard.lnk' -ErrorAction SilentlyContinue
        $bytes = $approved.'TRYX AI Dashboard.lnk'
        if ($bytes -and $bytes[0] -in @(3,7)) { $enabled = $false }
    }
    if ($enabled) { 'enabled' } else { 'disabled' }
} elseif ($Mode -eq 'Disable') {
    Assert-Available $taskStartup
    if (Test-Path -LiteralPath $taskStartup) { Remove-Item -LiteralPath $taskStartup }
    'Automatic startup disabled.'
} elseif ($Mode -eq 'Enable') {
    Write-Link $taskStartup 'launcher.py' 'autostart' 'Start the cooler dashboard after Windows sign-in.'
    # Clear only this app's approval record, allowing an explicit user enable to
    # undo a previous Task Manager disable. No machine-wide startup changes.
    $approvalKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder'
    if ($StartupDirectory -eq [Environment]::GetFolderPath('Startup')) {
        Remove-ItemProperty -Path $approvalKey -Name 'TRYX AI Dashboard.lnk' -ErrorAction SilentlyContinue
    }
    'Automatic startup enabled.'
} else {
    $labels = [IO.File]::ReadAllText((Join-Path $taskRoot 'assets/control-labels.json'),[Text.Encoding]::UTF8) | ConvertFrom-Json
    $control = Join-Path $DesktopDirectory ($labels.control + '.lnk')
    $toggle = Join-Path $DesktopDirectory ($labels.toggle + '.lnk')
    Assert-Available $control
    Assert-Available $toggle
    Write-Link $control 'control_panel.py' '' 'Start, stop, or configure the cooler dashboard.'
    Write-Link $toggle 'launcher.py' 'toggle' 'Toggle the dashboard without opening a console.'
    'Desktop shortcuts installed. Automatic startup is unchanged.'
}
