$ErrorActionPreference = 'Stop'
$script = 'C:\Users\Administrator\.openclaw\workspace\scripts\windows\open_file_dialog_host.ps1'
Start-Process powershell.exe -ArgumentList @('-NoProfile','-STA','-ExecutionPolicy','Bypass','-File', $script)
Start-Sleep -Milliseconds 1500
Write-Output 'OPEN_FILE_DIALOG_HOST_STARTED'
