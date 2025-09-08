# labitory/settings/__init__.py
"""
Settings module initialization.

This file determines which settings module to load based on the DJANGO_SETTINGS_MODULE
environment variable or defaults to development settings.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import os
from decouple import config

# Determine which settings to load
ENVIRONMENT = config('DJANGO_ENVIRONMENT', default='development')

# Mapping of environment names to settings modules
SETTINGS_MODULES = {
    'development': 'labitory.settings.development',
    'staging': 'labitory.settings.staging',
    'production': 'labitory.settings.production',
}

# Set the default Django settings module
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    settings_module = SETTINGS_MODULES.get(ENVIRONMENT, SETTINGS_MODULES['development'])
    os.environ['DJANGO_SETTINGS_MODULE'] = settings_module