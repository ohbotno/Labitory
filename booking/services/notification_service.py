# booking/services/notification_service.py
"""
Notification service for the Aperture Booking system.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

from ..models import Notification, NotificationPreference, Booking, Resource

logger = logging.getLogger(__name__)


class NotificationService:
    """Service class for managing all types of notifications."""
    
    def __init__(self):
        self.email_enabled = getattr(settings, 'EMAIL_ENABLED', True)
        self.sms_enabled = self._check_sms_enabled()
        self.push_enabled = getattr(settings, 'PUSH_ENABLED', True)
    
    def _check_sms_enabled(self) -> bool:
        """Check if SMS is enabled via database configuration."""
        try:
            from ..models import SMSConfiguration
            return SMSConfiguration.is_sms_enabled()
        except Exception:
            # Fallback to settings if database configuration fails
            return getattr(settings, 'SMS_ENABLED', False)
    
    def send_booking_confirmation(self, booking: Booking) -> bool:
        """Send booking confirmation notification."""
        try:
            # Create in-app notification
            notification = Notification.objects.create(
                user=booking.user,
                notification_type='booking_confirmation',
                title='Booking Confirmed',
                message=f'Your booking "{booking.title}" for {booking.resource.name} has been confirmed.',
                booking=booking
            )
            
            # Send email and SMS asynchronously using Celery
            self._schedule_async_notifications(notification.id)
            
            # Send push notification if enabled
            if self._should_send_push(booking.user, 'booking_confirmation'):
                self._send_push_notification(
                    booking.user,
                    'Booking Confirmed',
                    f'Your booking "{booking.title}" has been confirmed.'
                )
            
            logger.info(f"Booking confirmation sent for booking {booking.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending booking confirmation: {e}")
            return False
    
    def send_booking_reminder(self, booking: Booking, hours_before: int = 24) -> bool:
        """Send booking reminder notification."""
        try:
            # Create in-app notification
            notification = Notification.objects.create(
                user=booking.user,
                notification_type='booking_reminder',
                title='Booking Reminder',
                message=f'Reminder: Your booking "{booking.title}" starts in {hours_before} hours.',
                booking=booking
            )
            
            # Send email and SMS asynchronously using Celery
            self._schedule_async_notifications(notification.id)
            
            # Send push notification if enabled
            if self._should_send_push(booking.user, 'booking_reminder'):
                self._send_push_notification(
                    booking.user,
                    'Booking Reminder',
                    f'Your booking "{booking.title}" starts in {hours_before} hours.'
                )
            
            logger.info(f"Booking reminder sent for booking {booking.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending booking reminder: {e}")
            return False
    
    def send_booking_cancellation(self, booking: Booking, cancelled_by: User, reason: str = "") -> bool:
        """Send booking cancellation notification."""
        try:
            # Determine if this was self-cancelled or cancelled by admin
            if cancelled_by == booking.user:
                title = "Booking Cancelled"
                message = f'Your booking "{booking.title}" has been cancelled.'
            else:
                title = "Booking Cancelled by Admin"
                message = f'Your booking "{booking.title}" has been cancelled by an administrator.'
                if reason:
                    message += f' Reason: {reason}'
            
            # Create in-app notification
            notification = Notification.objects.create(
                user=booking.user,
                notification_type='booking_cancelled',
                title=title,
                message=message,
                booking=booking
            )
            
            # Send email if enabled
            if self._should_send_email(booking.user, 'booking_cancelled'):
                self._send_booking_email(
                    booking.user,
                    title,
                    'emails/booking_cancellation.html',
                    {
                        'booking': booking, 
                        'cancelled_by': cancelled_by, 
                        'reason': reason,
                        'self_cancelled': cancelled_by == booking.user
                    }
                )
            
            # Send SMS if enabled
            if self._should_send_sms(booking.user, 'booking_cancelled'):
                sms_message = f'Cancelled: {booking.title} at {booking.start_time.strftime("%Y-%m-%d %H:%M")}'
                if reason and cancelled_by != booking.user:
                    sms_message += f' - {reason}'
                self._send_booking_sms(booking.user, sms_message)
            
            # Send push notification
            if self._should_send_push(booking.user, 'booking_cancelled'):
                self._send_push_notification(booking.user, title, message)
            
            logger.info(f"Booking cancellation notification sent for booking {booking.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending booking cancellation notification: {e}")
            return False
    
    def send_resource_availability_notification(self, user: User, resource: Resource) -> bool:
        """Send notification when a resource becomes available."""
        try:
            # Create in-app notification
            notification = Notification.objects.create(
                user=user,
                notification_type='resource_available',
                title='Resource Available',
                message=f'The resource "{resource.name}" is now available for booking.',
                resource=resource
            )
            
            # Send email if enabled
            if self._should_send_email(user, 'resource_available'):
                self._send_booking_email(
                    user,
                    'Resource Available',
                    'emails/resource_available.html',
                    {'resource': resource}
                )
            
            # Send SMS if enabled
            if self._should_send_sms(user, 'resource_available'):
                self._send_booking_sms(
                    user,
                    f'Available: {resource.name} - book now!'
                )
            
            # Send push notification
            if self._should_send_push(user, 'resource_available'):
                self._send_push_notification(
                    user,
                    'Resource Available',
                    f'"{resource.name}" is now available for booking.'
                )
            
            logger.info(f"Resource availability notification sent to {user.username}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending resource availability notification: {e}")
            return False
    
    def send_system_maintenance_notification(self, users: List[User], message: str, scheduled_time: datetime) -> int:
        """Send system maintenance notification to multiple users."""
        successful_notifications = 0
        
        for user in users:
            try:
                # Create in-app notification
                notification = Notification.objects.create(
                    user=user,
                    notification_type='system_maintenance',
                    title='Scheduled System Maintenance',
                    message=f'System maintenance scheduled for {scheduled_time.strftime("%Y-%m-%d %H:%M")}. {message}'
                )
                
                # Send email if enabled
                if self._should_send_email(user, 'system_maintenance'):
                    self._send_booking_email(
                        user,
                        'Scheduled System Maintenance',
                        'emails/system_maintenance.html',
                        {
                            'message': message,
                            'scheduled_time': scheduled_time
                        }
                    )
                
                # Send SMS if enabled (shorter message)
                if self._should_send_sms(user, 'system_maintenance'):
                    self._send_booking_sms(
                        user,
                        f'Maintenance: {scheduled_time.strftime("%m/%d %H:%M")} - System may be unavailable'
                    )
                
                successful_notifications += 1
                
            except Exception as e:
                logger.error(f"Error sending maintenance notification to {user.username}: {e}")
        
        logger.info(f"System maintenance notifications sent to {successful_notifications} users")
        return successful_notifications
    
    def send_bulk_notification(
        self, 
        users: List[User], 
        title: str, 
        message: str, 
        notification_type: str = 'system_announcement'
    ) -> int:
        """Send bulk notification to multiple users."""
        successful_notifications = 0
        
        for user in users:
            try:
                # Create in-app notification
                notification = Notification.objects.create(
                    user=user,
                    notification_type=notification_type,
                    title=title,
                    message=message
                )
                
                # Send email if enabled
                if self._should_send_email(user, notification_type):
                    self._send_booking_email(
                        user,
                        title,
                        'emails/bulk_notification.html',
                        {'title': title, 'message': message}
                    )
                
                successful_notifications += 1
                
            except Exception as e:
                logger.error(f"Error sending bulk notification to {user.username}: {e}")
        
        logger.info(f"Bulk notifications sent to {successful_notifications} users")
        return successful_notifications
    
    def mark_notification_read(self, notification_id: int, user: User) -> bool:
        """Mark a notification as read."""
        try:
            notification = Notification.objects.get(
                id=notification_id,
                user=user
            )
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False
    
    def mark_all_notifications_read(self, user: User) -> int:
        """Mark all notifications as read for a user."""
        count = Notification.objects.filter(
            user=user,
            read_at__isnull=True
        ).update(read_at=timezone.now(), status='read')
        return count
    
    def get_user_notifications(
        self, 
        user: User, 
        unread_only: bool = False, 
        limit: Optional[int] = None
    ) -> List[Notification]:
        """Get notifications for a user."""
        queryset = Notification.objects.filter(user=user)
        
        if unread_only:
            queryset = queryset.filter(read_at__isnull=True)
        
        queryset = queryset.order_by('-created_at')
        
        if limit:
            queryset = queryset[:limit]
        
        return list(queryset)
    
    def cleanup_old_notifications(self, days_old: int = 30) -> int:
        """Clean up notifications older than specified days."""
        cutoff_date = timezone.now() - timedelta(days=days_old)
        deleted_count, _ = Notification.objects.filter(
            created_at__lt=cutoff_date
        ).delete()
        
        logger.info(f"Cleaned up {deleted_count} old notifications")
        return deleted_count
    
    # Private helper methods
    
    def _should_send_email(self, user: User, notification_type: str) -> bool:
        """Check if email should be sent for this notification type."""
        if not self.email_enabled:
            return False
        
        try:
            preference = NotificationPreference.objects.get(
                user=user,
                notification_type=notification_type
            )
            return preference.email_enabled
        except NotificationPreference.DoesNotExist:
            return True  # Default to enabled
    
    def _should_send_sms(self, user: User, notification_type: str) -> bool:
        """Check if SMS should be sent for this notification type."""
        # Check current SMS status dynamically
        if not self._check_sms_enabled():
            return False
        
        try:
            preference = NotificationPreference.objects.get(
                user=user,
                notification_type=notification_type
            )
            return preference.sms_enabled and hasattr(user, 'userprofile') and user.userprofile.phone
        except NotificationPreference.DoesNotExist:
            return False  # Default to disabled for SMS
    
    def _should_send_push(self, user: User, notification_type: str) -> bool:
        """Check if push notification should be sent."""
        if not self.push_enabled:
            return False
        
        try:
            preference = NotificationPreference.objects.get(
                user=user,
                notification_type=notification_type
            )
            return preference.push_enabled
        except NotificationPreference.DoesNotExist:
            return True  # Default to enabled
    
    def _send_booking_email(self, user: User, subject: str, template: str, context: Dict[str, Any]) -> bool:
        """Send email notification."""
        try:
            html_message = render_to_string(template, context)
            send_mail(
                subject=subject,
                message="",  # Plain text version could be generated
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            return True
        except Exception as e:
            logger.error(f"Error sending email to {user.email}: {e}")
            return False
    
    def _send_booking_sms(self, user: User, message: str) -> bool:
        """Send SMS notification."""
        try:
            # This would integrate with SMS service (e.g., Twilio)
            from .sms_service import send_sms
            return send_sms(user.userprofile.phone, message)
        except Exception as e:
            logger.error(f"Error sending SMS to {user.username}: {e}")
            return False
    
    def _send_push_notification(self, user: User, title: str, message: str) -> bool:
        """Send push notification."""
        try:
            # This would integrate with push notification service
            from .push_service import send_push_notification
            return send_push_notification(user, title, message)
        except Exception as e:
            logger.error(f"Error sending push notification to {user.username}: {e}")
            return False
    
    def _schedule_async_notifications(self, notification_id: int) -> None:
        """Schedule async email and SMS notifications using Celery tasks."""
        try:
            # Import here to avoid circular imports
            from ..tasks import send_email_notification, send_sms_notification
            
            # Schedule email task
            send_email_notification.delay(notification_id)
            
            # Schedule SMS task
            send_sms_notification.delay(notification_id)
            
            logger.debug(f"Scheduled async notifications for notification {notification_id}")
            
        except ImportError:
            # Fallback if Celery tasks are not available
            logger.warning("Celery tasks not available, notifications may be processed synchronously")
        except Exception as e:
            logger.error(f"Error scheduling async notifications for notification {notification_id}: {e}")


# Singleton instance
notification_service = NotificationService()