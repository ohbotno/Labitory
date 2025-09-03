# ViewSets module - organized by domain functionality
# This module contains all DRF ViewSets extracted from main.py for better organization

# Import all ViewSets for backward compatibility
from .users import UserProfileViewSet
from .bookings import BookingViewSet
from .resources import ResourceViewSet, ResourceResponsibleViewSet
from .notifications import NotificationViewSet, NotificationPreferenceViewSet, WaitingListEntryViewSet

# Expose all ViewSets at module level for backward compatibility
__all__ = [
    'UserProfileViewSet',
    'BookingViewSet', 
    'ResourceViewSet',
    'ResourceResponsibleViewSet',
    'NotificationViewSet',
    'NotificationPreferenceViewSet', 
    'WaitingListEntryViewSet'
]