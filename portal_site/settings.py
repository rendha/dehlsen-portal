"""
Settings of the ONE Dehlsen website (Sales + Project + Service + Task).

Works on your computer with no setup (SQLite, DEBUG on) and on a server when these environment variables are set:
    DJANGO_SECRET_KEY        a long random text (at least 32 characters)          - required on the server
    DJANGO_DEBUG             "1" to switch debug on (default: on only when no DATABASE_URL and no RENDER_EXTERNAL_HOSTNAME)
    DJANGO_ALLOWED_HOSTS     comma separated addresses (Render's address is added by itself)
    DATABASE_URL             postgresql://...   (without it: the SQLite file db.sqlite3, or SQLITE_PATH)
    ADMIN_PASSKEY            the passkey that unlocks the rates / reports of the Sales app (as before)
    MATERIALS_API_KEY        (optional) the Project app reads quotations directly now; this is only for the old API address
"""
import hashlib
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_list(name):
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _env_bool(name, default):
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


ON_SERVER = bool(os.environ.get("DATABASE_URL") or os.environ.get("RENDER_EXTERNAL_HOSTNAME"))
DEBUG = _env_bool("DJANGO_DEBUG", not ON_SERVER)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-local-development-key-do-not-use-on-a-server"
    else:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY to a long random text (at least 32 characters).  "
                                   "Make one with:  python -c \"import secrets; print(secrets.token_urlsafe(50))\"")

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS") + ["localhost", "127.0.0.1", "[::1]"]
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append("https://" + _render_host)

# The Project app reads the quotations straight from the Sales app, so no key has to be set.  (Only used when the old API address is called.)
os.environ.setdefault("MATERIALS_API_KEY", hashlib.sha256(("materials-api|" + SECRET_KEY).encode()).hexdigest())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "portal",
    "quotations",     # Sales
    "store",          # Project (materials)
    "cleaning",       # Service (cleaning manager)
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",     # everybody signs in, once, for everything
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "portal.middleware.HomeButtonMiddleware",                     # the small "Home" button inside Sales / Project / Service
]

ROOT_URLCONF = "portal_site.urls"
WSGI_APPLICATION = "portal_site.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],          # the Service app's own pages (base.html, dashboard.html ...)
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "store.context.roles",                  # the Project app's top bar
        "portal.context.portal",
    ]},
}]

if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"], conn_max_age=60,
                                                  ssl_require=_env_bool("DATABASE_SSL_REQUIRE", False))}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
                             "NAME": os.environ.get("SQLITE_PATH") or BASE_DIR / "db.sqlite3",
                             "OPTIONS": {"timeout": 20}}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
# Stay signed in until the person taps Log out.  Browsers keep a cookie for at most about 400 days, and every visit
# renews it, so someone who uses the site now and then is never signed out by time.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 400
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").is_dir() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = _env_bool("DJANGO_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^offline/$"]          # the platform's health check calls this page
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
}
