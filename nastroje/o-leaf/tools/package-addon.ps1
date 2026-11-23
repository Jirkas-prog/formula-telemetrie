$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '../oleaf')).Path
$packageInfo = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'app/package.json') | ConvertFrom-Json
$version = $packageInfo.version
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid package version.' }
$configText = Get-Content -Raw -LiteralPath (Join-Path $sourceRoot 'config.yaml')
if ($configText -notmatch ('version:\s*"' + [regex]::Escape($version) + '"')) { throw 'Version mismatch.' }
$installRoot = Join-Path $workspaceRoot "HomeAssistant_Addon_O-Leaf_$version"
$stageRoot = Join-Path $installRoot 'oleaf'
$zipPath = Join-Path $workspaceRoot "O-Leaf_HomeAssistant_Addon_$version.zip"
$latestPath = Join-Path $workspaceRoot 'oleaf-homeassistant-addon-source.zip'
$null = New-Item -ItemType Directory -Force -Path $stageRoot

$files = @(Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Force | Where-Object {
    $_.FullName -notmatch '[\\/](node_modules|\.git|data|tmp)[\\/]'
})
$expected = @{}
foreach ($file in $files) {
    $relative = $file.FullName.Substring($sourceRoot.Length + 1)
    $target = Join-Path $stageRoot $relative
    $null = New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent)
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    $expected['oleaf/' + $relative.Replace('\', '/')] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
}
if (@(Get-ChildItem -LiteralPath $stageRoot -Recurse -File -Force).Count -ne $files.Count) {
    throw 'Install folder contains unexpected files. Nothing was deleted; inspect it before packaging.'
}

# Use a new temporary archive, then replace only the named build artifacts.
# ZipFile includes dotfiles such as .dockerignore, unlike Compress-Archive.
$tempZip = Join-Path $workspaceRoot ([IO.Path]::GetRandomFileName() + '.zip')
[IO.Compression.ZipFile]::CreateFromDirectory($installRoot, $tempZip)
$archive = [IO.Compression.ZipFile]::OpenRead($tempZip)
try {
    $entries = @($archive.Entries | Where-Object { $_.Name })
    if ($entries.Count -ne $expected.Count) { throw 'ZIP file count mismatch.' }
    foreach ($entry in $entries) {
        if (-not $expected.ContainsKey($entry.FullName)) { throw "Unexpected ZIP entry: $($entry.FullName)" }
        $stream = $entry.Open()
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $hash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
        finally { $stream.Dispose(); $sha.Dispose() }
        if ($hash -ne $expected[$entry.FullName]) { throw "ZIP content mismatch: $($entry.FullName)" }
        $stageFile = Join-Path $installRoot $entry.FullName
        if ((Get-FileHash -LiteralPath $stageFile -Algorithm SHA256).Hash -ne $hash) { throw "Install content mismatch: $stageFile" }
    }
} finally { $archive.Dispose() }
Move-Item -LiteralPath $tempZip -Destination $zipPath -Force
Copy-Item -LiteralPath $zipPath -Destination $latestPath -Force
Write-Output "O-Leaf $version packaged: $($files.Count) files verified against source and install folder."
Get-Item -LiteralPath $zipPath, $latestPath | ForEach-Object {
    [pscustomobject]@{ Path = $_.FullName; Bytes = $_.Length; SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
} | ConvertTo-Json
