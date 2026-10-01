param([Parameter(Mandatory)][string]$Key)
. "$PSScriptRoot/config.ps1"
. "$PSScriptRoot/lib.ps1"
Push-Location $Root
try {
  if (-not (Test-Path "notes/$Key.md")) { throw "Create notes/$Key.md first" }
  $prompt = "Run prompts/capture.md.`nKEY: $Key`nTICKET: inbox/$Key.json`nSTATE: state/tasks/$Key.json`nNOTES: notes/$Key.md"
  $result = & claude -p $prompt --allowedTools "Read,Grep,Glob" --max-turns 15
  $rel = "analysis/$Key-$((Get-Today).ToString('yyyy-MM-dd'))-capture.md"
  $result | Set-Content $rel -Encoding utf8
  Register-Bundle $Key $rel
} finally { Pop-Location }
