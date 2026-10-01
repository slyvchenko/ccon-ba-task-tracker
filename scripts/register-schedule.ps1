param([string]$TaskName='CCON BA Tracker',[string]$Time='08:00')
$script = Join-Path $PSScriptRoot 'run-tracker.ps1'
$action = New-ScheduledTaskAction -Execute 'pwsh.exe' -Argument "-NoProfile -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Force
