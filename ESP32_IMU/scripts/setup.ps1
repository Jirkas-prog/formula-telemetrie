$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
New-Item -ItemType Directory -Force -Path '.tools','.cache' | Out-Null
$env:TEMP = Join-Path $root '.cache'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $root '.cache/pip'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -B -m venv .tools/venv
if ($LASTEXITCODE -ne 0) { throw 'Nelze vytvořit Python prostředí.' }
& .tools/venv/Scripts/python.exe -B -m pip install --disable-pip-version-check platformio==6.2.0 esptool==4.12.0
if ($LASTEXITCODE -ne 0) { throw 'Instalace nástrojů selhala.' }
