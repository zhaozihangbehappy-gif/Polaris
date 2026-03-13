$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } |
  ForEach-Object {
    try {
      $el = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$_.MainWindowHandle)
      [PSCustomObject]@{
        ProcessName = $_.ProcessName
        Id = $_.Id
        MainWindowTitle = $_.MainWindowTitle
        ClassName = $el.Current.ClassName
      }
    } catch {}
  } |
  Sort-Object ProcessName,Id |
  ConvertTo-Json -Depth 4
