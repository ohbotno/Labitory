# booking/admin/__init__.py
"""
Modularized admin configuration for the Aperture Booking system.
"""

# Import all admin configurations to register them with Django
from .core import *
from .bookings import *
from .resources import *

# Import any remaining admin configurations from the main admin.py
# This ensures backward compatibility while we transition to modular structure