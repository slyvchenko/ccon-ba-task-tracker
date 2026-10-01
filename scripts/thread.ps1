param([Parameter(Mandatory)][string]$Key)
. "$PSScriptRoot/config.ps1"
Push-Location $Root
try {
  $case = "cases/$Key"
  if (-not (Test-Path "$case/case.md")) { Copy-Item 'templates/case-template.md' "$case/case.md" }
  $prompt = "Run prompts/thread.md.`nKEY: $Key`nCASE: $case/case.md`nMAIL: $case/mail/`nTICKET: inbox/$Key.json"
  & claude -p $prompt --allowedTools "Read,Grep,Glob" --max-turns 20
} finally { Pop-Location }
