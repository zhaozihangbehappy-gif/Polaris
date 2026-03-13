$ErrorActionPreference = 'Stop'

function PostJson($path, $obj) {
  $headers = @{ 'x-openclaw-desktop-key' = $env:OPENCLAW_DESKTOP_KEY; 'Content-Type' = 'application/json' }
  $body = $obj | ConvertTo-Json -Depth 8 -Compress
  Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:7788/" + $path) -Method POST -Headers $headers -Body $body -TimeoutSec 15 | Select-Object -ExpandProperty Content
}

if (-not $env:OPENCLAW_DESKTOP_KEY) {
  throw 'OPENCLAW_DESKTOP_KEY is not set'
}

Write-Host '[1/3] list windows'
$list = PostJson 'window.inspect' @{ action = 'list' }
Write-Host $list

Write-Host '[2/3] locate Blender window'
$inspect = $list | ConvertFrom-Json
$win = $inspect.data.windows | Where-Object { $_.title -like '*Blender*' } | Select-Object -First 1
if (-not $win) { throw 'No Blender window found' }
Write-Host ("Found hwnd=" + $win.hwnd + " title=" + $win.title)

Write-Host '[3/3] capture target window'
$capture = PostJson 'desktop.capture' @{ target = 'window'; window = @{ hwnd = [int]$win.hwnd }; format = 'png'; purpose = 'preflight-capture' }
Write-Host $capture

Write-Host 'desktop bridge preflight OK'
