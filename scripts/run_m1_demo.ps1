# Development PC only. No Python or Blender is needed on a hospital/client PC.
param([string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not $PythonExecutable) {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonExecutable = (Get-Command python).Source
    }
}
if (-not $PythonExecutable) {
    $bundled = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    if (Test-Path $bundled) { $PythonExecutable = $bundled }
}
if (-not $PythonExecutable -and (Get-Command py -ErrorAction SilentlyContinue)) {
    & py -3 --version *> $null
    if ($LASTEXITCODE -eq 0) { $PythonExecutable = 'py' }
}
if (-not $PythonExecutable) { throw 'Python 3 not found; pass -PythonExecutable with its full path.' }
& $PythonExecutable scripts/geoengine.py build --area config/fukushima_station_east.json --osm fixtures/fictional_osm.json --plateau fixtures/minimal_plateau_lod1.gml --output dist/demo/map.json
if ($LASTEXITCODE -ne 0) { throw 'M1 build failed' }
& $PythonExecutable scripts/geoengine.py validate --map dist/demo/map.json
if ($LASTEXITCODE -ne 0) { throw 'M1 validation failed' }
Write-Host 'M1 synthetic demo generated. This is NOT real Fukushima city data.'
