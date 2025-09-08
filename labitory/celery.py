# labitory/celery.py
"""
Celery configuration for Labitory.

This file configures Celery for background task processing, including:
- Email notifications
- SMS notifications  
- Report generation
- Maintenance tasks
- Scheduled jobs

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labitory.settings.production')

# Create the Celery app
app = Celery('labitory')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Optional configuration for different environments
if hasattr(settings, 'CELERY_TASK_ROUTES'):
    app.conf.update(task_routes=settings.CELERY_TASK_ROUTES)

# Celery beat schedule for periodic tasks
app.conf.beat_schedule = {
    'send-pending-notifications': {
        'task': 'booking.tasks.send_pending_notifications',
        'schedule': 60.0,  # Every minute
        'options': {'queue': 'notifications'}
    },
    'cleanup-old-notifications': {
        'task': 'booking.tasks.cleanup_old_notifications',
        'schedule': 3600.0,  # Every hour
        'options': {'queue': 'maintenance'}
    },
    'generate-daily-reports': {
        'task': 'booking.tasks.generate_daily_reports',
        'schedule': 86400.0,  # Daily
        'options': {'queue': 'reports'}
    },
    'check-resource-maintenance': {
        'task': 'booking.tasks.check_resource_maintenance',
        'schedule': 1800.0,  # Every 30 minutes
        'options': {'queue': 'maintenance'}
    },
}

# Task configuration
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone=settings.TIME_ZONE,
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Error handling
app.conf.task_annotations = {
    'booking.tasks.send_email_notification': {
        'rate_limit': '100/m',  # 100 emails per minute max
        'retry_policy': {
            'max_retries': 3,
            'interval_start': 0,
            'interval_step': 0.2,
            'interval_max': 0.2,
        }
    },
    'booking.tasks.send_sms_notification': {
        'rate_limit': '50/m',  # 50 SMS per minute max
        'retry_policy': {
            'max_retries': 3,
            'interval_start': 0,
            'interval_step': 0.2,
            'interval_max': 0.2,
        }
    },
}


@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery connectivity."""
    print(f'Request: {self.request!r}')
    return f'Debug task executed at {self.request.id}'