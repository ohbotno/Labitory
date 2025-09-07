# booking/views/main.py
"""
Main views for the Labitory - contains only essential views that can't be modularized.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial

All other views have been migrated to their respective modules:
- Core views (dashboard, profile, etc.) → modules/core.py
- Booking views → modules/bookings.py
- Resource views → modules/resources.py  
- Notification views → modules/notifications.py
- Template views → modules/templates.py
- Check-in views → modules/checkin.py
- Conflict views → modules/conflicts.py
- Approval views → modules/approvals.py
- Group management → modules/core.py
- ViewSets → viewsets/ directory
"""

from django.contrib.auth.views import LoginView
from django.utils import timezone

from ..models import UserProfile


class CustomLoginView(LoginView):
    """Custom login view that handles first login redirect logic."""
    
    def get_success_url(self):
        """Redirect to about page on first login, dashboard on subsequent logins."""
        user = self.request.user
        
        try:
            profile = user.userprofile
            
            # Check if this is the user's first login
            if profile.first_login is None:
                # Mark the first login time
                profile.first_login = timezone.now()
                profile.save()
                
                # Redirect to about page for first-time users
                return '/about/'
            else:
                # Redirect to dashboard for returning users
                return '/dashboard/'
                
        except UserProfile.DoesNotExist:
            # If no profile exists, redirect to about page
            return '/about/'