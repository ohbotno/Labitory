# booking/management/commands/scheduler.py
"""
Management command for controlling the backup scheduler.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

from django.core.management.base import BaseCommand, CommandError
import signal
import sys


class Command(BaseCommand):
    """
    Management command for controlling the backup scheduler.
    
    Usage:
        python manage.py scheduler start
        python manage.py scheduler stop
        python manage.py scheduler status
        python manage.py scheduler restart
    """
    
    help = 'Control the backup scheduler'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['start', 'stop', 'status', 'restart'],
            help='Action to perform on the scheduler'
        )
        
        parser.add_argument(
            '--daemon',
            action='store_true',
            help='Run scheduler as a daemon (start action only)'
        )
    
    def handle(self, *args, **options):
        """Execute the scheduler command."""
        action = options['action']
        
        if action == 'start':
            self.start_scheduler(options.get('daemon', False))
        elif action == 'stop':
            self.stop_scheduler()
        elif action == 'status':
            self.show_status()
        elif action == 'restart':
            self.restart_scheduler()
    
    def start_scheduler(self, daemon=False):
        """Start the backup scheduler."""
        try:
            from booking.scheduler import get_scheduler
            
            scheduler = get_scheduler()
            
            if scheduler.started:
                self.stdout.write(self.style.WARNING("Scheduler is already running"))
                return
            
            scheduler.start()
            
            if daemon:
                self.stdout.write(self.style.SUCCESS("✅ Backup scheduler started as daemon"))
                
                # Set up signal handlers for graceful shutdown
                def signal_handler(sig, frame):
                    self.stdout.write("\n🛑 Stopping scheduler...")
                    scheduler.stop()
                    sys.exit(0)
                
                signal.signal(signal.SIGINT, signal_handler)
                signal.signal(signal.SIGTERM, signal_handler)
                
                # Keep the process running
                try:
                    signal.pause()
                except AttributeError:
                    # signal.pause() is not available on Windows
                    import time
                    while scheduler.started:
                        time.sleep(1)
            else:
                self.stdout.write(self.style.SUCCESS("✅ Backup scheduler started"))
                
        except Exception as e:
            raise CommandError(f"Failed to start scheduler: {str(e)}")
    
    def stop_scheduler(self):
        """Stop the backup scheduler."""
        try:
            from booking.scheduler import get_scheduler
            
            scheduler = get_scheduler()
            
            if not scheduler.started:
                self.stdout.write(self.style.WARNING("Scheduler is not running"))
                return
            
            scheduler.stop()
            self.stdout.write(self.style.SUCCESS("🛑 Backup scheduler stopped"))
            
        except Exception as e:
            raise CommandError(f"Failed to stop scheduler: {str(e)}")
    
    def show_status(self):
        """Show scheduler status."""
        try:
            from booking.scheduler import get_scheduler
            from booking.models import BackupSchedule
            
            scheduler = get_scheduler()
            status = scheduler.get_status()
            
            self.stdout.write(self.style.HTTP_INFO("📊 Backup Scheduler Status"))
            self.stdout.write("")
            
            if status['running']:
                self.stdout.write(f"🟢 Status: Running")
            else:
                self.stdout.write(f"🔴 Status: Stopped")
            
            self.stdout.write(f"📋 Active Jobs: {len(status['jobs'])}")
            
            if status['jobs']:
                self.stdout.write("")
                self.stdout.write("🔧 Scheduled Jobs:")
                for job in status['jobs']:
                    next_run = job['next_run'].strftime('%Y-%m-%d %H:%M:%S') if job['next_run'] else 'Not scheduled'
                    self.stdout.write(f"  • {job['name']} - Next: {next_run}")
            
            # Show backup schedules
            schedules = BackupSchedule.objects.all()
            self.stdout.write("")
            self.stdout.write(f"📅 Backup Schedules: {schedules.count()} total")
            
            enabled_schedules = schedules.filter(enabled=True).exclude(frequency='disabled')
            self.stdout.write(f"✅ Enabled: {enabled_schedules.count()}")
            
            for schedule in enabled_schedules:
                next_run = schedule.get_next_run_time()
                next_run_str = next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else 'Not scheduled'
                self.stdout.write(f"  • {schedule.name} ({schedule.frequency}) - Next: {next_run_str}")
                
        except Exception as e:
            raise CommandError(f"Failed to get scheduler status: {str(e)}")
    
    def restart_scheduler(self):
        """Restart the backup scheduler."""
        self.stdout.write("🔄 Restarting backup scheduler...")
        self.stop_scheduler()
        self.start_scheduler()
        self.stdout.write(self.style.SUCCESS("✅ Backup scheduler restarted"))