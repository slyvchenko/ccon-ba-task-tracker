$Root = Split-Path $PSScriptRoot -Parent
$result = foreach($f in Get-ChildItem (Join-Path $Root 'inbox') -Filter *.json){
  $t = Get-Content $f.FullName -Raw | ConvertFrom-Json
  [pscustomobject]@{ key=$t.key; summary=$t.summary; bucket='P3'; score=0; state='captured'; due=$null }
}
$result | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Root 'state/buckets.json') -Encoding utf8
