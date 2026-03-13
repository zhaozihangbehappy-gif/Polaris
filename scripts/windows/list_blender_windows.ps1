$ErrorActionPreference = 'Stop'
Get-Process -Name blender -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } |
  Select-Object ProcessName,Id,MainWindowTitle,MainWindowHandle |
  ConvertTo-Json -Compress
