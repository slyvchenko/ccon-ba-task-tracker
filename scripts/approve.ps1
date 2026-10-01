param([Parameter(Mandatory)][string[]]$Keys)
$Root = Split-Path $PSScriptRoot -Parent
foreach($k in $Keys){ Write-Host "Review and apply pending proposal for $k" }
