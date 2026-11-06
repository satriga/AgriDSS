<?php
/**
 * AgriDSS Hostinger Web Server Fallback Handler
 * =============================================
 * LiteSpeed / Apache will execute passenger_wsgi.py when CloudLinux Passenger is active.
 * If Passenger is warming up or during initial configuration, this prevents 403 Forbidden errors.
 */
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgriDSS &bull; Starting Application Engine</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #071326; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 16px; box-sizing: border-box; }
        .card { background: #0e2242; border: 1px solid #19365e; border-radius: 12px; padding: 32px 28px; max-width: 480px; width: 100%; text-align: center; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); }
        .logo-icon { width: 48px; height: 48px; margin: 0 auto 16px; background: linear-gradient(135deg, #f59e0b, #d97706); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 24px; }
        h1 { font-size: 20px; font-weight: 700; color: #ffffff; margin: 0 0 8px; }
        p { font-size: 13px; color: #94a3b8; line-height: 1.5; margin: 0 0 20px; }
        .loader { width: 32px; height: 32px; border: 3px solid rgba(245, 158, 11, 0.2); border-top-color: #f59e0b; border-radius: 50%; animation: spin 0.9s linear infinite; margin: 0 auto 16px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .hint { font-size: 11px; color: #64748b; background: rgba(15, 23, 42, 0.6); padding: 10px; border-radius: 6px; border: 1px solid #1e293b; text-align: left; }
    </style>
    <script>
        // Check if Flask/WSGI is ready and reload
        setTimeout(function() {
            window.location.reload();
        }, 2500);
    </script>
</head>
<body>
    <div class="card">
        <div class="logo-icon">🌾</div>
        <h1>AgriDSS Engine Starting</h1>
        <div class="loader"></div>
        <p>Connecting to CloudLinux Passenger WSGI. The dashboard will load automatically once the Python engine initializes...</p>
        <div class="hint">
            <strong>Hostinger Setup Tip:</strong> If this page remains, ensure you have clicked <em>Create Application</em> under <strong>Advanced &rarr; Setup Python App</strong> in hPanel with startup file <code>passenger_wsgi.py</code>.
        </div>
    </div>
</body>
</html>
