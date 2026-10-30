# Gunicorn configuration file for production
# Gunicorn automatically loads this file when started in the project directory

import os

# Port and binding
port = os.getenv("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Worker processes
workers = int(os.getenv("WEB_CONCURRENCY", "1"))
worker_class = "sync"

# Critical: Increase request timeout from default 30s to 120s
# This ensures PDF extraction, OCR, and Google Gemini AI calls complete successfully
timeout = 120
keepalive = 5

# Logging to stdout
accesslog = "-"
errorlog = "-"
loglevel = "info"
