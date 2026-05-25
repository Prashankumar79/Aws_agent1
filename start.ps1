# ================================================================================
#  start.ps1  —  Launch InfraSketch on localhost (Windows)
# ================================================================================
# PURPOSE:
#   Starts both the FastAPI backend and the Vite React frontend in separate
#   terminal windows so you can see logs from each.
#
# PORTS:
#   Backend  -> http://localhost:8000
#   Frontend -> http://localhost:3000
#   DrawIO   -> http://localhost:8081  (for Architecture Studio editor)
#   Qdrant   -> http://localhost:6333  (RAG vector store)
#
# USAGE:
#   1. Open PowerShell in the project root folder
#   2. Run:  .\start.ps1            (development, hot-reload ON)
#       Or:  .\start.ps1 -Production (no reload, binds 127.0.0.1 only)
#   3. Open browser to http://localhost:3000
# ================================================================================

[CmdletBinding()]
param(
    [switch]$Production
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host "========================================" -ForegroundColor Cyan
Write-Host '  InfraSketch - localhost launcher' -ForegroundColor Cyan
if ($Production) {
    Write-Host '  (production mode: no reload, 127.0.0.1 binding)' -ForegroundColor Yellow
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── Check Python ──────────────────────────────────────────────────────────────
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "ERROR: python not found in PATH." -ForegroundColor Red
    Write-Host "Install Python 3.11+ and try again." -ForegroundColor Red
    exit 1
}
Write-Host "Python found: $($pythonCmd.Source)" -ForegroundColor Green

# ── Check Node.js ─────────────────────────────────────────────────────────────
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Host "ERROR: node not found in PATH." -ForegroundColor Red
    Write-Host "Install Node.js 18+ and try again." -ForegroundColor Red
    exit 1
}
Write-Host "Node.js found: $($nodeCmd.Source)" -ForegroundColor Green

# ── Verify backend/.env exists ───────────────────────────────────────────────
$backendDir = Join-Path $projectRoot "backend"
$envFile = Join-Path $backendDir ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "" -ForegroundColor Yellow
    Write-Host "ERROR: backend/.env not found." -ForegroundColor Red
    Write-Host "       Copy backend/.env.example -> backend/.env and fill in your secrets." -ForegroundColor Yellow
    Write-Host "       Required: GEMINI_API_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY" -ForegroundColor Yellow
    exit 1
}
Write-Host "backend/.env found" -ForegroundColor Green

# ── Check backend dependencies ────────────────────────────────────────────────
Write-Host ""
Write-Host "Checking backend dependencies..." -ForegroundColor Yellow
& python -c "import fastapi, uvicorn, boto3, langgraph" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing backend dependencies (this may take several minutes)..." -ForegroundColor Yellow
    $reqFile = Join-Path $backendDir "requirements.txt"
    & python -m pip install -r $reqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install backend dependencies." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Backend dependencies OK" -ForegroundColor Green
}

# ── Check frontend dependencies ─────────────────────────────────────────────
$frontendDir = Join-Path $projectRoot "frontend"
Write-Host "Checking frontend dependencies..." -ForegroundColor Yellow
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "Installing frontend dependencies (npm install)..." -ForegroundColor Yellow
    Push-Location $frontendDir
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Failed to install frontend dependencies." -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "Frontend dependencies OK" -ForegroundColor Green
}

# ── Check & start Docker DrawIO + Qdrant ────────────────────────────────────
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Write-Host "WARNING: Docker not found in PATH." -ForegroundColor Yellow
    Write-Host "         Architecture Studio (draw.io editor) and RAG will not work." -ForegroundColor Yellow
} else {
    $composeFile = Join-Path $projectRoot "docker-compose.yml"

    function Start-Service {
        param(
            [string]$Container,
            [string]$DisplayName,
            [string]$Url,
            [string]$ServiceName
        )
        Write-Host "Checking $DisplayName container..." -ForegroundColor Yellow
        $running = & docker ps --filter "name=$Container" --format "{{.Names}}" 2>$null
        if ($running -eq $Container) {
            Write-Host "$DisplayName already running on $Url" -ForegroundColor Green
            return
        }
        Write-Host "Starting $DisplayName on $Url ..." -ForegroundColor Cyan
        if (Test-Path $composeFile) {
            & docker compose -f $composeFile up -d $ServiceName 2>$null
            if ($LASTEXITCODE -ne 0) {
                & docker-compose -f $composeFile up -d $ServiceName 2>$null
            }
        }
        # Poll for readiness instead of arbitrary sleep
        $deadline = (Get-Date).AddSeconds(30)
        do {
            Start-Sleep -Seconds 1
            $running = & docker ps --filter "name=$Container" --format "{{.Names}}" 2>$null
            if ($running -eq $Container) { break }
        } while ((Get-Date) -lt $deadline)
        if ($running -eq $Container) {
            Write-Host "$DisplayName started" -ForegroundColor Green
        } else {
            Write-Host "WARNING: Could not start $DisplayName container." -ForegroundColor Yellow
        }
    }

    Start-Service -Container "infrasketch-drawio" -DisplayName "DrawIO"  -Url "http://localhost:8081" -ServiceName "drawio"
    Start-Service -Container "qdrant-rag"          -DisplayName "Qdrant" -Url "http://localhost:6333" -ServiceName "qdrant"
}

# ── Pick uvicorn flags based on mode ─────────────────────────────────────────
if ($Production) {
    # Bind to localhost only and disable hot-reload.
    $uvicornArgs = "--host 127.0.0.1 --port 8000 --workers 2"
} else {
    # Dev mode: hot-reload on, still localhost-only by default.
    $uvicornArgs = "--host 127.0.0.1 --port 8000 --reload"
}

# ── Launch backend ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Starting BACKEND on http://localhost:8000 ..." -ForegroundColor Cyan
$escBackendDir = $backendDir -replace "'", "''"
$cmdBackend = "Write-Host '[BACKEND] Starting FastAPI...' -ForegroundColor Cyan; Set-Location -LiteralPath '$escBackendDir'; & python -m uvicorn app.main:app $uvicornArgs"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmdBackend

# ── Launch frontend ─────────────────────────────────────────────────────────
Write-Host "Starting FRONTEND on http://localhost:3000 ..." -ForegroundColor Cyan
$escFrontendDir = $frontendDir -replace "'", "''"
$cmdFrontend = "Write-Host '[FRONTEND] Starting Vite...' -ForegroundColor Green; Set-Location -LiteralPath '$escFrontendDir'; & npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmdFrontend

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  All services are starting!" -ForegroundColor Cyan
Write-Host "  Backend : http://localhost:8000" -ForegroundColor Cyan
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor Cyan
Write-Host "  DrawIO  : http://localhost:8081" -ForegroundColor Cyan
Write-Host "  Qdrant  : http://localhost:6333" -ForegroundColor Cyan
Write-Host "  API Docs: http://localhost:8000/docs (only when DEBUG=true)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Open your browser to:  http://localhost:3000" -ForegroundColor Green
