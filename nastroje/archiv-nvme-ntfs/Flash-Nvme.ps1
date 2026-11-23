[CmdletBinding()]
param(
    [int]$DiskNumber = -1,
    [string]$ExpectedSerial = '',
    [UInt64]$ExpectedSize = 0,
    [switch]$Execute,
    [switch]$FinalizeOnly,
    [string]$ImagerPath = 'C:\Program Files\Raspberry Pi Ltd\Imager\rpi-imager.exe'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$imagePath = Join-Path $PSScriptRoot 'formula-logger-rpi5-64GiB-NTFS.img.zst'
$hashPath = Join-Path $PSScriptRoot 'IMAGE_SHA256.txt'

function Get-CheckedTarget {
    $disk = Get-Disk -Number $DiskNumber
    if ($disk.IsBoot -or $disk.IsSystem -or $disk.BusType -ne 'USB') {
        throw 'Target must be an external USB disk, never the Windows system disk.'
    }
    if ($disk.Size -lt 230000000000 -or $disk.Size -gt 280000000000) {
        throw 'This installer is restricted to the intended approximately 256 GB SSD.'
    }
    if ($disk.IsReadOnly) { throw 'The target is read-only.' }
    $diskParts = @(Get-Partition -DiskNumber $DiskNumber -ErrorAction SilentlyContinue)
    if (@($diskParts | Where-Object { $_.DriveLetter -in @('C','D') }).Count -gt 0) {
        throw 'The target contains C: or D: and is protected.'
    }
    if ($Execute) {
        if ([string]::IsNullOrWhiteSpace($ExpectedSerial) -or $ExpectedSize -eq 0) {
            throw 'Execution requires the exact ExpectedSerial and ExpectedSize from the read-only disk list.'
        }
        if ([string]::IsNullOrWhiteSpace([string]$disk.SerialNumber)) {
            throw 'The adapter does not expose a serial number. Inspect the device manually before adapting this installer.'
        }
        if ($disk.SerialNumber.Trim() -cne $ExpectedSerial.Trim() -or $disk.Size -ne $ExpectedSize) {
            throw 'Disk identity changed. No further disk operation is permitted.'
        }
    }
    return $disk
}

if ($DiskNumber -lt 0) {
    Get-Disk | Where-Object { $_.BusType -eq 'USB' } |
        Select-Object Number,FriendlyName,SerialNumber,Size,IsBoot,IsSystem |
        Format-List
    Write-Host 'Read-only inventory. Choose the intended SSD explicitly; nothing was written.'
    return
}

$target = Get-CheckedTarget
$target | Select-Object Number,FriendlyName,SerialNumber,Size,BusType | Format-List
Write-Host 'Layout: 512 MiB FAT32 boot + 64 GiB ext4 system + NTFS to the end of the disk.'
if (-not $Execute) {
    Write-Host 'PLAN ONLY. No writes. Add -ExpectedSerial and -ExpectedSize, then -Execute, to erase and install.'
    return
}

$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from PowerShell as Administrator. It does not elevate itself.'
}

if (-not $FinalizeOnly) {
    if (-not (Test-Path -LiteralPath $imagePath -PathType Leaf)) { throw 'Prepared image is missing.' }
    if (-not (Test-Path -LiteralPath $ImagerPath -PathType Leaf)) { throw 'Raspberry Pi Imager executable is missing.' }
    $expectedHash = ((Get-Content -LiteralPath $hashPath -Raw).Trim() -split '\s+')[0]
    if ($expectedHash -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid image checksum file.' }
    if ((Get-FileHash -LiteralPath $imagePath -Algorithm SHA256).Hash -ine $expectedHash) {
        throw 'The image does not match its verified checksum.'
    }
    $null = Get-CheckedTarget
    # Imager 2.0.3 compares this string case-sensitively against its drive list.
    $devicePath = '\\.\PhysicalDrive{0}' -f $DiskNumber
    $imagerLog = Join-Path $PSScriptRoot 'imager-flash.log'
    Write-Host "ERASING AND WRITING: $devicePath ($($target.FriendlyName), serial $ExpectedSerial)"
    # The normal Imager protection of system drives and read-back verification stay enabled.
    $imagerArgs = '--cli --disable-eject --log-file "{0}" "{1}" "{2}"' -f $imagerLog,$imagePath,$devicePath
    $writer = Start-Process -FilePath $ImagerPath -ArgumentList $imagerArgs -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'imager-stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'imager-stderr.txt')
    if ($writer.ExitCode -ne 0) { throw "Imager failed with exit code $($writer.ExitCode). See imager-flash.log." }
}

Update-HostStorageCache
$null = Get-CheckedTarget
$parts = @(Get-Partition -DiskNumber $DiskNumber | Sort-Object PartitionNumber)
if ($parts.Count -ne 3) { throw 'Expected exactly three partitions; refusing to resize anything.' }
if ($parts[0].Offset -ne 8388608 -or $parts[0].Size -ne 536870912 -or
    $parts[1].Offset -ne 545259520 -or $parts[1].Size -ne 68719476736 -or
    $parts[2].Offset -ne 69264736256) {
    throw 'Unexpected partition boundaries; refusing to resize anything.'
}
$dataPartition = $parts[2]
if ($dataPartition.PartitionNumber -ne 3 -or $dataPartition.MbrType -ne 7) {
    throw 'The third partition is not the prepared NTFS data partition.'
}
$dataVolume = $dataPartition | Get-Volume
if ($dataVolume.FileSystem -ne 'NTFS' -or $dataVolume.FileSystemLabel -ne 'FORMULA_LOGS') {
    throw 'Expected FORMULA_LOGS / NTFS. No formatting will be attempted.'
}
$limit = Get-PartitionSupportedSize -DiskNumber $DiskNumber -PartitionNumber 3
if ($limit.SizeMax -lt $dataPartition.Size) { throw 'Invalid maximum NTFS size.' }
$null = Get-CheckedTarget
if ($limit.SizeMax -gt $dataPartition.Size) {
    Resize-Partition -DiskNumber $DiskNumber -PartitionNumber 3 -Size $limit.SizeMax
}
$dataPartition = Get-Partition -DiskNumber $DiskNumber -PartitionNumber 3
if (-not $dataPartition.DriveLetter) {
    Add-PartitionAccessPath -DiskNumber $DiskNumber -PartitionNumber 3 -AssignDriveLetter
}
$finalParts = @(Get-Partition -DiskNumber $DiskNumber | Sort-Object PartitionNumber)
if ($finalParts[1].Size -ne 68719476736) { throw 'System partition size changed unexpectedly.' }
$finalData = $finalParts[2] | Get-Volume
if ($finalData.FileSystem -ne 'NTFS' -or $finalData.FileSystemLabel -ne 'FORMULA_LOGS') {
    throw 'Final NTFS verification failed.'
}
@{
    completed_local = (Get-Date -Format o)
    disk_number = $DiskNumber
    serial = $ExpectedSerial
    disk_bytes = $ExpectedSize
    root_bytes = $finalParts[1].Size
    ntfs_bytes = $finalParts[2].Size
    ntfs_drive_letter = [string]$finalParts[2].DriveLetter
    image_written_this_run = (-not $FinalizeOnly.IsPresent)
    physical_pi_boot_tested = $false
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'FLASH_RESULT.json') -Encoding utf8
$finalParts | Select-Object PartitionNumber,DriveLetter,Offset,Size | Format-Table -AutoSize
Write-Host 'DONE. Safely eject the SSD, install it in the powered-off Pi, then boot.'
Write-Host 'SSH: ssh logger@formula-logger.local    SMB: \\formula-logger\logy'
