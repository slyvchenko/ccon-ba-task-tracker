param([int]$OlderThanDays=90)
$Root = Split-Path $PSScriptRoot -Parent
$cutoff = (Get-Date).AddDays(-$OlderThanDays)
Get-ChildItem (Join-Path $Root 'cases') -Directory | Where-Object { $_.LastWriteTime -lt $cutoff } | ForEach-Object {
  Move-Item $_.FullName (Join-Path $Root "archive/$($_.Name)") -Force
}
