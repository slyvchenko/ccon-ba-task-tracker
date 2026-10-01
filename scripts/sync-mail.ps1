$Root = Split-Path $PSScriptRoot -Parent
$drop = Join-Path $Root 'mail-drop'
if (-not (Test-Path $drop)) { Write-Host 'No mail-drop folder'; return }
Get-ChildItem $drop -File | ForEach-Object { Write-Host "Pending mail: $($_.Name)" }
