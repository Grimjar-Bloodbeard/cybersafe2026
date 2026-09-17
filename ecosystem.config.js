// PM2 process definition for the CyberSafe 2026 web app - runs it durably
// (survives this session ending, restarts on crash) exactly like the other
// apps on this box (see D:\Gotify\ecosystem.config.js for the same pattern).
// Kept as its own file, not added to C:\summitserver\ecosystem.config.js,
// which belongs to Summit Gaming/cloudflared - an unrelated app.
//
// See docs/architecture/DEPLOYMENT.md for the full deployment runbook and
// why each setting below is what it is.
module.exports = {
  apps: [
    {
      name: 'cybersafe2026',
      // Full path because this exe lives in the user Scripts folder, which
      // isn't on PM2's own PATH - same reason Gotify's config uses a direct
      // path to its own exe instead of relying on PATH resolution.
      script: 'C:\\Users\\cody\\AppData\\Roaming\\Python\\Python313\\Scripts\\uvicorn.exe',
      // --workers 1 is load-bearing, not a default left in place: the rate
      // limiter in backend/app/rate_limit.py is in-process state that does
      // NOT share across worker processes. Raising this without rethinking
      // that design silently makes rate limiting N times weaker.
      args: 'backend.app.main:app --host 127.0.0.1 --port 8098 --workers 1',
      interpreter: 'none',
      // Must be the repo root - backend/app/main.py imports scrapers.* and
      // scripts.* as top-level packages, exactly like the dev command
      // (`python -m uvicorn backend.app.main:app`) already requires.
      cwd: 'D:\\cybersafe2026',
      instances: 1,
      exec_mode: 'fork',
      watch: false,
      autorestart: true,
      max_restarts: 20,
      min_uptime: '10s',
      restart_delay: 3000,
      env: {
        PYTHONUNBUFFERED: '1'
      },
      error_file: './logs/cybersafe-error.log',
      out_file: './logs/cybersafe-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      time: true
    }
  ]
};
