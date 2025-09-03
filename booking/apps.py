# booking/apps.py
"""
App configuration for the booking app.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
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