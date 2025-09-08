# booking/tasks.py
"""
Celery tasks for background processing in the Labitory system.

This file defines all background tasks including:
- Email notifications
- SMS notifications
- Report generation
- Maintenance checks
- Data cleanup

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from celery import shared_task
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.mail import send_mail, send_mass_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.db import transaction

# Import models
from .models import (
    Notification, NotificationPreference, Booking, Resource, 
    MaintenanceSchedule, EmailConfiguration, SMSConfiguration
)
from .services.notification_service import NotificationService
from .services.sms_service import SMSService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_email_notification(self, notification_id: int):
    """
    Send email notification for a specific notification.
    This task is retryable and handles email failures gracefully.
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        
        # Check if user has email notifications enabled
        prefs = NotificationPreference.objects.filter(user=notification.user).first()
        if not prefs or not prefs.email_enabled:
            logger.info(f"Email disabled for user {notification.user.id}, skipping notification {notification_id}")
            return f"Email disabled for user {notification.user.id}"
        
        # Get email configuration
        email_config = EmailConfiguration.get_current_config()
        if not email_config or not email_config.enabled:
            logger.warning("Email configuration not enabled, skipping email notification")
            return "Email configuration not enabled"
        
        # Prepare email content
        subject = notification.title
        html_message = render_to_string('emails/notification.html', {
            'notification': notification,
            'user': notification.user,
            'site_name': getattr(settings, 'SITE_NAME', 'Labitory'),
        })
        plain_message = notification.message
        
        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=email_config.from_email,
            recipient_list=[notification.user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        # Update notification status
        notification.email_sent = True
        notification.email_sent_at = timezone.now()
        notification.save(update_fields=['email_sent', 'email_sent_at'])
        
        logger.info(f"Email sent successfully for notification {notification_id}")
        return f"Email sent to {notification.user.email}"
        
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} does not exist")
        return f"Notification {notification_id} not found"
    
    except Exception as exc:
        logger.error(f"Failed to send email for notification {notification_id}: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def send_sms_notification(self, notification_id: int):
    """
    Send SMS notification for a specific notification.
    This task is retryable and handles SMS failures gracefully.
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        
        # Check if user has SMS notifications enabled
        prefs = NotificationPreference.objects.filter(user=notification.user).first()
        if not prefs or not prefs.sms_enabled or not prefs.phone_number:
            logger.info(f"SMS disabled or no phone for user {notification.user.id}, skipping notification {notification_id}")
            return f"SMS disabled or no phone for user {notification.user.id}"
        
        # Use SMS service
        sms_service = SMSService()
        if not sms_service.is_enabled():
            logger.warning("SMS service not enabled, skipping SMS notification")
            return "SMS service not enabled"
        
        # Send SMS
        message = f"{notification.title}: {notification.message}"
        success = sms_service.send_sms(prefs.phone_number, message)
        
        if success:
            # Update notification status
            notification.sms_sent = True
            notification.sms_sent_at = timezone.now()
            notification.save(update_fields=['sms_sent', 'sms_sent_at'])
            
            logger.info(f"SMS sent successfully for notification {notification_id}")
            return f"SMS sent to {prefs.phone_number}"
        else:
            raise Exception("SMS service returned failure")
        
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} does not exist")
        return f"Notification {notification_id} not found"
    
    except Exception as exc:
        logger.error(f"Failed to send SMS for notification {notification_id}: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def send_pending_notifications():
    """
    Process all pending notifications and send them via appropriate channels.
    This task runs periodically to handle notification queue.
    """
    processed = 0
    
    # Get notifications that haven't been sent yet
    pending_notifications = Notification.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=24),  # Only recent notifications
        email_sent=False,
        sms_sent=False,
        is_read=False
    ).select_related('user', 'booking', 'booking__resource')
    
    for notification in pending_notifications:
        # Schedule email task
        send_email_notification.delay(notification.id)
        
        # Schedule SMS task
        send_sms_notification.delay(notification.id)
        
        processed += 1
    
    logger.info(f"Scheduled notifications for {processed} pending items")
    return f"Processed {processed} notifications"


@shared_task
def send_booking_reminders():
    """
    Send reminder notifications for upcoming bookings.
    This task runs hourly to check for bookings that need reminders.
    """
    now = timezone.now()
    reminder_time = now + timedelta(hours=1)  # 1 hour reminder
    
    # Find bookings starting within the next hour that haven't been reminded
    upcoming_bookings = Booking.objects.filter(
        start_time__range=(now, reminder_time),
        status='confirmed',
        reminder_sent=False
    ).select_related('user', 'resource')
    
    reminders_sent = 0
    
    for booking in upcoming_bookings:
        # Create reminder notification
        notification = Notification.objects.create(
            user=booking.user,
            notification_type='booking_reminder',
            title='Booking Reminder',
            message=f'Your booking "{booking.title}" for {booking.resource.name} starts in 1 hour.',
            booking=booking
        )
        
        # Send notifications
        send_email_notification.delay(notification.id)
        send_sms_notification.delay(notification.id)
        
        # Mark booking as reminded
        booking.reminder_sent = True
        booking.save(update_fields=['reminder_sent'])
        
        reminders_sent += 1
    
    logger.info(f"Sent {reminders_sent} booking reminders")
    return f"Sent {reminders_sent} booking reminders"


@shared_task
def cleanup_old_notifications():
    """
    Clean up old notifications to prevent database bloat.
    Removes notifications older than 30 days.
    """
    cutoff_date = timezone.now() - timedelta(days=30)
    
    deleted_count, _ = Notification.objects.filter(
        created_at__lt=cutoff_date,
        is_read=True
    ).delete()
    
    logger.info(f"Cleaned up {deleted_count} old notifications")
    return f"Cleaned up {deleted_count} old notifications"


@shared_task
def generate_daily_reports():
    """
    Generate daily usage reports and email them to administrators.
    """
    try:
        from django.contrib.auth.models import Group
        
        # Get admin users
        admin_group = Group.objects.filter(name='Lab Administrators').first()
        if not admin_group:
            logger.warning("Lab Administrators group not found, skipping daily reports")
            return "Lab Administrators group not found"
        
        admin_users = admin_group.user_set.filter(is_active=True)
        if not admin_users.exists():
            logger.warning("No active admin users found, skipping daily reports")
            return "No active admin users found"
        
        # Generate report data
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        
        bookings_today = Booking.objects.filter(
            start_time__date=today
        ).count()
        
        bookings_yesterday = Booking.objects.filter(
            start_time__date=yesterday
        ).count()
        
        active_resources = Resource.objects.filter(is_active=True).count()
        
        report_data = {
            'date': today,
            'bookings_today': bookings_today,
            'bookings_yesterday': bookings_yesterday,
            'active_resources': active_resources,
        }
        
        # Send report to admins
        subject = f"Daily Lab Usage Report - {today}"
        message = render_to_string('emails/daily_report.html', report_data)
        
        email_config = EmailConfiguration.get_current_config()
        if email_config and email_config.enabled:
            from_email = email_config.from_email
        else:
            from_email = settings.DEFAULT_FROM_EMAIL
        
        recipient_list = [user.email for user in admin_users if user.email]
        
        send_mail(
            subject=subject,
            message=f"Daily report for {today}",
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=message,
            fail_silently=False,
        )
        
        logger.info(f"Daily report sent to {len(recipient_list)} administrators")
        return f"Daily report sent to {len(recipient_list)} administrators"
        
    except Exception as exc:
        logger.error(f"Failed to generate daily reports: {exc}")
        raise exc


@shared_task
def check_resource_maintenance():
    """
    Check for resources that need maintenance and send notifications.
    """
    try:
        # Find resources that need maintenance
        now = timezone.now()
        
        # Resources with overdue maintenance
        overdue_maintenance = MaintenanceSchedule.objects.filter(
            next_maintenance_date__lt=now,
            is_completed=False,
            resource__is_active=True
        ).select_related('resource')
        
        notifications_sent = 0
        
        for maintenance in overdue_maintenance:
            # Create notification for resource managers
            resource_managers = User.objects.filter(
                groups__name='Resource Managers',
                is_active=True
            )
            
            for manager in resource_managers:
                notification = Notification.objects.create(
                    user=manager,
                    notification_type='maintenance_due',
                    title='Maintenance Overdue',
                    message=f'Resource "{maintenance.resource.name}" has overdue maintenance. '
                           f'Last maintenance: {maintenance.last_maintenance_date}',
                    resource=maintenance.resource
                )
                
                # Send notification
                send_email_notification.delay(notification.id)
                notifications_sent += 1
        
        logger.info(f"Sent {notifications_sent} maintenance notifications")
        return f"Sent {notifications_sent} maintenance notifications"
        
    except Exception as exc:
        logger.error(f"Failed to check resource maintenance: {exc}")
        raise exc


@shared_task
def process_waiting_lists():
    """
    Process waiting lists and notify users when resources become available.
    """
    try:
        from .models import WaitingList
        
        # Get all waiting list entries for available time slots
        now = timezone.now()
        
        waiting_entries = WaitingList.objects.filter(
            is_active=True,
            desired_date__gte=now.date()
        ).select_related('user', 'resource')
        
        notifications_sent = 0
        
        for entry in waiting_entries:
            # Check if the desired time slot is now available
            conflicting_bookings = Booking.objects.filter(
                resource=entry.resource,
                start_time__date=entry.desired_date,
                status__in=['confirmed', 'pending']
            )
            
            if not conflicting_bookings.exists():
                # Slot is available, notify the user
                notification = Notification.objects.create(
                    user=entry.user,
                    notification_type='waiting_list_available',
                    title='Resource Available',
                    message=f'The resource "{entry.resource.name}" is now available '
                           f'on {entry.desired_date}. Book now!',
                    resource=entry.resource
                )
                
                # Send notification
                send_email_notification.delay(notification.id)
                send_sms_notification.delay(notification.id)
                
                notifications_sent += 1
                
                # Deactivate the waiting list entry
                entry.is_active = False
                entry.notified_at = now
                entry.save(update_fields=['is_active', 'notified_at'])
        
        logger.info(f"Processed waiting lists and sent {notifications_sent} notifications")
        return f"Processed waiting lists and sent {notifications_sent} notifications"
        
    except Exception as exc:
        logger.error(f"Failed to process waiting lists: {exc}")
        raise exc


@shared_task
def backup_database():
    """
    Create a database backup using Django's built-in management command.
    """
    try:
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        call_command('create_backup', stdout=out)
        
        result = out.getvalue()
        logger.info(f"Database backup completed: {result}")
        return f"Database backup completed: {result}"
        
    except Exception as exc:
        logger.error(f"Failed to backup database: {exc}")
        raise exc


# Task for testing Celery connectivity
@shared_task
def test_celery():
    """Test task to verify Celery is working correctly."""
    logger.info("Celery test task executed successfully")
    return f"Celery test task executed at {timezone.now()}"