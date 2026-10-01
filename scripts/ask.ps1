param([Parameter(Mandatory)][string]$Key,[Parameter(Mandatory)][string]$Question)
. "$PSScriptRoot/config.ps1"
Push-Location $Root
try {
  $prompt = "Run prompts/ask.md.`nKEY: $Key`nQUESTION: $Question"
  & claude -p $prompt --allowedTools "Read,Grep,Glob" --max-turns 15
} finally { Pop-Location }
