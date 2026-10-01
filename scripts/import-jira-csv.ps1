param([Parameter(Mandatory)][string]$Path)
$Root = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force (Join-Path $Root 'inbox') | Out-Null
Import-Csv $Path | ForEach-Object {
  $key = $_.Key
  if (-not $key) { return }
  [pscustomobject]@{ key=$key; summary=$_.Summary; status=$_.Status; priority=$_.Priority; created=$_.Created; updated=$_.Updated; source='csv' } |
    ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Root "inbox/$key.json") -Encoding utf8
}
