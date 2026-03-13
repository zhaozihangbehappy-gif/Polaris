$ErrorActionPreference = 'Stop'
$p = Start-Process notepad.exe -PassThru
Start-Sleep -Milliseconds 800
$ws = New-Object -ComObject WScript.Shell
$null = $ws.AppActivate($p.Id)
Start-Sleep -Milliseconds 250
$ws.SendKeys('^o')
Start-Sleep -Milliseconds 1200
Write-Output 'NOTEPAD_OPEN_DIALOG_STARTED'
