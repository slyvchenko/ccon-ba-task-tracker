$Root = Split-Path $PSScriptRoot -Parent
$Source = 'csv'
$JiraBaseUrl = 'https://<site>.atlassian.net'
$JiraEmail = '<you@company.com>'
$JiraSecretName = 'JiraToken'
$MyAccountId = '<your Atlassian accountId>'
$MyWorkJql = 'assignee = currentUser() AND statusCategory != Done ORDER BY priority DESC, updated ASC'
$BusinessWeight = @{ Highest = 4; High = 3; Medium = 2; Low = 1; Lowest = 0 }
$P1BusinessPriorities = @('Highest')
$DeadlineDays = 2
$StaleDays = 30
$CapacityP2 = 15
$CapacityP3 = 5
$MaxAnalyze = 25
$MailDrop = Join-Path $Root 'mail-drop'
$CompanyDomain = '<company.com>'
