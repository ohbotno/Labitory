# labitory/settings/base.py
"""
Base Django settings for labitory project.

This file contains common settings shared across all environments.
Environment-specific settings should be placed in their respective files.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import os
from pathlib import Path
from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Ensure logs directory exists
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# SECURITY WARNING: keep the secret key used in production secret!
# This should be overridden in environment-specific settings
# Base settings should not define SECRET_KEY - each environment should set it

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'django_ratelimit',
    'django_apscheduler',
    'booking',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'booking.middleware.security.SecurityHeadersMiddleware',
    'booking.middleware.security.SecurityEventMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'booking.middleware.security.SessionSecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'booking.middleware.security.ContentSanitizationMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'booking.middleware.security.RateLimitMiddleware',
]

ROOT_URLCONF = 'labitory.urls'

# Django REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_VERSIONING_CLASS': 'booking.api.versioning.LabitoryAPIVersioning',
    'DEFAULT_VERSION': 'v1',
    'ALLOWED_VERSIONS': ['v1', 'v2'],
    'VERSION_PARAM': 'version',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'booking.api.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    },
    'PAGE_SIZE': 20,
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
}

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
                'booking.context_processors.notification_context',
                'booking.context_processors.license_context',
                'booking.context_processors.branding_context',
                'booking.context_processors.lab_settings_context',
                'booking.context_processors.version_context',
                'booking.context_processors.theme_context',
                'booking.context_processors.azure_ad_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'labitory.wsgi.application'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = config('TIME_ZONE', default='Europe/London')
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# Authentication backend - extensible for SSO
AUTHENTICATION_BACKENDS = [
    'booking.auth_backends.AzureADBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Microsoft Azure AD Configuration
AZURE_AD_TENANT_ID = ''  # Will be set in environment-specific settings
AZURE_AD_CLIENT_ID = ''
AZURE_AD_CLIENT_SECRET = ''
AZURE_AD_REDIRECT_URI = '/auth/azure/callback/'
AZURE_AD_SCOPES = ['openid', 'profile', 'email']
AZURE_AD_AUTHORITY = 'https://login.microsoftonline.com/'

# Login/Logout URLs
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Messages framework
from django.contrib.messages import constants as messages
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'
MESSAGE_TAGS = {
    messages.DEBUG: 'secondary',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}

# Password validation
# Override Django's default AUTH_PASSWORD_VALIDATORS setting
# This will be used by Django's built-in password validation system
AUTH_PASSWORD_VALIDATORS = AUTH_PASSWORD_VALIDATORS

# Lab booking specific settings
LAB_BOOKING_WINDOW_START = 9  # 09:00
LAB_BOOKING_WINDOW_END = 18   # 18:00
LAB_BOOKING_ADVANCE_DAYS = config('LAB_BOOKING_ADVANCE_DAYS', default=30, cast=int)

# APScheduler configuration
SCHEDULER_CONFIG = {
    "apscheduler.jobstores.default": {
        "class": "django_apscheduler.jobstores:DjangoJobStore"
    },
    "apscheduler.executors.processpool": {
        "type": "threadpool"
    },
    "apscheduler.executors.default": {
        "class": "apscheduler.executors.pool:ThreadPoolExecutor",
        "max_workers": "20",
    },
    "apscheduler.job_defaults.coalesce": "false",
    "apscheduler.job_defaults.max_instances": "3",
    "apscheduler.timezone": 'UTC',
}

# Common email configuration (will be overridden per environment)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@example.com')

# Google Calendar OAuth Integration
GOOGLE_CALENDAR_SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/userinfo.email'
]

# Rate Limiting Configuration
RATELIMIT_ENABLE = config('RATELIMIT_ENABLE', default=True, cast=bool)
RATELIMIT_USE_CACHE = 'default'

# Rate limit settings for different view types
RATELIMIT_LOGIN_ATTEMPTS = config('RATELIMIT_LOGIN_ATTEMPTS', default=5, cast=int)  # per 15 minutes
RATELIMIT_API_REQUESTS = config('RATELIMIT_API_REQUESTS', default=100, cast=int)    # per hour
RATELIMIT_BOOKING_REQUESTS = config('RATELIMIT_BOOKING_REQUESTS', default=10, cast=int)  # per 15 minutes
RATELIMIT_PASSWORD_RESET = config('RATELIMIT_PASSWORD_RESET', default=3, cast=int)  # per hour

# Authentication security settings
AUTH_MAX_FAILED_ATTEMPTS = config('AUTH_MAX_FAILED_ATTEMPTS', default=5, cast=int)  # Maximum failed login attempts
AUTH_LOCKOUT_DURATION = config('AUTH_LOCKOUT_DURATION', default=1800, cast=int)     # Account lockout duration in seconds (30 min default)
AUTH_TRACK_FAILED_ATTEMPTS = config('AUTH_TRACK_FAILED_ATTEMPTS', default=True, cast=bool)  # Track failed attempts in user profile

# Password complexity settings
AUTH_PASSWORD_MIN_LENGTH = config('AUTH_PASSWORD_MIN_LENGTH', default=8, cast=int)
AUTH_PASSWORD_REQUIRE_UPPERCASE = config('AUTH_PASSWORD_REQUIRE_UPPERCASE', default=True, cast=bool)
AUTH_PASSWORD_REQUIRE_LOWERCASE = config('AUTH_PASSWORD_REQUIRE_LOWERCASE', default=True, cast=bool)
AUTH_PASSWORD_REQUIRE_DIGITS = config('AUTH_PASSWORD_REQUIRE_DIGITS', default=True, cast=bool)
AUTH_PASSWORD_REQUIRE_SYMBOLS = config('AUTH_PASSWORD_REQUIRE_SYMBOLS', default=True, cast=bool)
AUTH_PASSWORD_MIN_UNIQUE_CHARS = config('AUTH_PASSWORD_MIN_UNIQUE_CHARS', default=4, cast=int)

# Django password validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': AUTH_PASSWORD_MIN_LENGTH,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    {
        'NAME': 'booking.utils.password_utils.PasswordComplexityValidator',
        'OPTIONS': {
            'min_length': AUTH_PASSWORD_MIN_LENGTH,
            'require_uppercase': AUTH_PASSWORD_REQUIRE_UPPERCASE,
            'require_lowercase': AUTH_PASSWORD_REQUIRE_LOWERCASE,
            'require_digits': AUTH_PASSWORD_REQUIRE_DIGITS,
            'require_symbols': AUTH_PASSWORD_REQUIRE_SYMBOLS,
            'min_unique_chars': AUTH_PASSWORD_MIN_UNIQUE_CHARS,
        }
    },
    {
        'NAME': 'booking.utils.password_utils.CommonPasswordValidator',
    },
]

# =============================================================================
# FILE UPLOAD & VALIDATION SETTINGS
# =============================================================================

# File upload size limits (in bytes)
MAX_FILE_SIZE = config('MAX_FILE_SIZE', default=10 * 1024 * 1024, cast=int)  # 10MB default
MAX_IMAGE_SIZE = config('MAX_IMAGE_SIZE', default=5 * 1024 * 1024, cast=int)  # 5MB default  
MAX_DOCUMENT_SIZE = config('MAX_DOCUMENT_SIZE', default=20 * 1024 * 1024, cast=int)  # 20MB default

# File validation settings
FILE_VALIDATION_ENABLED = config('FILE_VALIDATION_ENABLED', default=True, cast=bool)
FILE_VIRUS_SCAN_ENABLED = config('FILE_VIRUS_SCAN_ENABLED', default=True, cast=bool)
FILE_CONTENT_SCAN_ENABLED = config('FILE_CONTENT_SCAN_ENABLED', default=True, cast=bool)
FILE_STRIP_EXIF = config('FILE_STRIP_EXIF', default=True, cast=bool)

# Image processing settings
IMAGE_AUTO_ORIENT = config('IMAGE_AUTO_ORIENT', default=True, cast=bool)
IMAGE_JPEG_QUALITY = config('IMAGE_JPEG_QUALITY', default=85, cast=int)
IMAGE_WEBP_QUALITY = config('IMAGE_WEBP_QUALITY', default=80, cast=int)
IMAGE_MAX_DIMENSIONS = config('IMAGE_MAX_DIMENSIONS', default='2048x2048')  # WIDTHxHEIGHT
IMAGE_GENERATE_THUMBNAILS = config('IMAGE_GENERATE_THUMBNAILS', default=True, cast=bool)

# Parse image max dimensions
try:
    IMAGE_MAX_WIDTH, IMAGE_MAX_HEIGHT = map(int, IMAGE_MAX_DIMENSIONS.split('x'))
except ValueError:
    IMAGE_MAX_WIDTH, IMAGE_MAX_HEIGHT = 2048, 2048

# Allowed file types by category
ALLOWED_IMAGE_TYPES = [
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/svg+xml'
]

ALLOWED_DOCUMENT_TYPES = [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel', 
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain', 'text/csv', 'application/rtf'
]

ALLOWED_ARCHIVE_TYPES = [
    'application/zip', 'application/x-zip-compressed', 'application/x-rar-compressed',
    'application/x-tar', 'application/gzip'
]

# All allowed file types combined
ALLOWED_FILE_TYPES = ALLOWED_IMAGE_TYPES + ALLOWED_DOCUMENT_TYPES + ALLOWED_ARCHIVE_TYPES

# ClamAV virus scanning settings
CLAMAV_ENABLED = config('CLAMAV_ENABLED', default=False, cast=bool)
CLAMAV_SOCKET_PATH = config('CLAMAV_SOCKET_PATH', default='/var/run/clamav/clamd.ctl')
CLAMAV_TCP_HOST = config('CLAMAV_TCP_HOST', default='localhost')
CLAMAV_TCP_PORT = config('CLAMAV_TCP_PORT', default=3310, cast=int)

# File storage organization
FILE_UPLOAD_TEMP_DIR = config('FILE_UPLOAD_TEMP_DIR', default=None)
FILE_UPLOAD_PERMISSIONS = 0o644