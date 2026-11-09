# DarkWolf

DarkWolf is a local threat intelligence application for monitoring ransomware and data leak site listings. It collects public listing metadata, stores scrape evidence and observations in MongoDB, detects changes between collection runs, and presents victims, sources, recent changes, and geographic summaries in a React dashboard.

## Project layout

- `darkwolf-backend/` — FastAPI API, MongoDB integration, source-specific collectors, change detection, and collection CLI.
- `darkwolf-frontend/` — React, TypeScript, and Vite dashboard.
- `run_full_scrape.ps1` — Windows runner for the four collection stages. It checks MongoDB and Tor SOCKS connectivity first.
- `recon/` — source inventory, inspection tools, and saved investigation results.
- `Captchy/`, `Insomnia/`, and `Storm/` — separate experimental captcha/browser tooling and dependencies.
- `requirements.txt` — pinned Python dependencies for the backend and root-level Python utilities.

## Requirements

- Windows 10 or later (the full scrape runner uses PowerShell).
- Python 3.11 or later.
- Node.js 20 or later and npm.
- MongoDB running locally on `127.0.0.1:27017` (or configure another URI).
- A Tor SOCKS listener, normally `127.0.0.1:9050` or Tor Browser's `127.0.0.1:9150`, for live collection.

## Configuration

Create `darkwolf-backend/.env` from `darkwolf-backend/.env.example` and set the INC source URLs required by the backend. The file is ignored by Git. MongoDB and Tor defaults are local; override them with `MONGO_URI`, `MONGO_DB`, `TOR_HOST`, and `TOR_SOCKS_PORT` as needed.

## Install and run

### Backend

From the project root in PowerShell:

```powershell
py -3 -m venv darkwolf-backend\.venv
darkwolf-backend\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item darkwolf-backend\.env.example darkwolf-backend\.env
Set-Location darkwolf-backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health endpoints:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/health/database`
- `http://127.0.0.1:8000/docs` — interactive API documentation

### Frontend

In a second PowerShell window:

```powershell
Set-Location darkwolf-frontend
npm ci
npm run dev
```

The Vite development server is normally available at `http://127.0.0.1:5173`. The current frontend calls the API at `http://127.0.0.1:8000`.

## Full collection cycle

Start MongoDB and Tor first, then run from the project root:

```powershell
.\run_full_scrape.ps1
```

The script runs INC, HTML, API, and JavaScript source collectors in sequence and writes stage logs under `darkwolf-backend/logs/`. Use `-StartAt` to resume from a stage, or `-PerPage` to set INC pagination size. For example:

```powershell
.\run_full_scrape.ps1 -StartAt api-leak-sites
.\run_full_scrape.ps1 -PerPage 25
```

## Python dependencies

Install the pinned root environment with `pip install -r requirements.txt`. The experimental `Captchy` tooling has its own `Captchy/requirements.txt`; install it separately only when using that tooling. The frontend dependency versions are managed by `darkwolf-frontend/package-lock.json` and installed with `npm ci`.

## Git and local data

Commit source code, configuration templates, inventory files, and maintained investigation material. Local `.env` files, virtual environments, `node_modules`, build output, logs, and the `debug/` scratch directory are excluded. Never commit credentials or session cookies.
