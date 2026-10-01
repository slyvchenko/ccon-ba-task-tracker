function Get-Today { (Get-Date).Date }
function Get-NowIso { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }
function Register-Bundle([string]$Key,[string]$Rel){
  $p = Join-Path (Split-Path $PSScriptRoot -Parent) "state/tasks/$Key.json"
  if(Test-Path $p){ $s = Get-Content $p -Raw | ConvertFrom-Json } else { $s = [pscustomobject]@{key=$Key;state='captured'} }
  $s | Add-Member -NotePropertyName lastBundle -NotePropertyValue $Rel -Force
  $s | ConvertTo-Json -Depth 8 | Set-Content $p -Encoding utf8
}
