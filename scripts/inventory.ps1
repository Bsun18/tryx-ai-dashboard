$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Get-NvmeLink($Instance) {
    $node = $Instance
    for ($level = 0; $level -lt 7 -and $node; $level++) {
        if ($node.StartsWith('PCI\')) {
            $properties = @(Get-PnpDeviceProperty -InstanceId $node -ErrorAction SilentlyContinue)
            $generation = ($properties | Where-Object KeyName -EQ 'DEVPKEY_PciDevice_MaxLinkSpeed').Data
            $width = ($properties | Where-Object KeyName -EQ 'DEVPKEY_PciDevice_MaxLinkWidth').Data
            if ($generation -and $width) { return @{ max_gen = [int]$generation; max_width = [int]$width } }
        }
        $node = (Get-PnpDeviceProperty -InstanceId $node -KeyName 'DEVPKEY_Device_Parent' -ErrorAction SilentlyContinue).Data
    }
    return @{ max_gen = $null; max_width = $null }
}

$storage = @(Get-Disk -ErrorAction SilentlyContinue)
$disks = @(foreach ($drive in Get-CimInstance Win32_DiskDrive) {
    $details = $storage | Where-Object Number -EQ $drive.Index | Select-Object -First 1
    $bus = if ($details) { [string]$details.BusType } else { [string]$drive.InterfaceType }
    $link = if ($bus -eq 'NVMe') { Get-NvmeLink $drive.PNPDeviceID } else { @{ max_gen = $null; max_width = $null } }
    @{ index = [int]$drive.Index; model = $drive.Model.Trim(); bus = $bus;
       system = [bool]($details.IsSystem -or $details.IsBoot); max_gen = $link.max_gen; max_width = $link.max_width }
})
$physical = @(Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
$route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1 -ExpandProperty InterfaceAlias
@{
    cpu = ((Get-CimInstance Win32_Processor | Select-Object -First 1).Name).Trim()
    gpus = @((Get-CimInstance Win32_VideoController).Name)
    disks = $disks
    physical_interfaces = $physical
    default_interface = $route
} | ConvertTo-Json -Depth 5 -Compress
