# booking/scheduler.py
"""
Background scheduler for automated backup tasks.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution
from django.utils import timezone
from django.conf import settings


logger = logging.getLogger(__name__)


def check_and_run_backups():
    """Check for scheduled backups and run them if due."""
    try:
        from .backup_service import BackupService
        
        backup_service = BackupService()
        results = backup_service.run_scheduled_backups()
        
        if results['executed'] > 0:
            logger.info(f"Scheduled backup check completed: {results['successful']}/{results['executed']} successful")
            
            # Log any failures
            if results['failed'] > 0:
                for error in results['errors']:
                    logger.error(f"Backup failed: {error}")
        
    except Exception as e:
        logger.error(f"Error during scheduled backup check: {e}")


def cleanup_old_job_executions(max_age_days=7):
    """Clean up old job execution records."""
    try:
        from datetime import timedelta
        from django_apscheduler.models import DjangoJobExecution
        
        cutoff_date = timezone.now() - timedelta(days=max_age_days)
        deleted_count = DjangoJobExecution.objects.filter(
            run_time__lt=cutoff_date
        ).delete()[0]
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old job execution records")
            
    except Exception as e:
        logger.error(f"Error cleaning up job executions: {e}")


def run_specific_schedule(schedule_id):
    """Run a specific backup schedule."""
    try:
        from .backup_service import BackupService
        from .models import BackupSchedule
        
        schedule = BackupSchedule.objects.get(id=schedule_id)
        if not schedule.enabled:
            return
        
        backup_service = BackupService()
        result = backup_service._execute_scheduled_backup(schedule)
        
        if result['success']:
            logger.info(f"Scheduled backup '{schedule.name}' completed successfully: {result['backup_name']}")
        else:
            error_msg = '; '.join(result.get('errors', ['Unknown error']))
            logger.error(f"Scheduled backup '{schedule.name}' failed: {error_msg}")
            
    except Exception as e:
        logger.error(f"Error running scheduled backup {schedule_id}: {e}")


class BackupScheduler:
    """Background scheduler for automated backup tasks."""
    
    def __init__(self):
        self.scheduler = None
        self.started = False
    
    def start(self):
        """Start the backup scheduler."""
        if self.started:
            return
        
        try:
            # Create scheduler with Django job store
            self.scheduler = BackgroundScheduler(timezone=str(timezone.get_current_timezone()))
            self.scheduler.add_jobstore(DjangoJobStore(), "default")
            
            # Add the main backup checking job
            self.scheduler.add_job(
                check_and_run_backups,
                'interval',
                minutes=5,  # Check every 5 minutes
                id='backup_checker',
                max_instances=1,
                replace_existing=True,
                misfire_grace_time=300  # 5 minutes grace period
            )
            
            # Add cleanup job for old job executions
            self.scheduler.add_job(
                cleanup_old_job_executions,
                'interval',
                hours=24,  # Clean up daily
                id='job_cleanup',
                max_instances=1,
                replace_existing=True
            )
            
            self.scheduler.start()
            self.started = True
            logger.info("Backup scheduler started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start backup scheduler: {e}")
    
    def stop(self):
        """Stop the backup scheduler."""
        if self.scheduler and self.started:
            try:
                self.scheduler.shutdown(wait=False)
                self.started = False
                logger.info("Backup scheduler stopped")
            except Exception as e:
                logger.error(f"Error stopping backup scheduler: {e}")
    
    
    def get_status(self):
        """Get scheduler status."""
        if not self.scheduler:
            return {'running': False, 'jobs': []}
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name or job.id,
                'next_run': job.next_run_time,
                'func_name': job.func.__name__ if job.func else 'Unknown'
            })
        
        return {
            'running': self.started and self.scheduler.running,
            'jobs': jobs
        }
    
    def add_schedule_job(self, schedule):
        """Add a job for a specific backup schedule."""
        if not self.scheduler or not self.started:
            return False
        
        try:
            job_id = f'backup_schedule_{schedule.id}'
            
            # Remove existing job if it exists
            try:
                self.scheduler.remove_job(job_id)
            except:
                pass
            
            if not schedule.enabled or schedule.frequency == 'disabled':
                return True
            
            # Calculate next run time
            next_run = schedule.get_next_run_time()
            if not next_run:
                return False
            
            # Ensure backup_time is properly formatted
            backup_time = schedule.backup_time
            if isinstance(backup_time, str):
                from datetime import time as datetime_time
                try:
                    # Parse string format like "14:30" or "02:00"
                    hour, minute = backup_time.split(':')
                    backup_hour = int(hour)
                    backup_minute = int(minute)
                except (ValueError, AttributeError):
                    # Fallback to default time if parsing fails
                    backup_hour = 2
                    backup_minute = 0
            else:
                backup_hour = backup_time.hour
                backup_minute = backup_time.minute
            
            # Add the job
            if schedule.frequency == 'daily':
                self.scheduler.add_job(
                    run_specific_schedule,
                    'cron',
                    hour=backup_hour,
                    minute=backup_minute,
                    args=[schedule.id],
                    id=job_id,
                    max_instances=1,
                    replace_existing=True
                )
            elif schedule.frequency == 'weekly':
                self.scheduler.add_job(
                    run_specific_schedule,
                    'cron',
                    day_of_week=schedule.day_of_week,
                    hour=backup_hour,
                    minute=backup_minute,
                    args=[schedule.id],
                    id=job_id,
                    max_instances=1,
                    replace_existing=True
                )
            elif schedule.frequency == 'monthly':
                self.scheduler.add_job(
                    run_specific_schedule,
                    'cron',
                    day=schedule.day_of_month,
                    hour=backup_hour,
                    minute=backup_minute,
                    args=[schedule.id],
                    id=job_id,
                    max_instances=1,
                    replace_existing=True
                )
            
            logger.info(f"Added schedule job for '{schedule.name}' (ID: {schedule.id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add schedule job for '{schedule.name}': {e}")
            return False
    
    def remove_schedule_job(self, schedule_id):
        """Remove a job for a specific backup schedule."""
        if not self.scheduler:
            return
        
        try:
            job_id = f'backup_schedule_{schedule_id}'
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed schedule job for schedule ID: {schedule_id}")
        except Exception as e:
            logger.debug(f"Failed to remove schedule job {schedule_id}: {e}")
    
    
    def refresh_all_schedules(self):
        """Refresh all backup schedule jobs."""
        try:
            from django.db import connection, OperationalError
            from .models import BackupSchedule
            
            # Check if database is available (avoid queries during migrations)
            try:
                connection.ensure_connection()
                # Test if we can actually query the database
                BackupSchedule.objects.exists()
            except (OperationalError, Exception) as e:
                logger.info(f"Database not ready, skipping schedule refresh: {e}")
                return
            
            # Remove all existing backup schedule jobs
            if self.scheduler:
                for job in self.scheduler.get_jobs():
                    if job.id.startswith('backup_schedule_'):
                        self.scheduler.remove_job(job.id)
            
            # Add all enabled schedules
            schedules = BackupSchedule.objects.filter(enabled=True).exclude(frequency='disabled')
            for schedule in schedules:
                self.add_schedule_job(schedule)
                
            logger.info(f"Refreshed {schedules.count()} backup schedule jobs")
            
        except Exception as e:
            logger.error(f"Error refreshing schedule jobs: {e}")


# Global scheduler instance
backup_scheduler = BackupScheduler()


def start_scheduler():
    """Start the global backup scheduler."""
    backup_scheduler.start()
    backup_scheduler.refresh_all_schedules()


def stop_scheduler():
    """Stop the global backup scheduler."""
    backup_scheduler.stop()


def get_scheduler():
    """Get the global backup scheduler instance."""
    return backup_scheduler