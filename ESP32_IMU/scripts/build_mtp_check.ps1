$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
$env:TEMP=Join-Path $root '.cache';$env:TMP=$env:TEMP
$vs=& 'C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe' -latest -products '*' -property installationPath
$developerScript=Join-Path $vs 'Common7/Tools/VsDevCmd.bat'
$batch='@call "'+$developerScript+'" -no_logo -arch=x64'+"`r`n"+'cl /nologo /std:c++17 /EHsc tests\mtp_check.cpp /Fo.cache\mtp-check.obj /Fe.cache\mtp-check.exe /Fd.cache\mtp-check.pdb ole32.lib PortableDeviceGuids.lib'+"`r`n"
[IO.File]::WriteAllText((Join-Path $root '.cache/build-mtp-check.cmd'),$batch)
& $env:ComSpec /c '.cache\build-mtp-check.cmd'
if ($LASTEXITCODE -ne 0) { throw 'USB test build failed.' }
