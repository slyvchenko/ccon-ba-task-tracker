param([Parameter(Mandatory)][string]$Key,[Parameter(Mandatory)][string]$Path)
$Root = Split-Path $PSScriptRoot -Parent
$case = Join-Path $Root "cases/$Key/mail"
New-Item -ItemType Directory -Force $case | Out-Null
Copy-Item $Path $case -Force
