# booking/signals.py
"""
Django signals for the Labitory.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile, Booking, BookingHistory, Maintenance, NotificationPreference, BackupSchedule
from .notifications import booking_notifications, maintenance_notifications


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when User is created."""
    if created:
        # Use get_or_create to prevent duplicate UserProfile creation
        profile, profile_created = UserProfile.objects.get_or_create(user=instance)
        # Create default notification preferences only if the profile was just created
        if profile_created:
            create_default_notification_preferences(instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved."""
    if hasattr(instance, 'userprofile'):
        instance.userprofile.save()


@receiver(post_save, sender=Booking)
def log_booking_changes(sender, instance, created, **kwargs):
    """Log booking creation and updates."""
    if created:
        BookingHistory.objects.create(
            booking=instance,
            user=instance.user,
            action='created',
            new_values={
                'title': instance.title,
                'start_time': instance.start_time.isoformat(),
                'end_time': instance.end_time.isoformat(),
                'status': instance.status,
            }
        )
        # Send booking creation notification
        booking_notifications.booking_created(instance)
    else:
        # Handle status changes
        try:
            old_booking = Booking.objects.get(pk=instance.pk)
            if old_booking.status != instance.status:
                if instance.status == 'confirmed':
                    booking_notifications.booking_confirmed(instance)
                elif instance.status == 'cancelled':
                    # Note: We'd need to track who cancelled it for proper notification
                    booking_notifications.booking_cancelled(instance, instance.user)
        except Booking.DoesNotExist:
            pass


@receiver(post_delete, sender=Booking)
def log_booking_deletion(sender, instance, **kwargs):
    """Log booking deletion."""
    BookingHistory.objects.create(
        booking_id=instance.id,
        user=instance.user,
        action='deleted',
        old_values={
            'title': instance.title,
            'start_time': instance.start_time.isoformat(),
            'end_time': instance.end_time.isoformat(),
            'status': instance.status,
        }
    )


@receiver(post_save, sender=Maintenance)
def handle_maintenance_changes(sender, instance, created, **kwargs):
    """Handle maintenance creation and updates."""
    if created:
        maintenance_notifications.maintenance_scheduled(instance)


def create_default_notification_preferences(user):
    """Create default notification preferences for a new user."""
    default_preferences = [
        ('booking_confirmed', 'email', True),
        ('booking_confirmed', 'in_app', True),
        ('booking_cancelled', 'email', True),
        ('booking_cancelled', 'in_app', True),
        ('booking_reminder', 'email', True),
        ('approval_request', 'email', True),
        ('approval_request', 'in_app', True),
        ('approval_decision', 'email', True),
        ('approval_decision', 'in_app', True),
        ('maintenance_alert', 'email', True),
        ('maintenance_alert', 'in_app', True),
        ('conflict_detected', 'email', True),
        ('conflict_detected', 'in_app', True),
        ('quota_warning', 'email', True),
    ]
    
    preferences_to_create = []
    for notification_type, delivery_method, is_enabled in default_preferences:
        preferences_to_create.append(
            NotificationPreference(
                user=user,
                notification_type=notification_type,
                delivery_method=delivery_method,
                is_enabled=is_enabled
            )
        )
    
    NotificationPreference.objects.bulk_create(preferences_to_create, ignore_conflicts=True)


@receiver(post_save, sender=BackupSchedule)
def backup_schedule_updated(sender, instance, created, **kwargs):
    """Update scheduler when backup schedule is created or updated."""
    try:
        from .scheduler import get_scheduler
        
        scheduler = get_scheduler()
        if scheduler.started:
            # Remove old job and add new one
            scheduler.remove_schedule_job(instance.id)
            if instance.enabled and instance.frequency != 'disabled':
                scheduler.add_schedule_job(instance)
                
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating backup schedule in scheduler: {e}")


@receiver(post_delete, sender=BackupSchedule)
def backup_schedule_deleted(sender, instance, **kwargs):
    """Remove scheduled job when backup schedule is deleted."""
    try:
        from .scheduler import get_scheduler
        
        scheduler = get_scheduler()
        if scheduler.started:
            scheduler.remove_schedule_job(instance.id)
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error removing backup schedule from scheduler: {e}")