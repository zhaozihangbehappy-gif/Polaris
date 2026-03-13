$ErrorActionPreference = 'Stop'
Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } |
  Where-Object { $_.MainWindowTitle -match 'Open Delivery File|打开|Open|保存|Save' } |
  Select-Object ProcessName,Id,MainWindowTitle |
  ConvertTo-Json -Compress
