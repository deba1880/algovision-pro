# AlgoVision Pro — Windows Setup Script
# Run from project root: .\scripts\setup.ps1

param(
    [switch]$SkipDocker,
    [switch]$DevMode
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AlgoVision Pro — Setup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── Prerequisites check ──────────────────────────────────────────────────────

function Check-Command($cmd) {
    return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

$missing = @()
if (-not (Check-Command "docker"))    { $missing += "Docker Desktop" }
if (-not (Check-Command "python"))    { $missing += "Python 3.12+" }
if (-not (Check-Command "node"))      { $missing += "Node.js 20+" }
if (-not (Check-Command "pnpm"))      { $missing += "pnpm (npm install -g pnpm)" }

if ($missing.Count -gt 0) {
    Write-Host "Missing prerequisites:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "Install them and run this script again." -ForegroundColor Red
    exit 1
}

Write-Host "Prerequisites: OK" -ForegroundColor Green

# ── Copy .env if not exists ───────────────────────────────────────────────────

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host "Created .env from .env.example" -ForegroundColor Yellow
    Write-Host "IMPORTANT: Edit .env and fill in your Angel One SmartAPI credentials!" -ForegroundColor Red
    Write-Host "  ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press Enter after editing .env to continue..." -ForegroundColor Cyan
    Read-Host
}

# ── Start Docker infrastructure ───────────────────────────────────────────────

if (-not $SkipDocker) {
    Write-Host "Starting Docker services (DB, Redis, Kafka)..." -ForegroundColor Cyan
    docker compose up -d db redis zookeeper kafka
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Docker failed. Is Docker Desktop running?" -ForegroundColor Red
        exit 1
    }
    Write-Host "Waiting for PostgreSQL to be ready..."
    Start-Sleep -Seconds 15
    Write-Host "Infrastructure: OK" -ForegroundColor Green
}

# ── Backend setup ─────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "Setting up Python backend..." -ForegroundColor Cyan
Set-Location backend

if (-not (Test-Path "venv")) {
    python -m venv venv
}
& .\venv\Scripts\Activate.ps1
pip install -r requirements.txt --quiet

# Note: TA-Lib requires the C library. On Windows, use the pre-built wheel:
Write-Host ""
Write-Host "NOTE: TA-Lib C library installation on Windows:" -ForegroundColor Yellow
Write-Host "  Option 1 (easiest): pip install TA_Lib-0.4.28-cp312-cp312-win_amd64.whl" -ForegroundColor White
Write-Host "  Download from: https://github.com/cgohlke/talib-build/releases" -ForegroundColor White
Write-Host "  Option 2: Use Docker (TA-Lib is auto-installed in Dockerfile)" -ForegroundColor White
Write-Host ""

Set-Location ..

# ── Frontend setup ────────────────────────────────────────────────────────────

Write-Host "Setting up frontend..." -ForegroundColor Cyan
Set-Location frontend
pnpm install --frozen-lockfile 2>$null
if ($LASTEXITCODE -ne 0) { pnpm install }
Set-Location ..

Write-Host "Frontend: OK" -ForegroundColor Green

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Edit .env — add your Angel One SmartAPI credentials"  -ForegroundColor Yellow
Write-Host "     Get credentials from: https://smartapi.angelbroking.com/"
Write-Host ""
Write-Host "  2. Start the backend:" -ForegroundColor Yellow
Write-Host "     cd backend && venv\Scripts\activate && uvicorn app.main:app --reload"
Write-Host ""
Write-Host "  3. Start the frontend (new terminal):" -ForegroundColor Yellow
Write-Host "     cd frontend && pnpm dev"
Write-Host ""
Write-Host "  4. Open http://localhost:5173 in your browser" -ForegroundColor Cyan
Write-Host ""
Write-Host "  OR — start everything with Docker:" -ForegroundColor Yellow
Write-Host "     docker compose up"
Write-Host ""
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
