param([ValidateSet('build','backup','upload','restore','ports','preview','test')][string]$Action = 'build', [string]$Port, [string]$Backup)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
$env:TEMP = Join-Path $root '.cache'
$env:TMP = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PLATFORMIO_CORE_DIR = Join-Path $root '.tools/platformio'
$env:PLATFORMIO_SETTING_ENABLE_TELEMETRY = 'No'
$env:PIP_CACHE_DIR = Join-Path $root '.cache/pip'
$python = Join-Path $root '.tools/venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Nejdříve spusť scripts/setup.ps1.' }
switch ($Action) {
  build { & $python -B -m platformio run }
  ports { & $python -B -m serial.tools.list_ports -v }
  backup { & $python -B scripts/flash.py backup --port $Port }
  upload { if ($Backup) { & $python -B scripts/flash.py upload --port $Port --backup $Backup } else { & $python -B scripts/flash.py upload --port $Port } }
  restore { & $python -B scripts/flash.py restore --port $Port --backup $Backup }
  preview { & $python -B scripts/preview.py }
  test { & $python -B tests/check.py }
}
if ($LASTEXITCODE -ne 0) { throw "Akce $Action selhala ($LASTEXITCODE)." }
