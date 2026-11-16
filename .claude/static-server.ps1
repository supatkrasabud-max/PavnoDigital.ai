# Static file server for previewing PavnoStudio-main/dist locally (no Node/Python needed).
param([int]$Port = 8765)
$root = Join-Path $PSScriptRoot '..\PavnoStudio-main\dist' | Resolve-Path | Select-Object -ExpandProperty Path
$mime = @{ '.html'='text/html; charset=utf-8'; '.js'='text/javascript; charset=utf-8'; '.css'='text/css; charset=utf-8';
  '.png'='image/png'; '.jpg'='image/jpeg'; '.jpeg'='image/jpeg'; '.svg'='image/svg+xml'; '.pdf'='application/pdf';
  '.mp4'='video/mp4'; '.json'='application/json'; '.ico'='image/x-icon'; '.webp'='image/webp' }
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()
Write-Host "Serving $root at http://localhost:$Port/"
while ($listener.IsListening) {
  $ctx = $listener.GetContext()
  try {
    $rel = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath).TrimStart('/')
    $path = [IO.Path]::GetFullPath((Join-Path $root $rel))
    if (-not $path.StartsWith($root)) { $ctx.Response.StatusCode = 403 }
    else {
      if (Test-Path $path -PathType Container) { $path = Join-Path $path 'index.html' }
      if (Test-Path $path -PathType Leaf) {
        $bytes = [IO.File]::ReadAllBytes($path)
        $ext = [IO.Path]::GetExtension($path).ToLower()
        if ($mime.ContainsKey($ext)) { $ctx.Response.ContentType = $mime[$ext] } else { $ctx.Response.ContentType = 'application/octet-stream' }
        $ctx.Response.ContentLength64 = $bytes.Length
        $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
      } else { $ctx.Response.StatusCode = 404 }
    }
    Write-Host "$($ctx.Response.StatusCode) $($ctx.Request.Url.AbsolutePath)"
  } catch { Write-Host "ERR $($_.Exception.Message)" }
  finally { $ctx.Response.Close() }
}
