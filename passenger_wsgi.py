"""
Hostinger Passenger WSGI Entry Point (CloudLinux / hPanel Python Selector)
========================================================================
This file is required by Hostinger Shared and Cloud Web Hosting when using
the "Setup Python App" feature in hPanel.
"""

import sys
import os

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Auto-activate Virtual Environment if present
for venv_path in [
    os.path.join(PROJECT_DIR, "venv"),
    os.path.join(PROJECT_DIR, ".venv"),
    os.path.expanduser(f"~/virtualenv/{os.path.basename(PROJECT_DIR)}/3.11"),
    os.path.expanduser(f"~/virtualenv/{os.path.basename(PROJECT_DIR)}/3.10"),
    os.path.expanduser(f"~/virtualenv/public_html/3.11"),
    os.path.expanduser(f"~/virtualenv/public_html/3.10"),
]:
    py_bin = os.path.join(venv_path, "bin", "python")
    site_packages = os.path.join(venv_path, "lib", f"python3.{sys.version_info.minor}", "site-packages")
    if os.path.exists(site_packages) and site_packages not in sys.path:
        sys.path.insert(0, site_packages)
    if os.path.exists(py_bin) and sys.executable != py_bin:
        try:
            # Re-exec under the virtual environment if needed
            activate_this = os.path.join(venv_path, "bin", "activate_this.py")
            if os.path.exists(activate_this):
                with open(activate_this) as f:
                    exec(f.read(), dict(__file__=activate_this))
        except Exception:
            pass

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_DIR, ".env"))
except Exception:
    pass

# Expose Flask application instance as 'application' (Passenger WSGI standard)
try:
    from app import app as application
except Exception as e:
    # Diagnostic fallback for debugging deployment issues in browser
    import traceback
    err_tb = traceback.format_exc()
    def application(environ, start_response):
        status = '500 Internal Server Error'
        output = f"<h1>AgriDSS Startup Error</h1><p>Failed to import app: {e}</p><pre>{err_tb}</pre>".encode('utf-8')
        response_headers = [('Content-type', 'text/html; charset=utf-8'), ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]
