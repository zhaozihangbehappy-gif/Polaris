$ErrorActionPreference = "Stop"
function PostJson($path, $obj) {
  $headers = @{ "x-openclaw-desktop-key" = "desktop-secret"; "Content-Type" = "application/json" }
  $body = $obj | ConvertTo-Json -Depth 8 -Compress
  return (Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:7788/" + $path) -Method POST -Headers $headers -Body $body -TimeoutSec 30).Content
}
$inspectJson = PostJson "window.inspect" @{ action = "list" }
$inspect = $inspectJson | ConvertFrom-Json
$win = $inspect.data.windows | Where-Object { $_.title -like "*Blender 5.0*" } | Where-Object { $_.class_name -eq "GHOST_WindowClass" } | Select-Object -First 1
if (-not $win) { throw "blender gui window not found" }
$hwnd = [int]$win.hwnd
$left = [int]$win.rect.left
$top = [int]$win.rect.top
$width = [int]$win.rect.width
$height = [int]$win.rect.height
$points = @(
  @{ x = $left + 220; y = $top + 220; label = "p1" },
  @{ x = $left + [int]($width * 0.35); y = $top + [int]($height * 0.35); label = "p2" },
  @{ x = $left + [int]($width * 0.65); y = $top + [int]($height * 0.55); label = "p3" },
  @{ x = $left + [int]($width * 0.80); y = $top + [int]($height * 0.75); label = "p4" }
)
$selector = @{ hwnd = $hwnd }
Write-Host "hwnd=$hwnd"
Write-Host "== activate =="
Write-Host (PostJson "window.inspect" @{ action = "activate"; window = $selector })
Start-Sleep -Milliseconds 700
Write-Host "== capture start =="
Write-Host (PostJson "desktop.capture" @{ target = "window"; window = $selector; format = "png"; purpose = "trajectory-start" })
foreach ($pt in $points) {
  Write-Host "== move $($pt.label) $($pt.x),$($pt.y) =="
  Write-Host (PostJson "desktop.input" @{ action = "move"; x = $pt.x; y = $pt.y; window = $selector; verifyForeground = $true; abortKey = "esc"; reason = ("trajectory-" + $pt.label) })
  Start-Sleep -Milliseconds 350
  Write-Host "== capture $($pt.label) =="
  Write-Host (PostJson "desktop.capture" @{ target = "window"; window = $selector; format = "png"; purpose = ("trajectory-" + $pt.label) })
}
$last = $points[-1]
Write-Host "== click final =="
Write-Host (PostJson "desktop.input" @{ action = "click"; x = $last.x; y = $last.y; button = "left"; window = $selector; verifyForeground = $true; abortKey = "esc"; reason = "trajectory-final-click" })
Start-Sleep -Milliseconds 350
Write-Host "== capture end =="
Write-Host (PostJson "desktop.capture" @{ target = "window"; window = $selector; format = "png"; purpose = "trajectory-end" })
