<# Start the development Compose stack. Supply keys via host env or .env.local. #>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
& "$PSScriptRoot/dev_compose.ps1" up --build -d --wait
exit $LASTEXITCODE
