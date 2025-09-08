# booking/utils/email.py
"""
Email utility functions for the Labitory application.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import base64
import os
from django.conf import settings


def get_logo_base64():
    """Get the logo as a base64 encoded string for email templates."""
    try:
        # First try to get custom logo from branding configuration
        from ..models import LicenseConfiguration
        try:
            license_config = LicenseConfiguration.objects.filter(is_active=True).first()
            if license_config and hasattr(license_config, 'branding') and license_config.branding.logo_primary:
                logo_path = license_config.branding.logo_primary.path
                if os.path.exists(logo_path):
                    with open(logo_path, 'rb') as logo_file:
                        logo_data = logo_file.read()
                        return base64.b64encode(logo_data).decode('utf-8')
        except Exception:
            pass
        
        # Fallback to default logo
        logo_path = os.path.join(settings.STATIC_ROOT or 'static', 'images', 'logo.png')
        if not os.path.exists(logo_path):
            # Fallback to development path
            logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'logo.png')
        
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as logo_file:
                logo_data = logo_file.read()
                return base64.b64encode(logo_data).decode('utf-8')
    except Exception:
        pass
    
    return None


def get_email_branding_context():
    """Get branding context for email templates."""
    from ..models import LicenseConfiguration, LabSettings
    
    context = {
        'app_title': 'Labitory',
        'company_name': 'Labitory',
        'lab_name': 'Labitory',
        'logo_base64': get_logo_base64(),
        'support_email': 'support@aperature-booking.org',
        'website_url': '',
        'show_powered_by': True,
    }
    
    try:
        # Get lab settings
        lab_name = LabSettings.get_lab_name()
        context['lab_name'] = lab_name
        
        # Get branding from license configuration
        license_config = LicenseConfiguration.objects.filter(is_active=True).first()
        if license_config and hasattr(license_config, 'branding'):
            branding = license_config.branding
            context.update({
                'app_title': branding.app_title,
                'company_name': branding.company_name,
                'support_email': branding.support_email or context['support_email'],
                'website_url': branding.website_url,
                'show_powered_by': branding.show_powered_by,
            })
    except Exception:
        pass
    
    return context