"""
Standard WSGI Entry Point for Gunicorn / Production WSGI
=========================================================
Run with:
    gunicorn --workers 4 --bind 0.0.0.0:5000 wsgi:app
"""

import os
from dotenv import load_dotenv

load_dotenv()

from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
