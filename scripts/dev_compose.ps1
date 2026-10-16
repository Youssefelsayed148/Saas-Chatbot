# Shared Compose wrapper: never implicitly load .env, never echo resolved settings.
# An explicit .env.local takes precedence over Compose's default dotenv discovery.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$savedDisableEnvFile = $env:COMPOSE_DISABLE_ENV_FILE
$savedEnvFiles = $env:COMPOSE_ENV_FILES
try {
  $env:COMPOSE_DISABLE_ENV_FILE = '1'
  $env:COMPOSE_ENV_FILES = $null
  $composeArgs = @('--project-directory', $repoRoot, '-f', (Join-Path $repoRoot 'compose.yaml'))
  $localEnvFile = Join-Path $repoRoot '.env.local'
  if (Test-Path -LiteralPath $localEnvFile -PathType Leaf) {
    $composeArgs += @('--env-file', $localEnvFile)
  }
  & docker compose @composeArgs @args
  $composeExitCode = $LASTEXITCODE
} finally {
  $env:COMPOSE_DISABLE_ENV_FILE = $savedDisableEnvFile
  $env:COMPOSE_ENV_FILES = $savedEnvFiles
}
exit $composeExitCode
