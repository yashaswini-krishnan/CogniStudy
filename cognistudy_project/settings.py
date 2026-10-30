"""
Django settings for CogniStudy – AI-Powered Study Companion & Assessment Engine.

Configuration is driven entirely by environment variables (loaded from a .env file
in development). Never hardcode secrets here. See .env.example for required keys.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────
# Base directory and environment loading
# ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env in development. In production, inject variables directly.
load_dotenv(BASE_DIR / '.env')

# ─────────────────────────────────────────────────────────────
# Core secrets — MUST be set in the environment for production
# ─────────────────────────────────────────────────────────────
_secret_key = os.getenv('SECRET_KEY', '')
if not _secret_key:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Generate one and add it to your .env file before running the application."
    )
SECRET_KEY = _secret_key

# ─────────────────────────────────────────────────────────────
# Debug mode — always False in production
# ─────────────────────────────────────────────────────────────
DEBUG = os.getenv('DEBUG', 'False').strip().lower() == 'true'

# ─────────────────────────────────────────────────────────────
# Allowed hosts — comma-separated in env for production
# ─────────────────────────────────────────────────────────────
_allowed_raw = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost')
ALLOWED_HOSTS = [h.strip() for h in _allowed_raw.split(',') if h.strip()]

# ─────────────────────────────────────────────────────────────
# Installed applications
# ─────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

# ─────────────────────────────────────────────────────────────
# Middleware — WhiteNoise must come directly after SecurityMiddleware
# ─────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',          # static files in production
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cognistudy_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'cognistudy_project.wsgi.application'

# ─────────────────────────────────────────────────────────────
# Database — all credentials from environment variables
# ─────────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME', 'cognistudy_db'),
        'USER': os.getenv('DB_USER', 'root'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        'CONN_MAX_AGE': 60,  # reuse DB connections for up to 60 seconds
    }
}

# ─────────────────────────────────────────────────────────────
# Password validation
# ─────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─────────────────────────────────────────────────────────────
# Internationalisation
# ─────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────────────────────────
# Static files — WhiteNoise serves compressed, cached files
# ─────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ─────────────────────────────────────────────────────────────
# Media files (uploaded PDFs)
# ─────────────────────────────────────────────────────────────
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─────────────────────────────────────────────────────────────
# File upload limits — 20 MB max per request
# ─────────────────────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024   # 20 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024   # 20 MB

# ─────────────────────────────────────────────────────────────
# Default primary key
# ─────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─────────────────────────────────────────────────────────────
# Authentication redirects
# ─────────────────────────────────────────────────────────────
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# ─────────────────────────────────────────────────────────────
# Session and cookie security (baseline — always on)
# ─────────────────────────────────────────────────────────────
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False     # must be readable by JS for AJAX; keep False
SESSION_COOKIE_AGE = 1209600    # 2 weeks in seconds
X_FRAME_OPTIONS = 'DENY'

# ─────────────────────────────────────────────────────────────
# Production-only security settings (applied when DEBUG=False)
# These settings require HTTPS and should NOT be enabled in
# local development without a valid SSL certificate.
# ─────────────────────────────────────────────────────────────
if not DEBUG:
    # Force all HTTP → HTTPS redirects
    SECURE_SSL_REDIRECT = True

    # HSTS: tell browsers to use HTTPS for 1 year
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Cookies must travel over HTTPS only
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # Prevent MIME-type sniffing
    SECURE_CONTENT_TYPE_NOSNIFF = True

    # Enable browser XSS filter (legacy browsers)
    SECURE_BROWSER_XSS_FILTER = True

    # Proxy header for platforms that terminate SSL upstream (e.g. Railway, Render)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ─────────────────────────────────────────────────────────────
# Logging — structured, levelled, file + console output
# ─────────────────────────────────────────────────────────────
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {module}:{lineno} — {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },

    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_app': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'cognistudy_app.log',
            'maxBytes': 5 * 1024 * 1024,   # 5 MB per file
            'backupCount': 3,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'file_errors': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'cognistudy_errors.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 3,
            'formatter': 'verbose',
            'level': 'ERROR',
            'encoding': 'utf-8',
        },
    },

    'loggers': {
        # Application logger (core app)
        'core': {
            'handlers': ['console', 'file_app', 'file_errors'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # Django framework logger
        'django': {
            'handlers': ['console', 'file_errors'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Database query logger (only in DEBUG, very noisy)
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'WARNING',
            'propagate': False,
        },
    },

    # Root logger catches anything not handled above
    'root': {
        'handlers': ['console', 'file_errors'],
        'level': 'WARNING',
    },
}
