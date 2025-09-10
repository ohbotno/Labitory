# labitory/settings/production.py
"""
Production Django settings for labitory project.

This file contains settings specific to production environment.
All sensitive information should come from environment variables.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from .base import *
from decouple import config, Csv
import os

# SECURITY WARNING: never run with debug turned on in production!
DEBUG = False

# SECURITY WARNING: keep the secret key used in production secret!
# This MUST be set as an environment variable
SECRET_KEY = config('SECRET_KEY')

# Production hosts - must be explicitly set
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

# CSRF trusted origins - must be set for production
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', cast=Csv())

# Database configuration - PostgreSQL recommended for production
DB_ENGINE = config('DB_ENGINE', default='postgresql')

if DB_ENGINE == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT', default='5432'),
            'OPTIONS': {
                'sslmode': config('DB_SSLMODE', default='require'),
            },
            'CONN_MAX_AGE': 600,  # Connection pooling
        }
    }
elif DB_ENGINE == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT', default='3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                'sql_mode': 'STRICT_TRANS_TABLES',
            },
            'CONN_MAX_AGE': 600,  # Connection pooling
        }
    }
else:
    raise ValueError("Production must use PostgreSQL or MySQL, not SQLite")

# Cache configuration - Redis recommended for production
CACHE_BACKEND = config('CACHE_BACKEND', default='redis')

if CACHE_BACKEND == 'redis':
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
            'TIMEOUT': 300,  # 5 minutes default
        }
    }
else:
    # Fallback to database cache if Redis unavailable
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'cache_table',
        }
    }

# Session configuration - Use Redis in production
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = False

# Redis-specific session configuration
SESSION_REDIS_URL = config('REDIS_URL', default='redis://127.0.0.1:6379/2')
SESSION_REDIS_PREFIX = 'labitory:session:'

# Email configuration - Real email backend for production
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')

# SMS configuration (Twilio) - Required in production
TWILIO_ACCOUNT_SID = config('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = config('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = config('TWILIO_PHONE_NUMBER')

# Push notification configuration - Required for web notifications
VAPID_PRIVATE_KEY = config('VAPID_PRIVATE_KEY')
VAPID_PUBLIC_KEY = config('VAPID_PUBLIC_KEY')
VAPID_SUBJECT = config('VAPID_SUBJECT')

# Google OAuth credentials - Required for calendar integration
GOOGLE_OAUTH2_CLIENT_ID = config('GOOGLE_OAUTH2_CLIENT_ID')
GOOGLE_OAUTH2_CLIENT_SECRET = config('GOOGLE_OAUTH2_CLIENT_SECRET')

# Microsoft Azure AD credentials - Required for SSO in production
AZURE_AD_TENANT_ID = config('AZURE_AD_TENANT_ID')
AZURE_AD_CLIENT_ID = config('AZURE_AD_CLIENT_ID')
AZURE_AD_CLIENT_SECRET = config('AZURE_AD_CLIENT_SECRET')

# CORS settings - Restrictive for production
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', cast=Csv())
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

# Additional CORS security settings
CORS_ALLOWED_ORIGIN_REGEXES = config('CORS_ALLOWED_ORIGIN_REGEXES', default='', cast=Csv())
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-api-version',  # For API versioning
]

# Only allow specific methods
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# Preflight cache settings
CORS_PREFLIGHT_MAX_AGE = 86400  # 24 hours

# Expose specific headers to the frontend
CORS_EXPOSE_HEADERS = [
    'x-api-version',
    'x-ratelimit-limit',
    'x-ratelimit-remaining',
    'x-ratelimit-reset',
]

# Enable APScheduler in production
SCHEDULER_AUTOSTART = config('SCHEDULER_AUTOSTART', default=True, cast=bool)

# JWT Configuration
JWT_ACCESS_TOKEN_LIFETIME = config('JWT_ACCESS_TOKEN_LIFETIME', default=15, cast=int)  # minutes
JWT_REFRESH_TOKEN_LIFETIME = config('JWT_REFRESH_TOKEN_LIFETIME', default=7, cast=int)  # days
API_TOKEN_ROTATION_INTERVAL = config('API_TOKEN_ROTATION_INTERVAL', default=24, cast=int)  # hours

# Security settings for production
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
X_FRAME_OPTIONS = 'DENY'
USE_TZ = True

# Cookie security settings
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# Content Security Policy (basic)
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

# Static files configuration for production
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files configuration - Should use cloud storage
MEDIA_BACKEND = config('MEDIA_BACKEND', default='local')

if MEDIA_BACKEND == 's3':
    # AWS S3 configuration
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default=None)
    AWS_DEFAULT_ACL = 'private'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    else:
        MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'

# Production logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'json': {
            'format': '{"level": "{levelname}", "time": "{asctime}", "module": "{module}", "process": {process}, "thread": {thread}, "message": "{message}"}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'production_errors.log'),
            'maxBytes': 1024*1024*50,  # 50 MB
            'backupCount': 10,
            'formatter': 'json',
        },
        'app_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'production_app.log'),
            'maxBytes': 1024*1024*50,  # 50 MB
            'backupCount': 10,
            'formatter': 'json',
        },
        'security_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'production_security.log'),
            'maxBytes': 1024*1024*50,  # 50 MB
            'backupCount': 10,
            'formatter': 'json',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'app_file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['error_file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['security_file', 'error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security.csrf': {
            'handlers': ['security_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'booking': {
            'handlers': ['console', 'app_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'root': {
            'handlers': ['console', 'error_file'],
            'level': 'WARNING',
        },
    },
}

# Health check configuration
HEALTH_CHECK_ENABLED = config('HEALTH_CHECK_ENABLED', default=True, cast=bool)

# Monitoring configuration
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    
    sentry_logging = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.ERROR  # Send errors as events
    )
    
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), sentry_logging],
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
        send_default_pii=False,
        environment=config('ENVIRONMENT', default='production'),
        release=config('APP_VERSION', default='unknown'),
    )

# Rate limiting configuration (if django-ratelimit is installed)
RATELIMIT_ENABLE = config('RATELIMIT_ENABLE', default=True, cast=bool)
RATELIMIT_USE_CACHE = 'default'

# Celery configuration for background tasks
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default=config('REDIS_URL', default='redis://127.0.0.1:6379/0'))
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=config('REDIS_URL', default='redis://127.0.0.1:6379/0'))
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# Task routing for different queues
CELERY_TASK_ROUTES = {
    'booking.tasks.send_email_notification': {'queue': 'notifications'},
    'booking.tasks.send_sms_notification': {'queue': 'notifications'},
    'booking.tasks.generate_report': {'queue': 'reports'},
}

# Performance settings
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB