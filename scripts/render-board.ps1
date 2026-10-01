$Root = Split-Path $PSScriptRoot -Parent
$path = Join-Path $Root 'state/buckets.json'
if (-not (Test-Path $path)) { throw 'Run bucket.ps1 first' }
$data = Get-Content $path -Raw | ConvertFrom-Json
$data | Sort-Object bucket, score -Descending | Format-Table key,bucket,state,due,summary -AutoSize
