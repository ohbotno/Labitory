# booking/management/commands/run_scheduled_backups.py
"""
Management command for executing scheduled backups.

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
from django.utils import timezone
from datetime import datetime
import logging


class Command(BaseCommand):
    """
    Management command for executing scheduled backups.
    
    This command should be run periodically (e.g., every 5-15 minutes) via cron
    to check for and execute any scheduled backups that are due to run.
    
    Usage:
        python manage.py run_scheduled_backups
        python manage.py run_scheduled_backups --schedule-id 1
        python manage.py run_scheduled_backups --test
        python manage.py run_scheduled_backups --status
        python manage.py run_scheduled_backups --quiet
    """
    
    help = 'Execute scheduled backups that are due to run'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--schedule-id',
            type=int,
            help='Run a specific backup schedule by ID (ignores timing)'
        )
        
        parser.add_argument(
            '--test',
            action='store_true',
            help='Test mode - run all enabled schedules regardless of timing'
        )
        
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show status of all backup schedules and exit'
        )
        
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all backup schedules and exit'
        )
        
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Minimize output (only show errors)'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force execution even if schedule seems disabled'
        )
    
    def handle(self, *args, **options):
        """Execute the scheduled backup command."""
        from booking.backup_service import BackupService
        from booking.models import BackupSchedule
        
        # Set up logging
        if options['quiet']:
            logging.getLogger().setLevel(logging.ERROR)
        else:
            logging.getLogger().setLevel(logging.INFO)
        
        backup_service = BackupService()
        
        # Status mode
        if options['status']:
            self.show_backup_status(backup_service)
            return
        
        # List mode
        if options['list']:
            self.list_backup_schedules()
            return
        
        # Specific schedule mode
        if options['schedule_id']:
            self.run_specific_schedule(backup_service, options['schedule_id'], options)
            return
        
        # Test mode - run all schedules
        if options['test']:
            self.run_test_mode(backup_service, options)
            return
        
        # Normal mode - run scheduled backups
        self.run_scheduled_backups(backup_service, options)
    
    def run_scheduled_backups(self, backup_service, options):
        """Run normally scheduled backups."""
        try:
            if not options['quiet']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"🔄 Starting scheduled backup check at {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                )
            
            results = backup_service.run_scheduled_backups()
            
            if not options['quiet']:
                self.stdout.write(f"📊 Backup Summary:")
                self.stdout.write(f"   Total schedules: {results['total_schedules']}")
                self.stdout.write(f"   Executed: {results['executed']}")
                self.stdout.write(f"   Successful: {results['successful']}")
                self.stdout.write(f"   Failed: {results['failed']}")
                self.stdout.write(f"   Skipped: {results['skipped']}")
                
                # Show details for executed backups
                for result in results['schedule_results']:
                    if result['executed']:
                        status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
                        self.stdout.write(f"   {status}: {result['schedule_name']}")
                        if result['success'] and result['backup_name']:
                            self.stdout.write(f"      📦 Backup: {result['backup_name']}")
                        elif result['errors']:
                            for error in result['errors']:
                                self.stdout.write(f"      ⚠️ Error: {error}")
            
            # Show errors if any
            if results['errors']:
                for error in results['errors']:
                    self.stdout.write(self.style.ERROR(f"❌ {error}"))
            
            # Exit with appropriate code
            if results['failed'] > 0:
                raise CommandError(f"Some scheduled backups failed ({results['failed']}/{results['executed']})")
            
            if not options['quiet'] and results['executed'] == 0:
                self.stdout.write(self.style.WARNING("ℹ️ No backups were scheduled to run at this time"))
                
        except Exception as e:
            error_msg = f"❌ Scheduled backup execution failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            raise CommandError(str(e))
    
    def run_specific_schedule(self, backup_service, schedule_id, options):
        """Run a specific backup schedule by ID."""
        try:
            from booking.models import BackupSchedule
            
            schedule = BackupSchedule.objects.get(id=schedule_id)
            
            if not options['quiet']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"🔄 Running specific backup schedule: {schedule.name}"
                    )
                )
            
            result = backup_service.test_scheduled_backup(schedule_id)
            
            if result.get('success'):
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ Backup completed successfully: {result.get('backup_name', 'Unknown')}"
                    )
                )
            else:
                error_msg = f"❌ Backup failed: {'; '.join(result.get('errors', ['Unknown error']))}"
                self.stdout.write(self.style.ERROR(error_msg))
                raise CommandError("Backup failed")
                
        except BackupSchedule.DoesNotExist:
            raise CommandError(f"Backup schedule with ID {schedule_id} not found")
        except Exception as e:
            raise CommandError(f"Failed to run specific backup schedule: {str(e)}")
    
    def run_test_mode(self, backup_service, options):
        """Run all enabled schedules in test mode."""
        try:
            from booking.models import BackupSchedule
            
            schedules = BackupSchedule.objects.filter(enabled=True).exclude(frequency='disabled')
            
            if not schedules.exists():
                self.stdout.write(self.style.WARNING("⚠️ No enabled backup schedules found"))
                return
            
            if not options['quiet']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"🧪 Running {schedules.count()} backup schedules in test mode"
                    )
                )
            
            successful = 0
            failed = 0
            
            for schedule in schedules:
                if not options['quiet']:
                    self.stdout.write(f"🔄 Testing: {schedule.name}")
                
                result = backup_service.test_scheduled_backup(schedule.id)
                
                if result.get('success'):
                    successful += 1
                    if not options['quiet']:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"   ✅ Success: {result.get('backup_name', 'Unknown')}"
                            )
                        )
                else:
                    failed += 1
                    error_msg = '; '.join(result.get('errors', ['Unknown error']))
                    self.stdout.write(
                        self.style.ERROR(f"   ❌ Failed: {error_msg}")
                    )
            
            if not options['quiet']:
                self.stdout.write(f"📊 Test Results: {successful} successful, {failed} failed")
            
            if failed > 0:
                raise CommandError(f"Some test backups failed ({failed}/{successful + failed})")
                
        except Exception as e:
            raise CommandError(f"Test mode failed: {str(e)}")
    
    def show_backup_status(self, backup_service):
        """Show status of all backup schedules."""
        try:
            status = backup_service.get_backup_schedules_status()
            
            if 'error' in status:
                raise CommandError(f"Failed to get status: {status['error']}")
            
            self.stdout.write(self.style.HTTP_INFO("📊 Backup Schedules Status"))
            self.stdout.write("")
            
            self.stdout.write(f"📈 Overview:")
            self.stdout.write(f"   Total schedules: {status['total_schedules']}")
            self.stdout.write(f"   Enabled schedules: {status['enabled_schedules']}")
            self.stdout.write(f"   Healthy schedules: {status['healthy_schedules']}")
            
            if status['next_run']:
                self.stdout.write(f"   Next run: {status['next_run'].strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                self.stdout.write(f"   Next run: No schedules enabled")
            
            self.stdout.write("")
            
            if status['schedules']:
                self.stdout.write("📋 Schedule Details:")
                for schedule in status['schedules']:
                    health_icon = "🟢" if schedule['is_healthy'] else "🔴"
                    enabled_icon = "✅" if schedule['enabled'] else "❌"
                    
                    self.stdout.write(f"   {health_icon} {schedule['name']} ({enabled_icon} {schedule['frequency']})")
                    
                    if schedule['last_success']:
                        self.stdout.write(f"      Last success: {schedule['last_success'].strftime('%Y-%m-%d %H:%M:%S')}")
                    else:
                        self.stdout.write(f"      Last success: Never")
                    
                    self.stdout.write(f"      Success rate: {schedule['success_rate']}%")
                    
                    if schedule['consecutive_failures'] > 0:
                        self.stdout.write(f"      ⚠️ Consecutive failures: {schedule['consecutive_failures']}")
                    
                    if schedule['next_run']:
                        self.stdout.write(f"      Next run: {schedule['next_run'].strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    self.stdout.write("")
            else:
                self.stdout.write("ℹ️ No backup schedules configured")
                
        except Exception as e:
            raise CommandError(f"Failed to show backup status: {str(e)}")
    
    def list_backup_schedules(self):
        """List all backup schedules."""
        try:
            from booking.models import BackupSchedule
            
            schedules = BackupSchedule.objects.all()
            
            if not schedules.exists():
                self.stdout.write(self.style.WARNING("📋 No backup schedules found"))
                return
            
            self.stdout.write(self.style.HTTP_INFO(f"📋 Backup Schedules ({schedules.count()} total):"))
            self.stdout.write("")
            
            for schedule in schedules:
                enabled_status = "Enabled" if schedule.enabled else "Disabled"
                health_icon = "🟢" if schedule.is_healthy else "🔴"
                
                self.stdout.write(f"  {health_icon} ID {schedule.id}: {schedule.name}")
                self.stdout.write(f"      Status: {enabled_status}")
                self.stdout.write(f"      Frequency: {schedule.get_frequency_display()}")
                self.stdout.write(f"      Time: {schedule.backup_time}")
                
                if schedule.frequency == 'weekly':
                    day_name = schedule.get_day_of_week_display()
                    self.stdout.write(f"      Day: {day_name}")
                elif schedule.frequency == 'monthly':
                    self.stdout.write(f"      Day of month: {schedule.day_of_month}")
                
                components = []
                if schedule.include_database:
                    components.append("Database")
                if schedule.include_media:
                    components.append("Media")
                if schedule.include_configuration:
                    components.append("Config")
                self.stdout.write(f"      Components: {', '.join(components) if components else 'None'}")
                
                self.stdout.write(f"      Retention: {schedule.retention_days} days, max {schedule.max_backups_to_keep} backups")
                
                if schedule.total_runs > 0:
                    self.stdout.write(f"      Stats: {schedule.success_rate}% success rate ({schedule.total_successes}/{schedule.total_runs} runs)")
                
                self.stdout.write("")
                
        except Exception as e:
            raise CommandError(f"Failed to list backup schedules: {str(e)}")