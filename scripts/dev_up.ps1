<#
.SYNOPSIS
  One command to build and run the full local stack, seed the demo and enable the premium tier.

.DESCRIPTION
  Uses plain `docker` (no compose): network, volumes, pgvector db, api, worker, web.
  Provider keys are read ONLY from this process's environment and handed to containers
  with `-e NAME` (the value never appears on a command line or in output).

  Required host env:  CHAT_OPENAI_API_KEY, CHAT_OPENAI_MODEL
  Optional host env:  CHAT_OPENROUTER_API_KEY, CHAT_FREE_MODEL_CHAIN (sentiment, free tier),
                      PLATFORM_STAFF_EMAIL (default staff@example.com),
                      PLATFORM_STAFF_PASSWORD (prompted when unset), DEMO_SEED_PASSWORD,
                      API_PORT, WEB_PORT

  The database is named saas_dev (the seed and staff scripts refuse anything else) and
  is not published to the host.

.EXAMPLE
  $env:CHAT_OPENAI_API_KEY = '...'; $env:CHAT_OPENAI_MODEL = '...'; .\scripts\dev_up.ps1
#>
[CmdletBinding()]
param(
  [int]$ApiPort = $(if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }),
  [int]$WebPort = $(if ($env:WEB_PORT) { [int]$env:WEB_PORT } else { 3000 }),
  [int]$BackfillTimeoutMinutes = 20
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

$Net = 'saas-dev-net'
$PgVol = 'saas-dev-pgdata'
$AppVol = 'saas-dev-appdata'
$ApiImage = 'saas-dev-api:local'
$WebImage = 'saas-dev-web:local'
$DbUser = 'saas'
$DbName = 'saas_dev'
$ExpectedModel = 'openai:text-embedding-3-large'
# Dev-only credential for a database that is never published to the host.
$DbPassword = 'dev_only_not_a_secret'

function Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }
function Docker {
  & docker @args
  if ($LASTEXITCODE -ne 0) { throw "docker $($args[0]) failed (exit $LASTEXITCODE)." }
}
function Quiet {
  # Native stderr must not become a terminating error under -ErrorAction Stop (PS 5.1).
  $ErrorActionPreference = 'Continue'
  & docker @args *> $null
  return $LASTEXITCODE
}
function Wait-Until([scriptblock]$Test, [string]$What, [int]$Seconds = 120) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    try { if (& $Test) { return } } catch { }
    Start-Sleep -Seconds 2
  }
  throw "Timed out waiting for $What."
}

# --- Preconditions -----------------------------------------------------------------
$missing = @('CHAT_OPENAI_API_KEY', 'CHAT_OPENAI_MODEL') |
  Where-Object { -not [Environment]::GetEnvironmentVariable($_) }
if ($missing) {
  throw "Missing required environment variable(s): $($missing -join ', '). Set them in this PowerShell session first (values are never printed)."
}
if ((Quiet info) -ne 0) { throw 'Docker is not running.' }

$StaffEmail = if ($env:PLATFORM_STAFF_EMAIL) { $env:PLATFORM_STAFF_EMAIL } else { 'staff@example.com' }
if (-not $env:PLATFORM_STAFF_PASSWORD) {
  $secure = Read-Host -AsSecureString 'Platform staff password (min 8 characters)'
  $env:PLATFORM_STAFF_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}
$env:PLATFORM_STAFF_EMAIL = $StaffEmail
# Passed to containers as `-e DATABASE_URL` so it is not on any command line.
$env:DATABASE_URL = "postgresql://${DbUser}:${DbPassword}@saas-dev-db:5432/${DbName}"

# Provider keys flow host env -> container by name only.
$ProviderEnv = @('-e', 'CHAT_OPENAI_API_KEY', '-e', 'CHAT_OPENAI_MODEL')
foreach ($optional in 'CHAT_OPENROUTER_API_KEY', 'CHAT_FREE_MODEL_CHAIN') {
  if ([Environment]::GetEnvironmentVariable($optional)) { $ProviderEnv += @('-e', $optional) }
}

# --- Build, network, volumes -------------------------------------------------------
Step 'Building images'
Docker build -f apps/api/Dockerfile --target runtime -t $ApiImage .
Docker build -f apps/web/Dockerfile --build-arg API_PROXY_TARGET=http://saas-dev-api:8000 -t $WebImage .

Step 'Creating network and volumes'
if ((Quiet network inspect $Net) -ne 0) { Docker network create $Net | Out-Null }
foreach ($volume in $PgVol, $AppVol) { Docker volume create $volume | Out-Null }
# The app volume is written by the non-root `api` user.
Docker run --rm --user root -v "${AppVol}:/data" $ApiImage sh -c 'mkdir -p /data/storage && chown -R api:api /data'

foreach ($name in 'saas-dev-web', 'saas-dev-worker', 'saas-dev-api', 'saas-dev-db') {
  Quiet rm -f $name | Out-Null
}

# --- Database ----------------------------------------------------------------------
Step 'Starting pgvector database'
Docker run -d --name saas-dev-db --network $Net -v "${PgVol}:/var/lib/postgresql/data" `
  -e "POSTGRES_USER=$DbUser" -e "POSTGRES_PASSWORD=$DbPassword" -e "POSTGRES_DB=$DbName" `
  pgvector/pgvector:pg17 | Out-Null
