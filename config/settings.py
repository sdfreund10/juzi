"""
Django settings for config project.
"""

import mimetypes
import os
from pathlib import Path

import dj_database_url
import sentry_sdk
from dotenv import load_dotenv

# Ensure WhiteNoise/Django serve the web app manifest with the correct type.
mimetypes.add_type("application/manifest+json", ".webmanifest")

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-me-in-production",
)

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() in {"1", "true", "yes"}

if sentry_dsn := os.getenv("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment="development" if DEBUG else "production",
        release=os.getenv("SENTRY_RELEASE"),
        traces_sample_rate=0.0 if DEBUG else 1.0,
        send_default_pii=False,
        max_request_body_size="never",
    )


ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    "default": dj_database_url.config(
        default="postgres://juzi:juzi@localhost:5432/juzi_development",
        conn_max_age=600,
        engine="django.db.backends.postgresql",
    )
}
DATABASES["default"]["TEST"] = {
    "NAME": os.getenv("POSTGRES_TEST_DB", "juzi_test"),
}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/
#
# Built Preact assets live in frontend/dist and are served from the same origin
# via WhiteNoise (WHITENOISE_ROOT). Django admin/static still use STATIC_*.

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Manifest storage needs collectstatic; skip it in DEBUG so tests/CI can render
# admin without a staticfiles/ tree.
_STATICFILES_BACKEND = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if DEBUG
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": _STATICFILES_BACKEND,
    },
}

# Serve Vite build output (index.html, /assets/*, favicon, etc.) at site root.
WHITENOISE_ROOT = FRONTEND_DIST
WHITENOISE_INDEX_FILE = True
WHITENOISE_MIMETYPES = {".webmanifest": "application/manifest+json"}
# Keep sw.js / manifest near-fresh so clients pick up shell updates; hashed
# /assets/* still match WhiteNoise's immutable filename heuristic.
WHITENOISE_MAX_AGE = 60


# Default primary key field type
# https://docs.djangoproject.com/en/6.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Scheduling — streak ladder and mode unlock threshold (word-level easy_count)

# Maps minimum easy_streak → days until next due. Highest matching floor wins.
# Ladder: 1 → 1 day, 3–5 → 3 days, 6–9 → 7 days, 10+ → 14 days.
SCHEDULING_STREAK_INTERVALS: list[tuple[int, int]] = [
    (1, 1),
    (3, 3),
    (6, 7),
    (10, 14),
]
SCHEDULING_UNLOCK_EASY_COUNT = 5


# Django REST Framework

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "EXCEPTION_HANDLER": "api.exceptions.exception_handler",
}


# CORS — allow the Vite/Preact dev server (credentials for session cookies)

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True


# Production hardening (behind nginx TLS termination)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
