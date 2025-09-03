# booking/apps.py
"""
App configuration for the booking app.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

from django.apps import AppConfig
import os
import sys


class BookingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'booking'
    verbose_name = 'Labitory'
    
    def ready(self):
        """Initialize the app when Django starts."""
        # Import signals first
        try:
            import booking.signals
        except ImportError:
            pass
        
        # Check if scheduler should be started
        from django.conf import settings
        scheduler_autostart = getattr(settings, 'SCHEDULER_AUTOSTART', True)
        
        if not scheduler_autostart:
            return
            
        # Only start scheduler in main process, not in migrations or shell
        # Also avoid starting during migrations, makemigrations, or testing
        if (os.environ.get('RUN_MAIN') == 'true' or 
            ('runserver' in sys.argv and '--noreload' not in sys.argv)):
            
            # Don't start scheduler during migrations or tests
            if any(cmd in sys.argv for cmd in ['migrate', 'makemigrations', 'test', 'shell']):
                return
                
            # Defer scheduler startup to avoid database access during app initialization
            try:
                from threading import Timer
                from .scheduler import start_scheduler
                
                def delayed_start():
                    try:
                        start_scheduler()
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.info(f"Scheduler not started: {e}")
                
                # Start scheduler after 3 seconds to ensure Django is fully initialized
                Timer(3.0, delayed_start).start()
                
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Could not defer scheduler startup: {e}")