# labitory/settings/staging.py
"""
Staging Django settings for labitory project.

This file contains settings specific to staging environment.
Staging should closely mirror production but allow for testing.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from .production import *
from decouple import config, Csv

# Allow debug in staging if needed for troubleshooting
DEBUG = config('DEBUG', default=False, cast=bool)

# More permissive CORS for staging testing
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())

# Use less restrictive security settings in staging
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_HSTS_SECONDS = 0  # Don't enforce HSTS in staging

# Email configuration - may use different provider or console backend
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')

# Optional services in staging
TWILIO_ACCOUNT_SID = config('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = config('TWILIO_AUTH_TOKEN', default='')
TWILIO_PHONE_NUMBER = config('TWILIO_PHONE_NUMBER', default='')

# Push notification configuration - optional in staging
VAPID_PRIVATE_KEY = config('VAPID_PRIVATE_KEY', default='')
VAPID_PUBLIC_KEY = config('VAPID_PUBLIC_KEY', default='')
VAPID_SUBJECT = config('VAPID_SUBJECT', default='mailto:admin@staging.example.com')

# Use different database name for staging
if 'default' in DATABASES:
    DATABASES['default']['NAME'] = config('DB_NAME', default='labitory_staging')

# Staging-specific logging with more verbose output
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
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'staging_errors.log'),
            'maxBytes': 1024*1024*25,  # 25 MB
            'backupCount': 5,
            'formatter': 'json',
        },
        'app_file': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'staging_app.log'),
            'maxBytes': 1024*1024*25,  # 25 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'app_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['console', 'error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'booking': {
            'handlers': ['console', 'app_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'INFO' if DEBUG else 'WARNING',
            'propagate': False,
        },
        'root': {
            'handlers': ['console', 'error_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
    },
}

# Allow different cache timeout for staging testing
if 'default' in CACHES:
    CACHES['default']['TIMEOUT'] = 60  # Shorter cache timeout for testing

# Different Celery queue prefixes for staging
CELERY_TASK_ROUTES = {
    'booking.tasks.send_email_notification': {'queue': 'staging_notifications'},
    'booking.tasks.send_sms_notification': {'queue': 'staging_notifications'},
    'booking.tasks.generate_report': {'queue': 'staging_reports'},
}

# Staging-specific feature flags
FEATURE_FLAGS = {
    'ENABLE_NEW_DASHBOARD': config('ENABLE_NEW_DASHBOARD', default=True, cast=bool),
    'ENABLE_ADVANCED_REPORTING': config('ENABLE_ADVANCED_REPORTING', default=True, cast=bool),
    'ENABLE_BETA_FEATURES': config('ENABLE_BETA_FEATURES', default=True, cast=bool),
}

# Allow test data reset in staging
ALLOW_TEST_DATA_RESET = config('ALLOW_TEST_DATA_RESET', default=True, cast=bool)