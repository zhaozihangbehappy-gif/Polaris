$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
$out = Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } |
  ForEach-Object {
    try {
      $el = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$_.MainWindowHandle)
      $cls = $el.Current.ClassName
      [PSCustomObject]@{ ProcessName=$_.ProcessName; Id=$_.Id; MainWindowTitle=$_.MainWindowTitle; ClassName=$cls }
    } catch {}
  } |
  Where-Object { $_.ClassName -eq '#32770' -or $_.ClassName -eq 'NUIDialog' }
$json = $out | ConvertTo-Json -Compress
if (-not $json) { $json = '[]' }
Write-Output $json