Wait-Until { (Quiet exec saas-dev-db pg_isready -U $DbUser -d $DbName) -eq 0 } 'pg_isready' 90

# --- Migrate + API -----------------------------------------------------------------
Step 'Applying migrations'
Docker run --rm --network $Net -e DATABASE_URL -e STORAGE_ROOT=/data/storage -v "${AppVol}:/data" $ApiImage alembic upgrade head

Step 'Starting API'
Docker run -d --name saas-dev-api --network $Net -p "127.0.0.1:${ApiPort}:8000" -v "${AppVol}:/data" `
  -e DATABASE_URL -e STORAGE_ROOT=/data/storage -e ENVIRONMENT=development @ProviderEnv `
  $ApiImage | Out-Null
$ApiUrl = "http://127.0.0.1:$ApiPort"
Wait-Until { (Invoke-WebRequest "$ApiUrl/ready" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } '/ready' 120

Step 'Starting worker'
Docker run -d --name saas-dev-worker --network $Net -v "${AppVol}:/data" `
  -e DATABASE_URL -e STORAGE_ROOT=/data/storage -e ENVIRONMENT=development -e WORKER_HEARTBEAT_FILE=/tmp/worker-heartbeat @ProviderEnv `
  $ApiImage python -m app.worker | Out-Null

Step 'Building and starting web'
Docker run -d --name saas-dev-web --network $Net -p "127.0.0.1:${WebPort}:3000" $WebImage | Out-Null
Wait-Until { (Invoke-WebRequest "http://127.0.0.1:$WebPort" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } 'web' 90

# --- Seed + staff ------------------------------------------------------------------
Step 'Seeding demo tenant'
$seedEnv = @('-e', 'DATABASE_URL', '-e', 'ENVIRONMENT=development')
if ($env:DEMO_SEED_PASSWORD) { $seedEnv += @('-e', 'DEMO_SEED_PASSWORD') }
Docker run --rm --network $Net -v "${AppVol}:/data" -e STORAGE_ROOT=/data/storage @seedEnv $ApiImage python -m scripts.seed_demo

Step 'Creating platform staff account'
Docker run --rm --network $Net -e DATABASE_URL -e ENVIRONMENT=development -e PLATFORM_STAFF_EMAIL -e PLATFORM_STAFF_PASSWORD `
  $ApiImage python -m scripts.create_platform_staff

# --- Premium tier + backfill (through the staff API) -------------------------------
$row = (& docker exec saas-dev-db psql -U $DbUser -d $DbName -tAc `
  "select t.id || ' ' || b.id from tenants t join bots b on b.tenant_id = t.id where t.slug = 'demo-dental-clinic'")
$ids = "$row".Trim().Split(' ')
if ($ids.Count -ne 2) { throw 'Demo tenant/bot not found after seeding.' }
$TenantId, $BotId = $ids
$rag = "$ApiUrl/api/v1/tenants/$TenantId/bots/$BotId/rag"

Step 'Logging in as platform staff'
$loginBody = @{ email = $StaffEmail; password = $env:PLATFORM_STAFF_PASSWORD } | ConvertTo-Json
Invoke-RestMethod "$ApiUrl/api/v1/auth/login" -Method Post -Body $loginBody -ContentType 'application/json' `
  -SessionVariable session | Out-Null
$csrf = ($session.Cookies.GetCookies($ApiUrl) | Where-Object Name -eq 'chatbot_csrf').Value
if (-not $csrf) { throw 'Login succeeded but no CSRF cookie was issued.' }
$headers = @{ 'X-CSRF-Token' = $csrf }

Step 'Setting demo bot to premium tier'
Invoke-RestMethod $rag -Method Patch -Headers $headers -WebSession $session -ContentType 'application/json' `
  -Body (@{ tier = 'premium' } | ConvertTo-Json) | Out-Null

Step 'Triggering embedding backfill'
Invoke-RestMethod "$rag/backfill" -Method Post -Headers $headers -WebSession $session -ContentType 'application/json' `
  -Body '{}' | Out-Null

Step "Waiting for backfill (up to $BackfillTimeoutMinutes min)"
$deadline = (Get-Date).AddMinutes($BackfillTimeoutMinutes)
while ($true) {
  $status = Invoke-RestMethod $rag -WebSession $session
  $state = if ($status.backfill) { $status.backfill.status } else { 'none' }
  Write-Host "    backfill=$state done=$($status.backfill.done)/$($status.backfill.total) model=$($status.active_embedding_model)"
  if ($state -eq 'succeeded' -and $status.active_embedding_model -eq $ExpectedModel) { break }
  if ($state -in 'failed', 'cancelled') {
    throw "Backfill ended as '$state'. Check: docker logs saas-dev-worker"
  }
  if ((Get-Date) -gt $deadline) { throw 'Timed out waiting for the backfill to succeed.' }
  Start-Sleep -Seconds 5
}

Write-Host ''
Write-Host "Ready.  Web:   http://127.0.0.1:$WebPort" -ForegroundColor Green
Write-Host "        Staff: $StaffEmail  (the password you provided)"
Write-Host '        Demo client logins are printed by the seed step above. Stop with .\scripts\dev_down.ps1'
