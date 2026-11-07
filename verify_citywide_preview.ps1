param(
    [string]$PackageRoot = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PackageRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$manifestPath = [IO.Path]::Combine($root, 'preview_manifest.json')
if (-not [IO.File]::Exists($manifestPath)) {
    throw "Preview manifest is missing: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema -ne 'therabby.geoengine.citywide-static-preview.v0.1' -or
    $manifest.status -ne 'internal_preview; v1.0 acceptance pending' -or
    $manifest.acceptance_complete -ne $false -or
    $manifest.entry -ne 'viewer/citywide-v1.html' -or
    $null -eq $manifest.files -or $manifest.files.Count -eq 0) {
    throw 'Preview manifest schema, status, or entry is invalid.'
}

$paths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$count = 0
$bytes = [long]0
Write-Host "Checking preview copy: $($manifest.files.Count) files. Please wait before the browser opens."
foreach ($item in $manifest.files) {
    $relative = $item.path
    if ($relative -isnot [string] -or
        $relative -cnotmatch '^(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+$' -or
        @($relative.Split('/') | Where-Object { $_ -eq '.' -or $_ -eq '..' }).Count -ne 0 -or
        -not $paths.Add($relative)) {
        throw "Invalid or duplicate preview path: $relative"
    }
    if ($item.sha256 -isnot [string] -or $item.sha256 -cnotmatch '^[a-f0-9]{64}$' -or
        $null -eq $item.byte_length -or $item.byte_length -lt 0) {
        throw "Invalid preview size or hash: $relative"
    }
    $file = [IO.Path]::GetFullPath([IO.Path]::Combine($root, $relative.Replace('/', [IO.Path]::DirectorySeparatorChar)))
    if (-not $file.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
        -not [IO.File]::Exists($file)) {
        throw "Preview file is missing or outside the package: $relative"
    }
    $actualBytes = ([IO.FileInfo]$file).Length
    if ($actualBytes -ne [long]$item.byte_length) {
        throw "Preview file size differs: $relative"
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($file)
    try {
        $actualHash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
    if ($actualHash -cne $item.sha256) {
        throw "Preview file SHA-256 differs: $relative"
    }
    $count++
    $bytes += $actualBytes
    if ($count % 250 -eq 0) {
        Write-Host "Checked $count / $($manifest.files.Count) files..."
    }
}
if (-not $paths.Contains($manifest.entry)) {
    throw 'Preview entry is not included in the file list.'
}

$actualFiles = @(Get-ChildItem -LiteralPath $root -File -Recurse)
$measurementFiles = 0
foreach ($file in $actualFiles) {
    $relative = $file.FullName.Substring($root.Length + 1).Replace([IO.Path]::DirectorySeparatorChar, '/')
    if ($relative -eq 'preview_manifest.json' -or $paths.Contains($relative)) { continue }
    # The browser may save benchmark results directly beside the launcher.
    if ($relative -cmatch '^geoengine-citywide-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z\.json$') {
        $measurementFiles++
        continue
    }
    throw "Unlisted preview file: $relative"
}
if ($actualFiles.Count -ne $count + 1 + $measurementFiles) {
    throw "Unexpected preview file count: expected $($count + 1 + $measurementFiles), found $($actualFiles.Count)"
}
Write-Host "Preview verified: $count files, $bytes bytes. Acceptance remains pending."
