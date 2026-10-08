$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$env:PYTHONIOENCODING = 'utf-8'
$taskLog = Join-Path $taskRoot ('logs\homepage-' + (Get-Date -Format 'yyyy-MM-dd-HHmmss') + '.log')
New-Item -ItemType Directory -Path (Join-Path $taskRoot 'logs') -Force | Out-Null
& (Join-Path $taskRoot '.venv\Scripts\python.exe') (Join-Path $taskRoot 'refresh_homepage.py') --apply 2>&1 | Tee-Object -FilePath $taskLog
exit $LASTEXITCODE
