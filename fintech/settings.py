"""
Django settings for the Finalto Risk Management Dashboard.

This is a single-environment settings file designed for local development and
reviewer reproduction.  There is no database — all state is in-memory.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Security (local dev only — not for production deployment)
# ---------------------------------------------------------------------------

SECRET_KEY = "django-insecure-finalto-risk-dashboard-local-dev-key-change-in-prod"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    # Simulation engine — starts background threads in AppConfig.ready()
    "simulation.apps.SimulationConfig",
    # Dashboard UI and JSON API
    "dashboard.apps.DashboardConfig",
    # Minimal Django core (no admin, auth, sessions, or ORM needed)
    "django.contrib.staticfiles",
]

# ---------------------------------------------------------------------------
# Middleware (minimal — no sessions, auth, or CSRF for the local API)
# ---------------------------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

# Disable CSRF for the local JSON API (no forms or state-changing POSTs)
CSRF_COOKIE_SECURE = False

# ---------------------------------------------------------------------------
# URL routing
# ---------------------------------------------------------------------------

ROOT_URLCONF = "fintech.urls"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,   # looks for templates/<app>/... inside each app
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# WSGI
# ---------------------------------------------------------------------------

WSGI_APPLICATION = "fintech.wsgi.application"

# ---------------------------------------------------------------------------
# Database — intentionally disabled (all state is in-memory)
# ---------------------------------------------------------------------------

DATABASES = {}

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "/static/"

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# ---------------------------------------------------------------------------
# Logging — show simulation events without noise from Django internals
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s [%(name)s] %(levelname)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "simulation": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "dashboard":  {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}
