"""Vault settings. Everything deploy-specific comes from the environment.

Required in production (DEBUG unset/0): SECRET_KEY, DATABASE_URL (or DB_* vars), ALLOWED_HOSTS.
Startup fails loudly if any is missing. Also set in production: CSRF_TRUSTED_ORIGINS (the frontend's origin,
because the browser reaches the API through the frontend's /api proxy), FRONTEND_URL and the EMAIL_* vars.
"""
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
env = os.environ.get


def env_list(name):
    return [x.strip() for x in env(name, "").split(",") if x.strip()]


def env_int(name, default):
    return int(env(name, default))


DEBUG = env("DEBUG", "0") == "1"
SECRET_KEY = env("SECRET_KEY") or ("dev-only-insecure-key" if DEBUG else None)
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY environment variable is required when DEBUG is off")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS") or (["localhost", "127.0.0.1"] if DEBUG else [])
if env("RENDER_EXTERNAL_HOSTNAME"):  # injected by Render
    ALLOWED_HOSTS.append(env("RENDER_EXTERNAL_HOSTNAME"))
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS environment variable is required when DEBUG is off")
# The browser reaches the API on the frontend's own origin (Vercel rewrite / Vite proxy / nginx), so there
# is no CORS. Django checks the Origin header of unsafe requests against the Host it sees; behind a proxy that
# rewrites Host, list the frontend origin here (e.g. https://vault.example.app).
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    "accounts",
    "backtester",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# --- accounts and sessions
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
SESSION_COOKIE_AGE = 14 * 24 * 3600
SESSION_COOKIE_HTTPONLY = True          # JavaScript (and so XSS) can never read the session id
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False            # the SPA reads it and echoes it in X-CSRFToken (double-submit)
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG
PASSWORD_RESET_TIMEOUT = 24 * 3600      # also bounds email-verification links
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173").rstrip("/")

# --- email: console in development; SMTP (e.g. Resend) when EMAIL_HOST is set
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_BACKEND = ("django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST
                 else "django.core.mail.backends.console.EmailBackend")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env("EMAIL_USE_TLS", "1") == "1"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Vault <no-reply@localhost>")

ROOT_URLCONF = "vault_core.urls"
WSGI_APPLICATION = "vault_core.wsgi.application"


def _database():
    url = env("DATABASE_URL")
    if url and url.startswith("sqlite"):
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": url.split("///", 1)[1] or ":memory:"}
    if url:
        u = urlparse(url)
        db = {"NAME": u.path.lstrip("/"), "USER": unquote(u.username or ""),
              "PASSWORD": unquote(u.password or ""), "HOST": u.hostname, "PORT": u.port or 5432}
    else:
        if not DEBUG and not env("DB_PASSWORD"):
            raise ImproperlyConfigured("DATABASE_URL (or DB_PASSWORD) is required when DEBUG is off")
        db = {"NAME": env("DB_NAME", "vault"), "USER": env("DB_USER", "postgres"),
              "PASSWORD": env("DB_PASSWORD", ""), "HOST": env("DB_HOST", "localhost"),
              "PORT": env("DB_PORT", "5432")}
    return {"ENGINE": "django.db.backends.postgresql", "CONN_MAX_AGE": 60, "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {"sslmode": env("DB_SSLMODE", "prefer"), "connect_timeout": 5}, **db}


DATABASES = {"default": _database()}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# --- request hardening
DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if env("SECURE_PROXY_SSL_HEADER") == "1":  # set only behind a TLS-terminating proxy (Render does this)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)  # enable once HTTPS is verified

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # Session cookie auth. DRF enforces CSRF for authenticated unsafe requests; the auth views enforce it for
    # anonymous ones too (login CSRF).
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    # ponytail: LocMemCache makes these per-process limits. Shared cache if replicas > 1. Signed-in users are
    # counted per user; anonymous requests (auth endpoints) per IP.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    # Clients are identified by IP. Without NUM_PROXIES, DRF uses the whole X-Forwarded-For header, which a
    # client can set to anything to dodge throttling. 0 = use REMOTE_ADDR (no proxy); N = trust the address
    # appended by the Nth proxy from the end. Render has one proxy in front of the service.
    "NUM_PROXIES": env_int("NUM_PROXIES", 1 if env("RENDER_EXTERNAL_HOSTNAME") else 0),
    "DEFAULT_THROTTLE_RATES": {
        "read": env("THROTTLE_READ", "300/min"),
        "write": env("THROTTLE_WRITE", "30/min"),
        "jobs": env("THROTTLE_JOBS", "10/min"),
        "auth": env("THROTTLE_AUTH", "10/min"),     # login, signup, password reset: slows password guessing
        "guest": env("THROTTLE_GUEST", "5/hour"),   # guest creation, per IP
    },
}

# --- Vault limits (admission control). Defaults sized for one small worker.
VAULT = {
    "ALLOW_CUSTOM_CODE": env("ALLOW_CUSTOM_CODE", "0") == "1",
    "MAX_ACTIVE_RUNS": env_int("MAX_ACTIVE_RUNS", 50),  # global queued+running cap
    "MAX_GRID": env_int("MAX_GRID", 25),  # child runs per experiment (optimization combos or comparison cells)
    "MAX_GRID_PARAMS": env_int("MAX_GRID_PARAMS", 4),  # spec parameters one optimization may vary
    "MAX_COMPARE_STRATEGIES": env_int("MAX_COMPARE_STRATEGIES", 10),
    "MAX_COMPARE_SYMBOLS": env_int("MAX_COMPARE_SYMBOLS", 10),
    "BENCHMARKS": {"INR": "^NSEI", "USD": "^GSPC"},  # index buy-and-hold per currency for comparisons
    "MAX_RANGE_DAYS": env_int("MAX_RANGE_DAYS", 3660),
    "MAX_CODE_CHARS": env_int("MAX_CODE_CHARS", 10_000),
    "RUN_TIMEOUT_S": env_int("RUN_TIMEOUT_S", 60),
    "RUN_CPU_S": env_int("RUN_CPU_S", 30),
    "RUN_MEMORY_MB": env_int("RUN_MEMORY_MB", 256),
    "STALE_AFTER_S": env_int("STALE_AFTER_S", 120),
    "MAX_ATTEMPTS": env_int("MAX_ATTEMPTS", 3),
    "OOS_FRACTION": float(env("OOS_FRACTION", "0.3")),
    "GUEST_TTL_DAYS": env_int("GUEST_TTL_DAYS", 7),
    # Per-user quotas by tier; override any value with QUOTA_<TIER>_<LIMIT>, e.g. QUOTA_VERIFIED_RUNS_PER_DAY.
    "QUOTAS": {tier: {k: env_int(f"QUOTA_{tier.upper()}_{k.upper()}", v) for k, v in defaults.items()}
               for tier, defaults in {
                   "guest": {"active_jobs": 2, "runs_per_day": 20, "experiments_per_day": 2, "strategies": 5},
                   "unverified": {"active_jobs": 3, "runs_per_day": 30, "experiments_per_day": 3, "strategies": 20},
                   "verified": {"active_jobs": 10, "runs_per_day": 200, "experiments_per_day": 20, "strategies": 100},
               }.items()},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"kv": {"format": "ts=%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"}},
    "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "kv"}},
    "root": {"handlers": ["stdout"], "level": env("LOG_LEVEL", "INFO")},
}
