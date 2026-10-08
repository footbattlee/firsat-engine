# Current-user task. Does not change Windows power/sleep settings.
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $taskRoot 'run_homepage_refresh.ps1') + '"') -WorkingDirectory $taskRoot
# Daily 10:00 trigger, repeats at :00/:30 through 23:30.
$taskTrigger = New-ScheduledTaskTrigger -Daily -At '10:00'
$taskTrigger.Repetition = (New-ScheduledTaskTrigger -Once -At '10:00' -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Hours 14)).Repetition
$taskTrigger.Repetition.Duration = 'PT14H'
$taskTrigger.Repetition.StopAtDurationEnd = $false
$taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 23) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Firsatci Homepage Prices' -Action $taskAction -Trigger $taskTrigger -Settings $taskSettings -Principal $taskPrincipal -Description 'Homepage price checks only; 10:00-23:30 every 30 minutes. No social publishing.' -Force | Out-Null
Get-ScheduledTaskInfo -TaskName 'Firsatci Homepage Prices' | Select-Object NextRunTime,LastRunTime,LastTaskResult
