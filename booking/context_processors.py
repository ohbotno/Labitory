"""
Context processors for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

from django.db.models import Q
from .models import Notification, AccessRequest, TrainingRequest, LabSettings


def has_model(model_name):
    """Check if a model exists to avoid import errors."""
    try:
        from . import models
        return hasattr(models, model_name)
    except:
        return False


def notification_context(request):
    """Add notification counts to template context."""
    if not request.user.is_authenticated:
        return {
            'unread_notifications_count': 0,
            'pending_access_requests_count': 0,
            'pending_training_requests_count': 0,
            'total_notifications_count': 0,
            'recent_notifications': [],
        }
    
    try:
        # Count unread in-app notifications
        unread_notifications = Notification.objects.filter(
            user=request.user,
            delivery_method='in_app',
            status__in=['pending', 'sent']
        ).count()
        
        # Count pending access requests for lab admins/technicians
        pending_access_requests = 0
        if hasattr(request.user, 'userprofile') and \
           (request.user.userprofile.role in ['technician', 'sysadmin'] or \
            request.user.groups.filter(name='Lab Admin').exists()):
            pending_access_requests = AccessRequest.objects.filter(
                status='pending'
            ).count()
        
        # Count pending training requests for lab admins/technicians
        pending_training_requests = 0
        if hasattr(request.user, 'userprofile') and \
           (request.user.userprofile.role in ['technician', 'sysadmin'] or \
            request.user.groups.filter(name='Lab Admin').exists()):
            if has_model('TrainingRequest'):
                pending_training_requests = TrainingRequest.objects.filter(
                    status='pending'
                ).count()
        
        # Get recent unread notifications for display
        recent_notifications = Notification.objects.filter(
            user=request.user,
            delivery_method='in_app',
            status__in=['pending', 'sent']
        ).select_related('booking', 'resource', 'access_request', 'training_request', 'maintenance').order_by('-created_at')[:5]
        
        # Total actionable items
        total_notifications = (
            unread_notifications + 
            pending_access_requests + 
            pending_training_requests
        )
        
        return {
            'unread_notifications_count': unread_notifications,
            'pending_access_requests_count': pending_access_requests,
            'pending_training_requests_count': pending_training_requests,
            'total_notifications_count': total_notifications,
            'recent_notifications': recent_notifications,
        }
        
    except Exception as e:
        # Fallback in case of any errors
        return {
            'unread_notifications_count': 0,
            'pending_access_requests_count': 0,
            'pending_training_requests_count': 0,
            'total_notifications_count': 0,
            'recent_notifications': [],
        }


def license_context(request):
    """
    Add license information to template context.
    """
    try:
        from booking.services.licensing import license_manager
        
        license_info = license_manager.get_license_info()
        enabled_features = license_manager.get_enabled_features()
        
        return {
            'license_info': license_info,
            'license_type': license_info.get('type', 'open_source'),
            'license_valid': license_info.get('is_valid', True),
            'enabled_features': enabled_features,
            'is_commercial_license': license_info.get('type') != 'open_source',
            'is_white_label': enabled_features.get('white_label', False),
        }
    except Exception:
        # Fallback to open source defaults if there's an error
        from booking.services.licensing import license_manager
        return {
            'license_info': {'type': 'open_source', 'is_valid': True},
            'license_type': 'open_source',
            'license_valid': True,
            'enabled_features': license_manager._get_default_open_source_features(),
            'is_commercial_license': False,
            'is_white_label': False,
        }


def branding_context(request):
    """
    Add branding configuration to template context.
    """
    try:
        from booking.services.licensing import get_branding_config
        
        branding = get_branding_config()
        
        # Get logo URLs with fallbacks
        logo_url = branding.logo_primary.url if branding.logo_primary else None
        favicon_url = branding.logo_favicon.url if branding.logo_favicon else None
        
        return {
            'branding': branding,
            'app_title': branding.app_title,
            'company_name': branding.company_name,
            'primary_color': branding.color_primary,
            'secondary_color': branding.color_secondary,
            'accent_color': branding.color_accent,
            'show_powered_by': branding.show_powered_by,
            'custom_css_variables': branding.get_css_variables() if hasattr(branding, 'get_css_variables') else {},
            'logo_url': logo_url,
            'favicon_url': favicon_url,
            'footer_text': branding.footer_text,
            'support_email': branding.support_email,
            'support_phone': branding.support_phone,
            'website_url': branding.website_url,
        }
    except Exception:
        # Fallback to defaults
        return {
            'branding': None,
            'app_title': 'Labitory',
            'company_name': 'Open Source User',
            'primary_color': '#007bff',
            'secondary_color': '#6c757d', 
            'accent_color': '#28a745',
            'show_powered_by': True,
            'custom_css_variables': {},
        }


def lab_settings_context(request):
    """Add lab settings to template context."""
    try:
        return {
            'lab_name': LabSettings.get_lab_name(),
        }
    except Exception:
        # Fallback to default
        return {
            'lab_name': 'Labitory',
        }


def version_context(request):
    """Add application version to template context."""
    try:
        from labitory import __version__
        return {
            'version': __version__,
        }
    except Exception:
        # Fallback to current version
        return {
            'version': '1.1.2',
        }


def theme_context(request):
    """Add user's theme preference to template context."""
    if not request.user.is_authenticated:
        return {
            'user_theme': 'light',
            'user_theme_preference': 'light'
        }  # Default for anonymous users
    
    try:
        user_profile = request.user.userprofile
        theme_preference = user_profile.theme_preference
        
        # For server-side rendering, resolve system theme to a default
        # The client-side JavaScript will handle actual system detection
        if theme_preference == 'system':
            # Try to detect from User-Agent hints or default to light
            # This is a simple fallback - the client JS will override this
            resolved_theme = 'light'
        else:
            resolved_theme = theme_preference
            
        return {
            'user_theme': resolved_theme,
            'user_theme_preference': theme_preference
        }
    except Exception:
        # Fallback to light theme if profile doesn't exist or error occurs
        return {
            'user_theme': 'light',
            'user_theme_preference': 'light'
        }