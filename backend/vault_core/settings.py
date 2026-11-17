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
    "django.contrib.staticfiles",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "accounts",
    "backtester",
    "assist",
]

MIDDLEWARE = [
    "vault_core.observability.RequestContextMiddleware",  # outermost: request ID, timing, access log, metrics
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
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
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
    "WORKER_GRACE_S": env_int("WORKER_GRACE_S", 20),  # after SIGTERM: finish the current run within this, else requeue
    "MAX_ATTEMPTS": env_int("MAX_ATTEMPTS", 3),
    "OOS_FRACTION": float(env("OOS_FRACTION", "0.3")),
    "GUEST_TTL_DAYS": env_int("GUEST_TTL_DAYS", 7),
    # Per-user quotas by tier; override any value with QUOTA_<TIER>_<LIMIT>, e.g. QUOTA_VERIFIED_RUNS_PER_DAY.
    "QUOTAS": {tier: {k: env_int(f"QUOTA_{tier.upper()}_{k.upper()}", v) for k, v in defaults.items()}
               for tier, defaults in {
                   "guest": {"active_jobs": 2, "runs_per_day": 20, "experiments_per_day": 2, "strategies": 5,
                             "ai_requests_per_day": 5},
                   "unverified": {"active_jobs": 3, "runs_per_day": 30, "experiments_per_day": 3, "strategies": 20,
                                  "ai_requests_per_day": 10},
                   "verified": {"active_jobs": 10, "runs_per_day": 200, "experiments_per_day": 20, "strategies": 100,
                                "ai_requests_per_day": 50},
               }.items()},
}

# --- AI assistance (Phase 4, D-077 to D-083). Off unless AI_PROVIDER and its key are set; the app works fully without it.
AI = {
    "PROVIDER": env("AI_PROVIDER", ""),  # "groq"
    "GROQ_API_KEY": env("GROQ_API_KEY", ""),
    "MODEL": env("AI_MODEL", "openai/gpt-oss-120b"),
    "REASONING_EFFORT": env("AI_REASONING_EFFORT", ""),  # only for reasoning models: low | medium | high
    "TIMEOUT_S": env_int("AI_TIMEOUT_S", 30),
    "MAX_OUTPUT_TOKENS": env_int("AI_MAX_OUTPUT_TOKENS", 2000),
    "MAX_REPAIRS": env_int("AI_MAX_REPAIRS", 2),
    "MAX_PROMPT_CHARS": env_int("AI_MAX_PROMPT_CHARS", 1000),
    # Whole deployment, per UTC day. Keep it below the provider's free daily token limit (D-081).
    "DAILY_TOKEN_BUDGET": env_int("AI_DAILY_TOKEN_BUDGET", 150_000),
    "MAX_QUEUED": env_int("AI_MAX_QUEUED", 20),  # global queued AI requests before 503
    "CACHE_DAYS": env_int("AI_CACHE_DAYS", 7),
    "RETENTION_DAYS": env_int("AI_RETENTION_DAYS", 30),
    "STALE_AFTER_S": env_int("AI_STALE_AFTER_S", 180),
}

# --- Observability (D-069 to D-073)
# JSON log lines; every line carries request_id / run_id when there is one. LOG_FORMAT=text for local reading.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"context": {"()": "vault_core.observability.ContextFilter"}},
    "formatters": {
        "json": {"()": "vault_core.observability.JSONFormatter"},
        "text": {"format": "ts=%(asctime)s level=%(levelname)s logger=%(name)s request_id=%(request_id)s "
                           "run_id=%(run_id)s %(message)s"},
    },
    "handlers": {"stdout": {"class": "logging.StreamHandler", "filters": ["context"],
                            "formatter": "text" if env("LOG_FORMAT") == "text" else "json"}},
    "root": {"handlers": ["stdout"], "level": env("LOG_LEVEL", "INFO")},
}

METRICS_TOKEN = env("METRICS_TOKEN", "")  # /metrics is 404 unless set
API_DOCS = env("API_DOCS", "1" if DEBUG else "0") == "1"  # /api/schema/ and /api/docs/
SPECTACULAR_SETTINGS = {
    "TITLE": "Vault API",
    "DESCRIPTION": "Strategy backtester: builder strategies, backtests, comparisons and optimizations. Session-cookie "
                   "auth with CSRF; every resource is private to its owner.",
    "VERSION": "3.5",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
    # Several models have a `status` or `kind` with different choices; name each set explicitly.
    "ENUM_NAME_OVERRIDES": {
        "RunStatusEnum": "backtester.models.BacktestRun.STATUS_CHOICES",
        "ExperimentStatusEnum": ["running", "completed", "partially_completed", "failed"],
        "StrategyKindEnum": "backtester.models.Strategy.KIND_CHOICES",
        "ExperimentKindEnum": "backtester.models.Experiment.KIND_CHOICES",
    },
}

# Throttle counters live in a Postgres table shared by every process and instance (D-073), so limits are exact.
# The table is created by migration backtester.0021. Writes are single upserts and expired rows are removed by the
# worker's housekeeping (vault_core/throttle_cache.py, D-075). THROTTLE_CACHE=locmem (per-process counters) and
# THROTTLE_CACHE=django (Django's stock DatabaseCache) exist for the load-test comparisons only.
_THROTTLE_CACHES = {
    "locmem": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "django": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "vault_cache"},
    "upsert": {"BACKEND": "vault_core.throttle_cache.UpsertDatabaseCache", "LOCATION": "vault_cache"},
}
CACHES = {"default": _THROTTLE_CACHES[env("THROTTLE_CACHE", "upsert")]}

# Templates and static files exist only for the API docs page (Swagger UI assets from drf-spectacular-sidecar).
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True,
              "OPTIONS": {"context_processors": ["django.template.context_processors.request"]}}]
STATIC_URL = "static/"

# Error tracking (D-071): only when SENTRY_DSN is set, and never with personal data.
SENTRY_DSN = env("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    from vault_core.observability import sentry_options

    sentry_sdk.init(**sentry_options(SENTRY_DSN, env("SENTRY_ENVIRONMENT", "production"),
                                     float(env("SENTRY_TRACES_SAMPLE_RATE", "0"))))
