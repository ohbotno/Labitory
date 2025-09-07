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