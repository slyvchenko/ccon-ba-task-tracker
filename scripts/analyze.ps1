# Bot run for one task
param([Parameter(Mandatory)][string]$Key)
. "$PSScriptRoot/config.ps1"
. "$PSScriptRoot/lib.ps1"
Push-Location $Root
try {
  $prompt = "Run prompts/analyze.md.`nKEY: $Key`nTICKET: inbox/$Key.json`nSTATE: state/tasks/$Key.json`nTODAY: $((Get-Today).ToString('yyyy-MM-dd'))"
  $result = & claude -p $prompt --allowedTools "Read,Grep,Glob" --max-turns 25
  New-Item -ItemType Directory -Force analysis | Out-Null
  $rel = "analysis/$Key-$((Get-Today).ToString('yyyy-MM-dd')).md"
  $result | Set-Content $rel -Encoding utf8
  Register-Bundle $Key $rel
} finally { Pop-Location }
