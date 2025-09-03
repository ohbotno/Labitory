# booking/templatetags/booking_extras.py
"""
Template tags and filters for booking-related functionality.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django import template
from datetime import timedelta

register = template.Library()


@register.filter
def duration_to(start_time, end_time):
    """
    Calculate and format the duration between two datetime objects.
    Usage: {{ start_time|duration_to:end_time }}
    """
    if not start_time or not end_time:
        return "Unknown"
    
    try:
        duration = end_time - start_time
        
        # Extract days, hours, and minutes
        days = duration.days
        seconds = duration.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        # Format the duration string
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0 and days == 0:  # Only show minutes if less than a day
            parts.append(f"{minutes}m")
        
        if not parts:
            return "< 1m"
        
        return " ".join(parts)
    
    except (TypeError, AttributeError):
        return "Invalid"


@register.filter
def sub(value, arg):
    """
    Subtract arg from value. Useful for datetime calculations.
    Usage: {{ end_time|sub:start_time }}
    """
    try:
        return value - arg
    except (TypeError, ValueError):
        return ""


@register.filter
def div(value, arg):
    """
    Divide value by arg.
    Usage: {{ seconds|div:3600 }}
    """
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0


# =============================================================================
# Google Calendar Integration Template Tags
# =============================================================================

@register.filter
def has_google_calendar_integration(user):
    """Check if user has Google Calendar integration enabled."""
    try:
        from ..models import GoogleCalendarIntegration
        return GoogleCalendarIntegration.objects.filter(
            user=user, 
            is_active=True
        ).exists()
    except Exception:
        return False


@register.filter
def badge_color(status_text):
    """Convert status text to Bootstrap badge color."""
    if not status_text:
        return 'secondary'
    
    status_lower = status_text.lower()
    
    if 'active' in status_lower or 'connected' in status_lower or 'success' in status_lower:
        return 'success'
    elif 'error' in status_lower or 'failed' in status_lower or 'expired' in status_lower:
        return 'danger'
    elif 'warning' in status_lower or 'issue' in status_lower:
        return 'warning'
    elif 'disabled' in status_lower or 'disconnected' in status_lower:
        return 'secondary'
    else:
        return 'info'


@register.filter
def replace(value, args):
    """Replace text in a string. Usage: {{ text|replace:"old,new" }}"""
    if not args:
        return value
    
    try:
        old, new = args.split(',', 1)
        return str(value).replace(old, new)
    except (ValueError, AttributeError):
        return value


@register.filter
def get_form_field(form, field_name):
    """
    Get a form field by name. Usage: {{ form|get_form_field:"field_name" }}
    This allows dynamic field access in templates.
    """
    try:
        return form[field_name]
    except KeyError:
        return None


@register.filter
def get_item(dictionary, key):
    """
    Get an item from a dictionary by key. Usage: {{ dict|get_item:key }}
    This allows dynamic dictionary access in templates.
    """
    try:
        if hasattr(dictionary, 'get'):
            return dictionary.get(key)
        else:
            return dictionary[key]
    except (KeyError, TypeError):
        return None


@register.filter
def make_query_string(query_dict):
    """
    Convert a QueryDict to a query string. Usage: {{ request.GET|make_query_string }}
    This creates URL parameters from GET parameters, excluding 'page'.
    """
    try:
        from django.http import QueryDict
        
        # Create a copy and remove 'page' parameter for pagination
        params = query_dict.copy()
        if 'page' in params:
            del params['page']
        
        # Convert to query string
        if params:
            return '&' + params.urlencode()
        return ''
    except (AttributeError, TypeError):
        return ''


@register.simple_tag
def get_checklist_fields(form, item_id):
    """
    Get all three checklist fields for an item (enabled, order, required).
    Usage: {% get_checklist_fields form item.id as fields %}
    Returns a dict with enabled, order, and required fields.
    """
    try:
        return {
            'enabled': form[f'item_{item_id}_enabled'],
            'order': form[f'item_{item_id}_order'],
            'required': form[f'item_{item_id}_required'],
        }
    except KeyError as e:
        return {
            'enabled': None,
            'order': None,
            'required': None,
            'error': str(e)
        }