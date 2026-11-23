$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
$env:TEMP=Join-Path $root '.cache';$env:TMP=$env:TEMP
$locator='C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
if (!(Test-Path -LiteralPath $locator)) { throw 'Test obnovy vyžaduje Visual Studio C++ Build Tools.' }
$vs=& $locator -latest -products '*' -property installationPath
$developerScript=Join-Path $vs 'Common7/Tools/VsDevCmd.bat'
$batch='@call "'+$developerScript+'" -no_logo -arch=x64'+"`r`n"
foreach ($name in @('recovery_native','recovery_integration','sampling_native','network_native')) {
  $batch+='cl /nologo /std:c++17 /EHsc tests\'+$name+'.cpp /Fo.cache\'+$name+'.obj /Fe.cache\'+$name+'.exe /Fd.cache\'+$name+'.pdb'+"`r`n"
  $batch+='if errorlevel 1 exit /b 1'+"`r`n"
  $batch+='.cache\'+$name+'.exe'+"`r`n"+'if errorlevel 1 exit /b 1'+"`r`n"
}
[IO.File]::WriteAllText((Join-Path $root '.cache/test-recovery.cmd'),$batch)
& $env:ComSpec /c '.cache\test-recovery.cmd'
if ($LASTEXITCODE -ne 0) { throw 'Test obnovy selhal.' }
