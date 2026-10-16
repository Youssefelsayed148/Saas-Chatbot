<#
.SYNOPSIS
  Stop and remove the dev stack started by dev_up.ps1.
.DESCRIPTION
  Removes the containers and network. Volumes (database and uploads) are kept unless
  -RemoveVolumes is passed. Images are kept.
#>
[CmdletBinding()]
param([switch]$RemoveVolumes)
$ErrorActionPreference = 'Stop'
function Quiet {
  # Native stderr must not become a terminating error under -ErrorAction Stop (PS 5.1).
  $ErrorActionPreference = 'Continue'
  & docker @args *> $null
  return $LASTEXITCODE
}

foreach ($name in 'saas-dev-web', 'saas-dev-worker', 'saas-dev-api', 'saas-dev-db') {
  if ((Quiet container inspect $name) -eq 0) {
    Quiet rm -f $name | Out-Null
    Write-Host "removed container $name"
  }
}
if ((Quiet network rm saas-dev-net) -eq 0) { Write-Host 'removed network saas-dev-net' }
if ($RemoveVolumes) {
  foreach ($volume in 'saas-dev-pgdata', 'saas-dev-appdata') {
    if ((Quiet volume rm $volume) -eq 0) { Write-Host "removed volume $volume" }
  }
} else {
  Write-Host 'Volumes kept (saas-dev-pgdata, saas-dev-appdata). Use -RemoveVolumes to delete them.'
}
