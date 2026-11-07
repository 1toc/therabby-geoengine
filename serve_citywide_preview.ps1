param(
    [ValidateRange(1024, 65535)][int]$Port = 8767,
    [switch]$NoBrowser,
    [switch]$StationLod2
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$listener = $null
$selectedPort = $null

function Send-TextResponse([IO.Stream]$stream, [int]$status, [string]$reason, [string]$message, [bool]$headOnly) {
    $body = [Text.Encoding]::UTF8.GetBytes($message)
    $header = [Text.Encoding]::ASCII.GetBytes("HTTP/1.1 $status $reason`r`nContent-Type: text/plain; charset=utf-8`r`nContent-Length: $($body.Length)`r`nConnection: close`r`nCache-Control: no-store`r`n`r`n")
    $stream.Write($header, 0, $header.Length)
    if (-not $headOnly) { $stream.Write($body, 0, $body.Length) }
}

function Handle-Client([Net.Sockets.TcpClient]$client) {
    $stream = $client.GetStream()
    $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::ASCII, $false, 1024, $true)
    try {
        $line = $reader.ReadLine()
        if ($null -eq $line) { return }
        if ($line -notmatch '^(GET|HEAD) (\S+) HTTP/1\.[01]$') {
            Send-TextResponse $stream 400 'Bad Request' 'Only HTTP GET and HEAD are supported.' $false
            return
        }
        $method = $Matches[1]
        $requestTarget = $Matches[2]
        $headersEnded = $false
        for ($n = 0; $n -lt 100; $n++) {
            $headerLine = $reader.ReadLine()
            if ($null -eq $headerLine -or $headerLine -eq '') { $headersEnded = $true; break }
        }
        if (-not $headersEnded) {
            Send-TextResponse $stream 431 'Request Header Fields Too Large' 'Too many request headers.' ($method -eq 'HEAD')
            return
        }
        $urlPath = $requestTarget.Split('?')[0]
        if (-not $urlPath.StartsWith('/')) {
            Send-TextResponse $stream 400 'Bad Request' 'Invalid URL path.' ($method -eq 'HEAD')
            return
        }
        $decoded = [Uri]::UnescapeDataString($urlPath)
        if ($decoded.Contains([char]0)) {
            Send-TextResponse $stream 400 'Bad Request' 'Invalid URL path.' ($method -eq 'HEAD')
            return
        }
        if ($decoded -eq '/') { $decoded = '/viewer/citywide-v1.html' }
        $relative = $decoded.TrimStart([char]'/').Replace('/', [IO.Path]::DirectorySeparatorChar)
        $file = [IO.Path]::GetFullPath([IO.Path]::Combine($root, $relative))
        if (-not $file.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            Send-TextResponse $stream 403 'Forbidden' 'Path outside the preview is forbidden.' ($method -eq 'HEAD')
            return
        }
        if (-not [IO.File]::Exists($file)) {
            Send-TextResponse $stream 404 'Not Found' 'File not found.' ($method -eq 'HEAD')
            return
        }
        $type = switch ([IO.Path]::GetExtension($file).ToLowerInvariant()) {
            '.html' { 'text/html; charset=utf-8' }
            '.js'   { 'text/javascript; charset=utf-8' }
            '.json' { 'application/json; charset=utf-8' }
            '.md'   { 'text/plain; charset=utf-8' }
            '.glb'  { 'model/gltf-binary' }
            default { 'application/octet-stream' }
        }
        $source = [IO.File]::Open($file, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        try {
            $header = [Text.Encoding]::ASCII.GetBytes("HTTP/1.1 200 OK`r`nContent-Type: $type`r`nContent-Length: $($source.Length)`r`nConnection: close`r`nCache-Control: no-store`r`n`r`n")
            $stream.Write($header, 0, $header.Length)
            if ($method -eq 'GET') { $source.CopyTo($stream) }
        } finally {
            $source.Dispose()
        }
    } finally {
        $reader.Dispose()
    }
}

for ($candidate = $Port; $candidate -le [Math]::Min(65535, $Port + 20); $candidate++) {
    $probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $candidate)
    try {
        $probe.Start()
        $listener = $probe
        $selectedPort = $candidate
        break
    } catch [Net.Sockets.SocketException] {
        $probe.Stop()
        if ($_.Exception.SocketErrorCode -ne [Net.Sockets.SocketError]::AddressAlreadyInUse) { throw }
    }
}
if ($null -eq $listener) { throw "No free local preview port from $Port through $([Math]::Min(65535, $Port + 20))." }

try {
    $query = if ($StationLod2) { 'station_lod2=1&photo_stream=all' } else { 'benchmark=1' }
    $url = "http://127.0.0.1:$selectedPort/viewer/citywide-v1.html?$query"
    Write-Host "Local preview server: $url"
    Write-Host 'Keep this window open while using the viewer. Press Ctrl+C to stop.'
    if (-not $NoBrowser) { Start-Process -FilePath $url }
    while ($true) {
        $client = $listener.AcceptTcpClient()
        $client.ReceiveTimeout = 10000
        $client.SendTimeout = 30000
        try { Handle-Client $client }
        catch { Write-Warning "Request failed: $($_.Exception.Message)" }
        finally { $client.Dispose() }
    }
} finally {
    $listener.Stop()
}
