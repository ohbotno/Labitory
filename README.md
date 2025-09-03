# Labitory v1.0.0

A comprehensive laboratory resource management system designed for academic institutions. Built with Django, Labitory provides conflict-free scheduling, collaborative booking management, and detailed analytics for efficient lab resource utilization.

[![License: Dual](https://img.shields.io/badge/License-Dual%20(GPL%2FCommercial)-blue.svg)](LICENSING.md)
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

Labitory is available under **dual licensing**:

### Open Source License (GPL-3.0) - FREE
- ✅ Full-featured lab booking system
- ✅ Commercial use allowed
- ✅ Complete source code access
- ❗ Must retain "Labitory" branding and attribution

### Commercial License - PAID
- 🎨 Remove all Labitory branding
- 🏷️ Add your own branding and customization
- 💼 Professional support included
- 🔒 No GPL obligations

**Pricing:** Starting at £1,599/year

📋 **[View Complete Licensing Guide](LICENSING.md)** | 💼 **[Get Commercial License](mailto:commercial@labitory.org)**

---

Made with ❤️ for the academic community | [Documentation](https://docs.labitory.org) | [Support](https://github.com/ohbotno/labitory/issues)