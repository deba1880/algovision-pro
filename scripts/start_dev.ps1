# Quick start for development (without Docker for app code)
# Requires: Docker for DB/Redis/Kafka, Python venv, pnpm

Write-Host "Starting AlgoVision Pro (dev mode)..." -ForegroundColor Cyan

# Start infrastructure
Write-Host "Starting DB, Redis, Kafka..." -ForegroundColor Yellow
docker compose up -d db redis zookeeper kafka
Start-Sleep -Seconds 5

# Start backend in new window
Write-Host "Starting backend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD\backend'; .\venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

Start-Sleep -Seconds 3

# Start frontend in new window
Write-Host "Starting frontend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD\frontend'; pnpm dev"

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "AlgoVision Pro is starting up!" -ForegroundColor Green
Write-Host "  Frontend:  http://localhost:5173" -ForegroundColor Cyan
Write-Host "  Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "  API Docs:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
