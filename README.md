# Labitory v2.0.0

A comprehensive laboratory resource management system designed for academic institutions. Built with Django, Labitory provides conflict-free scheduling, collaborative booking management, and detailed analytics for efficient lab resource utilization.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Django 4.2+](https://img.shields.io/badge/django-4.2+-green.svg)](https://www.djangoproject.com/)

## Key Features

- **Intelligent Booking System** - Conflict detection, recurring bookings, templates, and check-in/out
- **Multi-level Approvals** - Configurable workflows with delegation and risk assessment tracking  
- **User Management** - Role-based access, group management, training requirements, and lab inductions
- **Notification System** - Email, SMS, push, and in-app alerts with user preferences
- **Waiting Lists** - Automatic notifications when resources become available
- **Maintenance Scheduling** - Track maintenance windows, vendors, and costs
- **Analytics Dashboard** - Usage statistics, booking patterns, and comprehensive reporting
- **Calendar Integration** - Personal and public ICS feeds with import/export
- **Issue Tracking** - Report and manage resource issues with priority assignment
- **Training & Compliance** - Course management, certifications, and compliance tracking
- **Backup System** - Automated and manual backups with restoration
- **Mobile Responsive** - Full functionality on all devices

## Quick Start Guide

### Prerequisites
- Python 3.8 or higher
- pip package manager
- Git

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/ohbotno/labitory.git
cd labitory/
```

2. **Set up Python environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure the database**
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py create_email_templates
```

4. **Run the development server**
```bash
python manage.py runserver
```

Visit http://127.0.0.1:8000 to access Labitory.

### Production Deployment

For automated production deployment:
```bash
curl -fsSL https://raw.githubusercontent.com/ohbotno/labitory/main/easy_install.sh | sudo bash
```

This script handles all dependencies, database setup, SSL certificates, and service configuration.

## Environment Configuration

Labitory uses environment variables for configuration. Copy `.env.example` to `.env` and configure according to your environment.

### Core Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DJANGO_ENVIRONMENT` | Environment mode (`development`, `staging`, `production`) | `development` | Yes |
| `SECRET_KEY` | Django secret key for cryptographic signing | - | Yes |
| `DEBUG` | Enable debug mode (NEVER use in production) | `False` | Yes |
| `ALLOWED_HOSTS` | Comma-separated list of allowed host/domain names | - | Yes (production) |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated list of trusted origins for CSRF | - | Yes (production) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins | - | No |
| `TIME_ZONE` | System timezone | `Europe/London` | No |

**⚠️ Security Note**: Generate a unique `SECRET_KEY` for production:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Database Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DB_ENGINE` | Database engine (`sqlite`, `postgresql`, `mysql`) | `sqlite` | Yes |
| `DB_NAME` | Database name | `labitory` | Yes (if not SQLite) |
| `DB_USER` | Database username | - | Yes (if not SQLite) |
| `DB_PASSWORD` | Database password | - | Yes (if not SQLite) |
| `DB_HOST` | Database host | `localhost` | Yes (if not SQLite) |
| `DB_PORT` | Database port | `5432`/`3306` | Yes (if not SQLite) |
| `DB_SSLMODE` | PostgreSQL SSL mode (`require`, `disable`) | `require` | No |

### Redis & Caching

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `CACHE_BACKEND` | Cache backend (`redis`, `database`) | `redis` | No |
| `REDIS_URL` | Redis connection URL for cache | `redis://127.0.0.1:6379/1` | No |
| `REDIS_SESSION_DB` | Redis database for sessions | `2` | No |
| `CELERY_BROKER_URL` | Celery message broker URL | `redis://127.0.0.1:6379/0` | Yes (production) |
| `CELERY_RESULT_BACKEND` | Celery result backend URL | `redis://127.0.0.1:6379/0` | Yes (production) |
| `REDIS_SAVE_ENABLED` | Enable Redis persistence | `True` | No |
| `REDIS_MAXMEMORY_POLICY` | Redis eviction policy | `allkeys-lru` | No |

### Email Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `EMAIL_BACKEND` | Django email backend | `console.EmailBackend` | Yes |
| `EMAIL_HOST` | SMTP server hostname | `smtp.gmail.com` | Yes (if using SMTP) |
| `EMAIL_PORT` | SMTP server port | `587` | Yes (if using SMTP) |
| `EMAIL_USE_TLS` | Use TLS for email | `True` | No |
| `EMAIL_USE_SSL` | Use SSL for email | `False` | No |
| `EMAIL_HOST_USER` | SMTP authentication username | - | Yes (if using SMTP) |
| `EMAIL_HOST_PASSWORD` | SMTP authentication password | - | Yes (if using SMTP) |
| `DEFAULT_FROM_EMAIL` | Default sender email address | - | Yes (production) |

### SMS Configuration (Twilio)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | - | No |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | - | No |
| `TWILIO_PHONE_NUMBER` | Twilio phone number for sending SMS | - | No |

### Push Notifications

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `VAPID_PRIVATE_KEY` | VAPID private key for web push | - | No |
| `VAPID_PUBLIC_KEY` | VAPID public key for web push | - | No |
| `VAPID_SUBJECT` | VAPID subject (mailto: URL) | - | No |

**Generate VAPID keys**:
```bash
python -c "from py_vapid import Vapid; v = Vapid(); v.generate_keys(); print('Private:', v.private_key_pem().strip()); print('Public:', v.public_key_urlsafe())"
```

### OAuth & SSO Integration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GOOGLE_OAUTH2_CLIENT_ID` | Google OAuth2 Client ID | - | No |
| `GOOGLE_OAUTH2_CLIENT_SECRET` | Google OAuth2 Client Secret | - | No |
| `AZURE_AD_TENANT_ID` | Azure AD Tenant ID for SSO | - | No |
| `AZURE_AD_CLIENT_ID` | Azure AD Application Client ID | - | No |
| `AZURE_AD_CLIENT_SECRET` | Azure AD Client Secret | - | No |

### File Storage & AWS S3

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MEDIA_BACKEND` | Media storage backend (`local`, `s3`) | `local` | No |
| `AWS_ACCESS_KEY_ID` | AWS Access Key ID | - | Yes (if using S3) |
| `AWS_SECRET_ACCESS_KEY` | AWS Secret Access Key | - | Yes (if using S3) |
| `AWS_STORAGE_BUCKET_NAME` | S3 bucket name for media files | - | Yes (if using S3) |
| `AWS_S3_REGION_NAME` | AWS region | `us-east-1` | No |
| `AWS_S3_CUSTOM_DOMAIN` | CDN domain for S3 assets | - | No |

### Security Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SECURE_SSL_REDIRECT` | Redirect all HTTP to HTTPS | `False` | No |
| `RATELIMIT_ENABLE` | Enable rate limiting | `True` | No |

### Monitoring & Logging

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SENTRY_DSN` | Sentry error tracking DSN | - | No |
| `SENTRY_TRACES_SAMPLE_RATE` | Sentry performance monitoring sample rate | `0.1` | No |
| `ENVIRONMENT` | Environment name for monitoring | `development` | No |
| `APP_VERSION` | Application version for tracking | `1.0.0` | No |
| `HEALTH_CHECK_ENABLED` | Enable health check endpoints | `True` | No |

### Application Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `LAB_BOOKING_ADVANCE_DAYS` | Days in advance bookings can be made | `30` | No |
| `SCHEDULER_AUTOSTART` | Auto-start background scheduler | `False` | No |

### Feature Flags

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `ENABLE_NEW_DASHBOARD` | Enable new dashboard UI | `False` | No |
| `ENABLE_ADVANCED_REPORTING` | Enable advanced reporting features | `False` | No |
| `ENABLE_BETA_FEATURES` | Enable beta features | `False` | No |
| `ALLOW_TEST_DATA_RESET` | Allow test data reset (staging only) | `False` | No |

### Development Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `ENABLE_DEBUG_TOOLBAR` | Enable Django Debug Toolbar | `False` | No |
| `SHOW_SQL_QUERIES` | Show SQL queries in console | `False` | No |

### Example Production Configuration

```bash
# .env for production
DJANGO_ENVIRONMENT=production
SECRET_KEY=your-generated-secret-key
DEBUG=False
ALLOWED_HOSTS=labitory.yourdomain.com,www.labitory.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://labitory.yourdomain.com
DB_ENGINE=postgresql
DB_NAME=labitory_prod
DB_USER=labitory_user
DB_PASSWORD=strong-password-here
DB_HOST=db.yourdomain.com
REDIS_URL=redis://redis.yourdomain.com:6379/1
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.yourdomain.com
EMAIL_HOST_USER=noreply@yourdomain.com
EMAIL_HOST_PASSWORD=email-password-here
DEFAULT_FROM_EMAIL=Labitory <noreply@yourdomain.com>
SECURE_SSL_REDIRECT=True
```

## License

Labitory is **100% open source** under the Apache License 2.0.

### 🎆 Why Apache 2.0?
- ✅ **Completely free** to use, modify, and distribute
- ✅ **Commercial use allowed** - use it in your business
- 👆 **Attribution required** - give credit where it's due
- 🔒 **Patent protection** - prevents patent trolling
- 📝 **State changes** - modifications must be documented
- 🎯 **Professional** - used by Kubernetes, Android, Kafka

### 🙏 Attribution

If you use Labitory, we appreciate (but don't require) a mention like:
> "Powered by [Labitory](https://github.com/ohbotno/labitory)"

This helps us understand our impact in the scientific community.

### 🤝 Contributing

We welcome contributions! By contributing, you agree that your contributions will be licensed under Apache 2.0. See our [Contributing Guide](CONTRIBUTING.md) for details.

---

Made with ❤️ for the academic community | [Documentation](https://docs.labitory.org) | [Support](https://github.com/ohbotno/labitory/issues)