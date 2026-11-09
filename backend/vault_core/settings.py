"""Vault settings. Everything deploy-specific comes from the environment.

Required in production (DEBUG unset/0): SECRET_KEY, DATABASE_URL (or DB_* vars),
ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS. Startup fails loudly if any of the first three is missing.
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
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS") or (["http://localhost:5173"] if DEBUG else [])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "corsheaders",
    "rest_framework",
    "backtester",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    # ponytail: LocMemCache makes these per-process, per-IP limits. Shared cache if replicas > 1.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "read": env("THROTTLE_READ", "300/min"),
        "write": env("THROTTLE_WRITE", "30/min"),
        "jobs": env("THROTTLE_JOBS", "10/min"),
    },
}

# --- Vault limits (admission control). Defaults sized for one small worker.
VAULT = {
    "ALLOW_CUSTOM_CODE": env("ALLOW_CUSTOM_CODE", "0") == "1",
    "MAX_ACTIVE_RUNS": env_int("MAX_ACTIVE_RUNS", 50),  # global queued+running cap
    "MAX_GRID": env_int("MAX_GRID", 25),
    "MAX_RANGE_DAYS": env_int("MAX_RANGE_DAYS", 3660),
    "MAX_CODE_CHARS": env_int("MAX_CODE_CHARS", 10_000),
    "RUN_TIMEOUT_S": env_int("RUN_TIMEOUT_S", 60),
    "RUN_CPU_S": env_int("RUN_CPU_S", 30),
    "RUN_MEMORY_MB": env_int("RUN_MEMORY_MB", 256),
    "STALE_AFTER_S": env_int("STALE_AFTER_S", 120),
    "MAX_ATTEMPTS": env_int("MAX_ATTEMPTS", 3),
    "OOS_FRACTION": float(env("OOS_FRACTION", "0.3")),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"kv": {"format": "ts=%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"}},
    "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "kv"}},
    "root": {"handlers": ["stdout"], "level": env("LOG_LEVEL", "INFO")},
}
