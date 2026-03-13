param(
  [Parameter(Mandatory=$true)]
  [string]$PlanPath
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class NativeMouse {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
}
"@

function Get-OrDefault($value, $defaultValue) {
  if ($null -eq $value) { return $defaultValue }
  return $value
}
function Move-Smooth([int]$sx, [int]$sy, [int]$ex, [int]$ey, [int]$steps=12, [int]$delay=12) {
  for ($i = 1; $i -le $steps; $i++) {
    $t = $i / $steps
    $x = [int]($sx + ($ex - $sx) * $t)
    $y = [int]($sy + ($ey - $sy) * $t)
    [NativeMouse]::SetCursorPos($x, $y) | Out-Null
    Start-Sleep -Milliseconds $delay
  }
}
function Click-Left() {
  [NativeMouse]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
  Start-Sleep -Milliseconds 35
  [NativeMouse]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
}
function DoubleClick-Left([int]$interval=110) {
  Click-Left
  Start-Sleep -Milliseconds $interval
  Click-Left
}

$plan = Get-Content -Raw -Encoding UTF8 $PlanPath | ConvertFrom-Json
foreach ($step in $plan.steps) {
  switch ($step.kind) {
    'activateExplorerPath' {
      $ws = New-Object -ComObject WScript.Shell
      if (-not $ws.AppActivate($step.path)) {
        Start-Process explorer.exe $step.path | Out-Null
        Start-Sleep -Milliseconds ([int](Get-OrDefault $step.waitMs 1800))
        $null = $ws.AppActivate($step.path)
      } else {
        Start-Sleep -Milliseconds 250
      }
      Start-Sleep -Milliseconds 300
    }
    'movePath' {
      $cur = [System.Windows.Forms.Cursor]::Position
      foreach ($pt in $step.points) {
        $steps = [int](Get-OrDefault $pt.steps 10)
        $delay = [int](Get-OrDefault $pt.delayMs 12)
        Move-Smooth $cur.X $cur.Y ([int]$pt.x) ([int]$pt.y) $steps $delay
        $cur = New-Object System.Drawing.Point ([int]$pt.x), ([int]$pt.y)
      }
    }
    'click' {
      Click-Left
    }
    'doubleClick' {
      DoubleClick-Left ([int](Get-OrDefault $step.intervalMs 110))
    }
    'sendKeys' {
      $ws = New-Object -ComObject WScript.Shell
      Start-Sleep -Milliseconds ([int](Get-OrDefault $step.preDelayMs 120))
      $ws.SendKeys([string]$step.text)
    }
    'wait' {
      Start-Sleep -Milliseconds ([int]$step.ms)
    }
    default {
      throw "Unknown step kind: $($step.kind)"
    }
  }
}
Write-Output 'GUI_MACRO_DONE'
