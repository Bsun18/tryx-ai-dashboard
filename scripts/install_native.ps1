param([string]$ExpectedUserSid)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskBuild = Join-Path $taskRoot 'build\native'
$taskIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$taskSid = $taskIdentity.User.Value
if ($ExpectedUserSid -and $taskSid -ne $ExpectedUserSid) { throw 'Use the same Windows account for installation and the dashboard.' }
if (-not ([Security.Principal.WindowsPrincipal]::new($taskIdentity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator consent is needed once to install the sensor driver and protected sensor host.'
}
$taskProgram = Join-Path $env:ProgramFiles 'TRYX AI Dashboard Sensors'
$taskData = Join-Path $env:ProgramData ('TryxAiDashboard\' + $taskSid)
$taskName = 'TRYX AI Sensors-' + $taskSid

function Assert-NoReparse([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Refusing reparse point: $Path" }
}

function Protect-Directory([string]$Path) {
    Assert-NoReparse $Path
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    foreach ($entry in @(@('S-1-5-18','FullControl'), @('S-1-5-32-544','FullControl'), @('S-1-5-32-545','ReadAndExecute'))) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($entry[0]), $entry[1],
            'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

try {
    $taskManifest = Get-Content -LiteralPath (Join-Path $taskBuild 'payload-sha256.json') -Raw | ConvertFrom-Json
    $taskPayload = Join-Path $taskBuild 'payload'
    foreach ($entry in $taskManifest.PSObject.Properties) {
        if ([IO.Path]::GetFileName($entry.Name) -cne $entry.Name) { throw 'Invalid payload filename.' }
        $file = Join-Path $taskPayload $entry.Name
        Assert-NoReparse $file
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ine $entry.Value) { throw "Payload checksum mismatch: $($entry.Name)" }
    }
    if (-not $taskManifest.'SensorHost.exe' -or -not $taskManifest.'LibreHardwareMonitorLib.dll') { throw 'Incomplete sensor payload.' }
    $taskInstaller = Join-Path $taskBuild 'PawnIO_setup.exe'
    if ((Get-FileHash -LiteralPath $taskInstaller -Algorithm SHA256).Hash -ine '1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032') { throw 'PawnIO checksum mismatch.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $taskInstaller
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=namazso.eu') { throw 'PawnIO publisher signature is not valid.' }
    $taskOld = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($taskOld) {
        if ($taskOld.Actions.Count -ne 1 -or $taskOld.Actions[0].Execute.Trim('"') -ine (Join-Path $taskProgram 'SensorHost.exe')) { throw 'Another task already uses the sensor task name.' }
        Stop-ScheduledTask -InputObject $taskOld
        # Scheduler cancellation may return before the CLR releases its DLLs.
        # Only stop a process executing this exact protected host.
        Get-CimInstance Win32_Process -Filter "Name='SensorHost.exe'" | ForEach-Object {
            if ($_.ExecutablePath -ieq (Join-Path $taskProgram 'SensorHost.exe')) {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
                Wait-Process -Id $_.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
            }
        }
    }
    Protect-Directory $taskProgram
    Assert-NoReparse (Join-Path $env:ProgramData 'TryxAiDashboard')
    Protect-Directory (Join-Path $env:ProgramData 'TryxAiDashboard')
    Protect-Directory $taskData
    foreach ($entry in $taskManifest.PSObject.Properties) {
        $destination = Join-Path $taskProgram $entry.Name
        Assert-NoReparse $destination
        if (-not (Test-Path -LiteralPath $destination) -or (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ine $entry.Value) {
            Copy-Item -LiteralPath (Join-Path $taskPayload $entry.Name) -Destination $destination -Force
        }
    }
    $taskPawn = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO' -ErrorAction SilentlyContinue
    if (-not $taskPawn -or [version]$taskPawn.DisplayVersion -lt [version]'2.2.0') {
        $installed = Start-Process -FilePath $taskInstaller -ArgumentList '-install' -WindowStyle Hidden -Wait -PassThru
        if ($installed.ExitCode -notin @(0,3010)) { throw "PawnIO installer returned $($installed.ExitCode)." }
    }
    $taskAction = New-ScheduledTaskAction -Execute (Join-Path $taskProgram 'SensorHost.exe') -WorkingDirectory $taskProgram
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskSid -LogonType Interactive -RunLevel Highest
    $taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Principal $taskPrincipal -Settings $taskSettings -Description 'Read-only CPU/GPU/motherboard sensors for TRYX AI Dashboard. On demand; exits when the dashboard stops.' -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName
    @{ok=$true; task=$taskName; host=$taskProgram} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBuild 'install-result.json') -Encoding UTF8
} catch {
    @{ok=$false; error=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBuild 'install-result.json') -Encoding UTF8
    throw
}
