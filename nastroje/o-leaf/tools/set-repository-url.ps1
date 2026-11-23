param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $RepositoryUrl
)

$ErrorActionPreference = 'Stop'

$RepositoryUrl = $RepositoryUrl.Trim().TrimEnd('/')
$uri = $null
if (-not [Uri]::TryCreate($RepositoryUrl, [UriKind]::Absolute, [ref] $uri) -or
    $uri.Scheme -ne 'https' -or
    $uri.Host -ne 'github.com') {
    throw 'Použijte URL ve tvaru https://github.com/UZIVATEL/REPOZITAR.'
}

$segments = @($uri.AbsolutePath.Trim('/').Split('/') | Where-Object { $_ })
if ($segments.Count -ne 2) {
    throw 'GitHub URL musí obsahovat právě uživatele nebo organizaci a název repozitáře.'
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$readmePath = Join-Path $repositoryRoot 'README.md'
$repositoryPath = Join-Path $repositoryRoot 'repository.yaml'
$readme = Get-Content -Raw -LiteralPath $readmePath

if ($readme -notmatch '__REPOSITORY_URL(?:_ENCODED)?__') {
    throw 'README už neobsahuje zástupnou URL. Repozitář byl pravděpodobně nastaven.'
}

$encodedUrl = [Uri]::EscapeDataString($RepositoryUrl)
$readme = $readme.Replace('__REPOSITORY_URL_ENCODED__', $encodedUrl)
$readme = $readme.Replace('__REPOSITORY_URL__', $RepositoryUrl)
[IO.File]::WriteAllText($readmePath, $readme, [Text.UTF8Encoding]::new($false))

$repository = Get-Content -Raw -LiteralPath $repositoryPath
if ($repository -match '(?m)^url:\s*') {
    $repository = [regex]::Replace($repository, '(?m)^url:.*$', "url: '$RepositoryUrl'")
} else {
    $repository = $repository.TrimEnd() + "`nurl: '$RepositoryUrl'`n"
}
[IO.File]::WriteAllText($repositoryPath, $repository, [Text.UTF8Encoding]::new($false))

Write-Output "Nastaveno: $RepositoryUrl"
Write-Output 'Nahrajte obsah této složky do kořene veřejného GitHub repozitáře.'

