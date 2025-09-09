"""
Context processors for the Labitory.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
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
    # Removed licensing requirement - all features now available
    """
    # All features are now freely available
    return {
        'license_info': {'type': 'open_source', 'is_valid': True},
        'license_type': 'open_source',
        'license_valid': True,
        'enabled_features': {
            'advanced_reports': True,
            'custom_branding': True,
            'sms_notifications': True,
            'calendar_sync': True,
            'maintenance_tracking': True,
            'white_label': False,
            'multi_tenant': False,
        },
        'is_commercial_license': False,
        'is_white_label': False,
    }


def branding_context(request):
    """
    Add branding configuration to template context.
    # Removed licensing requirement - all features now available
    """
    # Default branding settings - all features freely available
    return {
        'branding': None,
        'app_title': 'Labitory',
        'company_name': 'Open Source User',
        'primary_color': '#007bff',
        'secondary_color': '#6c757d', 
        'accent_color': '#28a745',
        'show_powered_by': True,
        'custom_css_variables': {},
        'logo_url': None,
        'favicon_url': None,
        'footer_text': '',
        'support_email': '',
        'support_phone': '',
        'website_url': '',
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


def azure_ad_context(request):
    """Provide Azure AD configuration to templates."""
    from django.conf import settings
    
    return {
        'AZURE_AD_CLIENT_ID': getattr(settings, 'AZURE_AD_CLIENT_ID', ''),
        'AZURE_AD_ENABLED': bool(
            getattr(settings, 'AZURE_AD_CLIENT_ID', '') and 
            getattr(settings, 'AZURE_AD_CLIENT_SECRET', '') and 
            getattr(settings, 'AZURE_AD_TENANT_ID', '')
        ),
    }