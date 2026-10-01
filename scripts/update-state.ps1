$Root = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force (Join-Path $Root 'state/tasks') | Out-Null
Get-ChildItem (Join-Path $Root 'inbox') -Filter *.json | ForEach-Object {
  $t = Get-Content $_.FullName -Raw | ConvertFrom-Json
  $p = Join-Path $Root "state/tasks/$($t.key).json"
  if (-not (Test-Path $p)) {
    [pscustomobject]@{ key=$t.key; state='captured'; due=$null; next='analyze'; history=@() } | ConvertTo-Json -Depth 8 | Set-Content $p -Encoding utf8
  }
}
