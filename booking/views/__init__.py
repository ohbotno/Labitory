# booking/views/__init__.py
"""
Views package for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

# Import all views from modularized structure for backward compatibility
from .modules import *

# Import views from main module (remaining views that haven't been modularized yet)
# Re-enabled to provide complete functionality while modular structure coexists
from .main import *

# Import new modular ViewSets for backward compatibility
from .viewsets import *

# Import licensing views module for URL routing
from . import licensing