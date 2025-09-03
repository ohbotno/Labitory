# booking/services/__init__.py
"""
Business logic services for the Aperture Booking system.
"""

# Import service singletons for easy access
from .booking_service import booking_service
from .notification_service import notification_service

# Import service classes for dependency injection or custom instantiation
from .booking_service import BookingService
from .notification_service import NotificationService

# Import existing services for backward compatibility
try:
    from .backup_service import *
except ImportError:
    pass

try:
    from .checkin_service import *
except ImportError:
    pass

try:
    from .maintenance_service import *
except ImportError:
    pass

try:
    from .push_service import *
except ImportError:
    pass

try:
    from .sms_service import *
except ImportError:
    pass

try:
    from .update_service import *
except ImportError:
    pass

try:
    from .google_calendar import *
except ImportError:
    pass

# Removed licensing requirement - all features now available
# try:
#     from .licensing import *
# except ImportError:
#     pass

__all__ = [
    'booking_service',
    'notification_service',
    'BookingService',
    'NotificationService',
]