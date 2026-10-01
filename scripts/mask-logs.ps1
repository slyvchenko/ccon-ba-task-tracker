param([Parameter(Mandatory)][string]$Key)
$Root = Split-Path $PSScriptRoot -Parent
$src = Join-Path $Root "logs/$Key/raw"
$dst = Join-Path $Root "logs/$Key/masked"
New-Item -ItemType Directory -Force $dst | Out-Null
Get-ChildItem $src -File | ForEach-Object {
  $t = Get-Content $_.FullName -Raw
  $t = $t -replace '(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}','[EMAIL]'
  $t = $t -replace '\+?\d[\d\s\-()]{7,}\d','[PHONE]'
  $t | Set-Content (Join-Path $dst $_.Name) -Encoding utf8
}
