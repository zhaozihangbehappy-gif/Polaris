$ErrorActionPreference = 'Stop'

param(
  [string]$BridgeUrl = 'http://127.0.0.1:7788',
  [string]$WindowTitlePattern = '*Blender*',
  [string]$WindowClass = 'GHOST_WindowClass'
)

function PostJson($path, $obj) {
  $headers = @{ 'x-openclaw-desktop-key' = $env:OPENCLAW_DESKTOP_KEY; 'Content-Type' = 'application/json' }
  $body = $obj | ConvertTo-Json -Depth 8 -Compress
  Invoke-WebRequest -UseBasicParsing -Uri ($BridgeUrl.TrimEnd('/') + '/' + $path) -Method POST -Headers $headers -Body $body -TimeoutSec 15 | Select-Object -ExpandProperty Content
}

if (-not $env:OPENCLAW_DESKTOP_KEY) {
  throw 'OPENCLAW_DESKTOP_KEY is not set'
}

Write-Host '[1/4] enumerate windows'
$listJson = PostJson 'window.inspect' @{ action = 'list' }
$list = $listJson | ConvertFrom-Json
$win = $list.data.windows |
  Where-Object { $_.title -like $WindowTitlePattern } |
  Where-Object { $_.class_name -eq $WindowClass } |
  Select-Object -First 1
if (-not $win) {
  throw 'Blender window not found; bridge precondition failed'
}
Write-Host ("Found hwnd=" + $win.hwnd + " title=" + $win.title)

$selector = @{ hwnd = [int]$win.hwnd }

Write-Host '[2/4] activate target window'
$activate = PostJson 'window.inspect' @{ action = 'activate'; window = $selector }
Write-Host $activate
Start-Sleep -Milliseconds 500

Write-Host '[3/4] capture current Blender window'
$capture = PostJson 'desktop.capture' @{ target = 'window'; window = $selector; format = 'png'; purpose = 'blender-bridge-preflight' }
Write-Host $capture

Write-Host '[4/4] perform harmless foreground-verified move'
$centerX = [int]($win.rect.left + ($win.rect.width / 2))
$centerY = [int]($win.rect.top + ($win.rect.height / 2))
$move = PostJson 'desktop.input' @{ action = 'move'; x = $centerX; y = $centerY; window = $selector; verifyForeground = $true; abortKey = 'esc'; reason = 'blender-bridge-preflight-move' }
Write-Host $move

Write-Host 'blender bridge / GUI preflight OK'
