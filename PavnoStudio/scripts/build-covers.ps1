# สร้างรูปจากแม่แบบ HTML ใน design/covers ด้วย Chrome headless (เรนเดอร์ 2 เท่าแล้วย่อให้คม)
#   ปกสินค้า:   .\scripts\build-covers.ps1                      -> dist/assets/products/<id>-cover.jpg (580x820)
#   ภาพ mockup: .\scripts\build-covers.ps1 -Page mockup -W 1200 -H 1200 -Suffix book   -OutDir dist\assets\mockups
#               .\scripts\build-covers.ps1 -Page mockup -W 1200 -H 1200 -Suffix inside -OutDir dist\assets\mockups
param([string[]]$Ids = @('thai-abc','abc-tracing','hiragana','kanji-g1','chinese-60','math-add','math-sub','math-mul','math-div','math-bundle','coloring'),
      [string]$Page = 'cover', [int]$W = 580, [int]$H = 820, [string]$OutDir = '', [string]$Suffix = 'cover')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$root = Split-Path $PSScriptRoot -Parent
if (-not $OutDir) { $OutDir = Join-Path $root 'dist\assets\products' }
if (-not [System.IO.Path]::IsPathRooted($OutDir)) { $OutDir = Join-Path $root $OutDir }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$html = [System.IO.Path]::Combine($root, 'design', 'covers', "$Page.html").Replace([string][char]92, '/')
$tmp = Join-Path $env:TEMP 'pavno-covers'; New-Item -ItemType Directory -Force $tmp | Out-Null
$enc = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object MimeType -eq 'image/jpeg'
$ep = New-Object System.Drawing.Imaging.EncoderParameters 1
$ep.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter ([System.Drawing.Imaging.Encoder]::Quality), 90L
foreach ($id in $Ids) {
  $png = Join-Path $tmp "$id-$Suffix.png"
  if (Test-Path $png) { Remove-Item $png }
  $url = 'file:///' + $html.Replace(' ', '%20') + "?id=$id&v=$Suffix"
  $args = @('--headless=new','--disable-gpu','--hide-scrollbars','--allow-file-access-from-files','--force-device-scale-factor=2',"--window-size=$W,$H",'--virtual-time-budget=8000',"--screenshot=$png",$url)
  Start-Process -FilePath $chrome -ArgumentList $args -Wait -NoNewWindow -RedirectStandardError (Join-Path $tmp 'chrome.log')
  if (-not (Test-Path $png)) { throw "render failed: $id ($url)" }
  $src = [System.Drawing.Image]::FromFile($png)
  $bmp = New-Object System.Drawing.Bitmap $W, $H
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = 'HighQualityBicubic'; $g.SmoothingMode = 'HighQuality'; $g.PixelOffsetMode = 'HighQuality'
  $g.DrawImage($src, 0, 0, $W, $H)
  $out = Join-Path $OutDir "$id-$Suffix.jpg"
  $bmp.Save($out, $enc, $ep)
  $g.Dispose(); $bmp.Dispose(); $src.Dispose()
  Write-Output "ok $id"
}
