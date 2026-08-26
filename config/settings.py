"""
Configurações do projeto PDV.

Sistema SaaS multi-tenant para gestão de PDV.

Configuração sensível é lida de variáveis de ambiente. Os valores padrão
existem apenas para facilitar o desenvolvimento local e NUNCA devem ser
utilizados em produção.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default="False"):
    return env(key, default).strip().lower() in {"1", "true", "yes", "on"}


def env_int(key, default):
    try:
        return int(env(key, default))
    except TypeError, ValueError:
        return int(default)


SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    "dev-insecure-key-apenas-para-desenvolvimento-local-nao-usar-em-producao",
)

DEBUG = env_bool("DJANGO_DEBUG", "True")

ALLOWED_HOSTS = [
    host.strip()
    for host in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Aplicações do projeto
    "apps.core.apps.CoreConfig",
    "apps.companies.apps.CompaniesConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.clients.apps.ClientsConfig",
    "apps.products.apps.ProductsConfig",
    "apps.inventory.apps.InventoryConfig",
    "apps.financial.apps.FinancialConfig",
    "apps.sales.apps.SalesConfig",
    "apps.fiscal.apps.FiscalConfig",
    "apps.printing.apps.PrintingConfig",
    "apps.audit.apps.AuditConfig",
    "apps.web.apps.WebConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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
        "DIRS": [BASE_DIR / "frontend" / "templates"],
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
ASGI_APPLICATION = "config.asgi.application"


# Banco de dados
# Produção: PostgreSQL via variáveis de ambiente.
# Desenvolvimento local (padrão): SQLite, sem necessidade de serviços externos.
if env("PDV_DB_ENGINE", "sqlite").lower() in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("PDV_DB_NAME", "pdv"),
            "USER": env("PDV_DB_USER", "pdv"),
            "PASSWORD": env("PDV_DB_PASSWORD", ""),
            "HOST": env("PDV_DB_HOST", "localhost"),
            "PORT": env("PDV_DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        ),
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Hash de senhas: bcrypt conforme diretriz do projeto.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "apps.clients.backends.ClientePlataformaBackend",
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/app/"
LOGOUT_REDIRECT_URL = "/"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

_FRONTEND_STATIC = BASE_DIR / "frontend" / "static"
STATICFILES_DIRS = [_FRONTEND_STATIC] if _FRONTEND_STATIC.exists() else []

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache: locmem no desenvolvimento (padrão). Em produção use "file" (sem
# depender de Redis) ou "memcached" — o throttle da API de impressão
# depende de um cache COMPARTILHADO entre os workers do gunicorn.
if env("PDV_CACHE_BACKEND", "locmem") == "file":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": env("PDV_CACHE_DIR", BASE_DIR / ".django-cache"),
        }
    }
elif env("PDV_CACHE_BACKEND") == "memcached":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.memcached.PyMemcacheCache",
            "LOCATION": env("PDV_CACHE_LOCATION", "127.0.0.1:11211"),
        }
    }

# Arquivos enviados (certificados A1 do módulo fiscal etc.). NUNCA servir
# este diretório publicamente no nginx — acesso apenas interno.
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("PDV_MEDIA_ROOT", BASE_DIR / "media"))

# Módulo fiscal NFC-e (tasks/TSK_00008.md).
# Produção exige configuração explícita; homologação é o padrão seguro.
SEFAZ_UF = env("SEFAZ_UF", "SP")
SEFAZ_AMBIENTE = env("SEFAZ_AMBIENTE", "HOMOLOGACAO")
SEFAZ_TIMEOUT = env_int("SEFAZ_TIMEOUT", 30)
# Senha do certificado A1 NUNCA vai para o banco ou logs.
SEFAZ_CERTIFICATE_PASSWORD = os.environ.get("SEFAZ_CERTIFICATE_PASSWORD", "")

# Segurança (produção deve definir DJANGO_DEBUG=False e as opções abaixo via env)
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", "True")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 0)
