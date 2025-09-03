# booking/templatetags/notification_tags.py
"""
Template tags for notification preferences.

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

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, {})
    return {}


@register.filter  
def get_attr(obj, attr):
    """Get an attribute from an object."""
    if hasattr(obj, attr):
        return getattr(obj, attr)
    return None