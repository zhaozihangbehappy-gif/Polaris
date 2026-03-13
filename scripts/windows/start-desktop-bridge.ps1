param(
  [string]$Repo = 'D:\Administrator\Documents\Playground\openclaw-upstream',
  [string]$ApiKey = 'desktop-secret',
  [string]$BindHost = '127.0.0.1',
  [int]$Port = 7788
)

$ErrorActionPreference = 'Stop'

$log = $env:TEMP + '\openclaw-desktop-bridge.log'
$err = $env:TEMP + '\openclaw-desktop-bridge.err.log'

$py = $null
foreach ($candidate in @('py','python','python.exe')) {
  try {
    $cmd = Get-Command $candidate -ErrorAction Stop
    $py = $cmd.Source
    break
  } catch {}
}
if (-not $py) { throw 'No Python launcher found on Windows host' }

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'bridge\.desktop_bridge\.server' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$args = '-m bridge.desktop_bridge.server --host ' + $BindHost + ' --port ' + $Port + ' --workspace-root "' + $Repo + '" --api-key ' + $ApiKey
$p = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $log -RedirectStandardError $err -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2

if ($p.HasExited) {
  Write-Output ('EXITED:' + $p.ExitCode)
  if (Test-Path $log) { Get-Content $log }
  if (Test-Path $err) { Get-Content $err }
  exit 1
}

Write-Output ('STARTED:' + $p.Id)
Write-Output ('LOG:' + $log)
Write-Output ('ERR:' + $err)
