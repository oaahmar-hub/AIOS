---
description: Deploy AIOS backend and frontend to Railway
---

# Deploy AIOS to Railway

Steps to deploy the latest AIOS backend and React frontend.

## 1. Pre-deployment checks
- Ensure all tests pass:
  ```bash
  cd /Users/hassanka/Downloads/AIOS/automation/unit_intelligence/runtime
  python3 test_unit_intelligence.py
  python3 test_unit_intelligence_api.py
  ```
- Ensure the backend can be imported:
  ```bash
  cd /Users/hassanka/Downloads/AIOS/automation/central_orchestrator/runtime
  python3 -c "import aios_live_api_server; print('ok')"
  ```

## 2. Build the frontend
- Requires Node.js. If not installed locally, use the binary at `~/.local/node/bin` or install via Homebrew.
  ```bash
  export PATH="/Users/hassanka/.local/node/bin:$PATH"
  cd /Users/hassanka/Dev/AIOS-Front
  npm install
  npm run build
  ```

## 3. Copy built frontend into the backend
- Copy the `dist/` output to `AIOS/app/` so the backend serves it at `/app/`:
  ```bash
  rm -rf /Users/hassanka/Downloads/AIOS/app
  cp -R /Users/hassanka/Dev/AIOS-Front/dist /Users/hassanka/Downloads/AIOS/app
  ```

## 4. Deploy to Railway
- Use the Railway CLI or GitHub integration.
- If Railway CLI is installed:
  ```bash
  cd /Users/hassanka/Downloads/AIOS
  railway up
  ```
- Verify the deployment health check:
  ```bash
  curl -s https://aios-runtime-production.up.railway.app/api/health
  ```

## 5. Post-deployment verification
- Open the frontend at `https://aios-runtime-production.up.railway.app/app/`
- Verify `/api/health` returns `status: ready`
- Verify `/api/deployment/status` shows the expected blockers
- Verify `/api/unit/stats` returns staging stats

## 6. Rollback
- If issues occur, redeploy the previous stable deployment via Railway dashboard.
