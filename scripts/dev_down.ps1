<# Stop the development Compose stack, keeping database and upload volumes. #>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
& "$PSScriptRoot/dev_compose.ps1" down
exit $LASTEXITCODE
