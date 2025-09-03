# booking/notifications.py
"""
Notification service for the Labitory.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import logging
from typing import Dict, List, Optional, Any
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Q
from .models import (
    Notification, NotificationPreference, EmailTemplate, 
    Booking, Resource, Maintenance, UserProfile, AccessRequest, TrainingRequest,
    RiskAssessment, UserRiskAssessment, TrainingCourse, UserTraining, ResourceResponsible
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for creating and sending notifications."""
    
    def __init__(self):
        self.default_preferences = {
            'booking_confirmed': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'booking_cancelled': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'booking_reminder': {'email': True, 'in_app': False, 'push': True, 'sms': False},
            'approval_request': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'approval_decision': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'maintenance_alert': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'conflict_detected': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'booking_overridden': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'quota_warning': {'email': True, 'in_app': False, 'push': False, 'sms': False},
            'waitlist_joined': {'email': False, 'in_app': True, 'push': True, 'sms': False},
            'waitlist_availability': {'email': True, 'in_app': True, 'push': True, 'sms': True},
            'waitlist_cancelled': {'email': False, 'in_app': True, 'push': False, 'sms': False},
            'access_request_submitted': {'email': True, 'in_app': True, 'push': False, 'sms': False},
            'access_request_approved': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'access_request_rejected': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'training_request_submitted': {'email': True, 'in_app': True, 'push': False, 'sms': False},
            'training_request_scheduled': {'email': True, 'in_app': True, 'push': True, 'sms': True},
            'training_request_completed': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'training_request_cancelled': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'escalation_notification': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'emergency_alert': {'email': True, 'in_app': True, 'push': True, 'sms': True},
            'safety_alert': {'email': True, 'in_app': True, 'push': True, 'sms': True},
            'evacuation_notice': {'email': True, 'in_app': True, 'push': True, 'sms': True},
            'emergency_maintenance': {'email': True, 'in_app': True, 'push': True, 'sms': True},
            # Approval Workflow Notifications
            'risk_assessment_assigned': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'risk_assessment_submitted': {'email': True, 'in_app': True, 'push': False, 'sms': False},
            'risk_assessment_approved': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'risk_assessment_rejected': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'risk_assessment_expiring': {'email': True, 'in_app': False, 'push': False, 'sms': False},
            'training_enrolled': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'training_session_scheduled': {'email': True, 'in_app': True, 'push': True, 'sms': True},
            'training_session_reminder': {'email': True, 'in_app': False, 'push': True, 'sms': True},
            'training_completed': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'training_failed': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'training_certificate_issued': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'training_expiring': {'email': True, 'in_app': False, 'push': False, 'sms': False},
            'resource_responsibility_assigned': {'email': True, 'in_app': True, 'push': True, 'sms': False},
            'compliance_check_required': {'email': True, 'in_app': True, 'push': True, 'sms': False},
        }
    
    def create_notification(
        self,
        user,
        notification_type: str,
        title: str,
        message: str,
        priority: str = 'medium',
        booking: Optional[Booking] = None,
        resource: Optional[Resource] = None,
        maintenance: Optional[Maintenance] = None,
        access_request: Optional[AccessRequest] = None,
        training_request: Optional[TrainingRequest] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Notification]:
        """Create notifications based on user preferences."""
        notifications = []
        
        # Get user preferences or use defaults
        preferences = self._get_user_preferences(user, notification_type)
        
        for delivery_method, is_enabled in preferences.items():
            if is_enabled:
                notification = Notification.objects.create(
                    user=user,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    priority=priority,
                    delivery_method=delivery_method,
                    booking=booking,
                    resource=resource,
                    maintenance=maintenance,
                    access_request=access_request,
                    training_request=training_request,
                    metadata=metadata or {}
                )
                notifications.append(notification)
        
        return notifications
    
    def _get_user_preferences(self, user, notification_type: str) -> Dict[str, bool]:
        """Get user notification preferences for a specific type."""
        preferences = {}
        
        # Query user's explicit preferences
        user_prefs = NotificationPreference.objects.filter(
            user=user,
            notification_type=notification_type,
            is_enabled=True
        )
        
        for pref in user_prefs:
            preferences[pref.delivery_method] = True
        
        # Fill in defaults for missing preferences
        defaults = self.default_preferences.get(notification_type, {})
        for method, enabled in defaults.items():
            if method not in preferences:
                preferences[method] = enabled
        
        return preferences
    
    def send_pending_notifications(self) -> int:
        """Send all pending notifications."""
        pending_notifications = Notification.objects.filter(
            Q(status='pending') &
            (Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=timezone.now()))
        ).select_related('user', 'booking', 'resource', 'maintenance')
        
        sent_count = 0
        
        for notification in pending_notifications:
            try:
                if notification.delivery_method == 'email':
                    self._send_email_notification(notification)
                elif notification.delivery_method == 'sms':
                    self._send_sms_notification(notification)
                elif notification.delivery_method == 'in_app':
                    # In-app notifications are already "sent" when created
                    notification.mark_as_sent()
                elif notification.delivery_method == 'push':
                    self._send_push_notification(notification)
                
                sent_count += 1
                logger.info(f"Sent {notification.delivery_method} notification to {notification.user.username}")
                
            except Exception as e:
                logger.error(f"Failed to send notification {notification.id}: {str(e)}")
                notification.mark_as_failed()
        
        return sent_count
    
    def _send_email_notification(self, notification: Notification):
        """Send email notification."""
        # Get email template
        template = self._get_email_template(notification.notification_type)
        
        if not template:
            # Fallback to basic email
            self._send_basic_email(notification)
            return
        
        # Build context for template
        context = self._build_email_context(notification)
        
        # Render email content
        subject = template.render_subject(context)
        html_content = template.render_html(context)
        text_content = template.render_text(context)
        
        # Send email
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[notification.user.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        notification.mark_as_sent()
    
    def _send_basic_email(self, notification: Notification):
        """Send basic email without template."""
        from django.core.mail import send_mail
        
        send_mail(
            subject=notification.title,
            message=notification.message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.user.email],
            fail_silently=False
        )
        
        notification.mark_as_sent()
    
    def _send_sms_notification(self, notification: Notification):
        """Send SMS notification using Twilio service."""
        from .sms_service import sms_service
        
        # Get user's phone number
        phone_number = sms_service.get_user_phone_number(notification.user)
        
        if not phone_number:
            logger.warning(f"No phone number found for user {notification.user.username}")
            notification.mark_as_failed("No phone number available")
            return
        
        # Format message for SMS
        sms_message = sms_service.format_notification_message(notification)
        
        # Send SMS
        success = sms_service.send_sms(phone_number, sms_message)
        
        if success:
            notification.mark_as_sent()
            logger.info(f"SMS notification sent to {notification.user.username} at {phone_number}")
        else:
            notification.mark_as_failed("SMS delivery failed")
            logger.error(f"Failed to send SMS to {notification.user.username} at {phone_number}")
    
    def _send_push_notification(self, notification: Notification):
        """Send push notification using web push service."""
        from .push_service import push_service
        
        # Format notification for push
        push_data = push_service.format_notification_for_push(notification)
        
        # Send to all user's active push subscriptions
        sent_count = push_service.send_to_user(
            user=notification.user,
            title=notification.title,
            message=notification.message,
            **push_data
        )
        
        if sent_count > 0:
            notification.mark_as_sent()
            logger.info(f"Push notification sent to {sent_count} devices for {notification.user.username}")
        else:
            notification.mark_as_failed("No active push subscriptions")
            logger.warning(f"No active push subscriptions for user {notification.user.username}")
    
    def _get_email_template(self, notification_type: str) -> Optional[EmailTemplate]:
        """Get active email template for notification type."""
        try:
            return EmailTemplate.objects.filter(
                notification_type=notification_type,
                is_active=True
            ).first()
        except Exception:
            return None
    
    def _build_email_context(self, notification: Notification) -> Dict[str, Any]:
        """Build context variables for email template rendering."""
        context = {
            'user': notification.user,
            'user_profile': getattr(notification.user, 'userprofile', None),
            'notification': notification,
            'site_name': getattr(settings, 'SITE_NAME', 'Labitory'),
            'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
        }
        
        # Add related objects
        if notification.booking:
            context['booking'] = notification.booking
            context['resource'] = notification.booking.resource
        
        if notification.resource:
            context['resource'] = notification.resource
        
        if notification.maintenance:
            context['maintenance'] = notification.maintenance
            context['resource'] = notification.maintenance.resource
        
        if notification.access_request:
            context['access_request'] = notification.access_request
            context['resource'] = notification.access_request.resource
        
        if notification.training_request:
            context['training_request'] = notification.training_request
            context['resource'] = notification.training_request.resource
        
        # Add metadata
        context.update(notification.metadata)
        
        return context
    
    def get_user_notifications(self, user, limit: int = 20, unread_only: bool = False) -> List[Notification]:
        """Get notifications for a user."""
        queryset = Notification.objects.filter(
            user=user,
            delivery_method='in_app'
        ).select_related('booking', 'resource', 'maintenance')
        
        if unread_only:
            queryset = queryset.filter(status__in=['pending', 'sent'])
        
        return list(queryset[:limit])
    
    def mark_notifications_as_read(self, user, notification_ids: List[int]) -> int:
        """Mark multiple notifications as read."""
        updated = Notification.objects.filter(
            user=user,
            id__in=notification_ids,
            delivery_method='in_app',
            status__in=['pending', 'sent']
        ).update(
            status='read',
            read_at=timezone.now(),
            updated_at=timezone.now()
        )
        
        return updated
    
    def send_escalation_notifications(self):
        """Send escalation notifications for overdue requests."""
        from .models import AccessRequest, TrainingRequest
        from datetime import timedelta
        
        # Define escalation timeframes
        now = timezone.now()
        escalation_1_cutoff = now - timedelta(days=3)  # 3 days old
        escalation_2_cutoff = now - timedelta(days=7)  # 7 days old
        escalation_3_cutoff = now - timedelta(days=14) # 14 days old
        
        escalated_count = 0
        
        try:
            # Check overdue access requests
            overdue_access_requests = AccessRequest.objects.filter(
                status='pending',
                created_at__lte=escalation_1_cutoff
            )
            
            for access_request in overdue_access_requests:
                days_old = (now - access_request.created_at).days
                
                # Determine escalation level
                if days_old >= 14:
                    escalation_level = 3
                    priority = 'urgent'
                elif days_old >= 7:
                    escalation_level = 2
                    priority = 'high'
                else:
                    escalation_level = 1
                    priority = 'medium'
                
                # Check if we already sent this escalation
                existing_escalation = Notification.objects.filter(
                    access_request=access_request,
                    notification_type='escalation_notification',
                    metadata__escalation_level=escalation_level
                ).exists()
                
                if not existing_escalation:
                    self._send_access_escalation_notification(
                        access_request, 
                        escalation_level, 
                        priority, 
                        days_old
                    )
                    escalated_count += 1
            
            # Check overdue training requests
            overdue_training_requests = TrainingRequest.objects.filter(
                status='pending',
                created_at__lte=escalation_1_cutoff
            )
            
            for training_request in overdue_training_requests:
                days_old = (now - training_request.created_at).days
                
                # Determine escalation level
                if days_old >= 14:
                    escalation_level = 3
                    priority = 'urgent'
                elif days_old >= 7:
                    escalation_level = 2
                    priority = 'high'
                else:
                    escalation_level = 1
                    priority = 'medium'
                
                # Check if we already sent this escalation
                existing_escalation = Notification.objects.filter(
                    training_request=training_request,
                    notification_type='escalation_notification',
                    metadata__escalation_level=escalation_level
                ).exists()
                
                if not existing_escalation:
                    self._send_training_escalation_notification(
                        training_request, 
                        escalation_level, 
                        priority, 
                        days_old
                    )
                    escalated_count += 1
                    
            return escalated_count
                    
        except Exception as e:
            logger.error(f"Error sending escalation notifications: {e}")
            return 0
    
    def _send_access_escalation_notification(self, access_request, escalation_level, priority, days_old):
        """Send escalation notification for access request."""
        escalation_messages = {
            1: f"Access request for {access_request.resource.name} has been pending for {days_old} days.",
            2: f"REMINDER: Access request for {access_request.resource.name} has been pending for {days_old} days.",
            3: f"URGENT: Access request for {access_request.resource.name} has been pending for {days_old} days and requires immediate attention."
        }
        
        # Notify lab managers
        lab_managers = UserProfile.objects.filter(role='lab_manager')
        for manager in lab_managers:
            self.create_notification(
                user=manager.user,
                notification_type='escalation_notification',
                title=f"Overdue Access Request: {access_request.resource.name}",
                message=escalation_messages[escalation_level],
                priority=priority,
                resource=access_request.resource,
                access_request=access_request,
                metadata={
                    'escalation_level': escalation_level,
                    'days_old': days_old,
                    'request_type': 'access_request'
                }
            )
    
    def _send_training_escalation_notification(self, training_request, escalation_level, priority, days_old):
        """Send escalation notification for training request."""
        escalation_messages = {
            1: f"Training request for {training_request.resource.name} has been pending for {days_old} days.",
            2: f"REMINDER: Training request for {training_request.resource.name} has been pending for {days_old} days.",
            3: f"URGENT: Training request for {training_request.resource.name} has been pending for {days_old} days and requires immediate attention."
        }
        
        # Notify lab managers
        lab_managers = UserProfile.objects.filter(role='lab_manager')
        for manager in lab_managers:
            self.create_notification(
                user=manager.user,
                notification_type='escalation_notification',
                title=f"Overdue Training Request: {training_request.resource.name}",
                message=escalation_messages[escalation_level],
                priority=priority,
                resource=training_request.resource,
                training_request=training_request,
                metadata={
                    'escalation_level': escalation_level,
                    'days_old': days_old,
                    'request_type': 'training_request'
                }
            )


class BookingNotifications:
    """Helper class for booking-specific notifications."""
    
    def __init__(self):
        self.service = NotificationService()
    
    def booking_created(self, booking: Booking):
        """Send notification when booking is created."""
        if booking.status == 'confirmed':
            self.booking_confirmed(booking)
        else:
            # Notify managers about approval request
            self._notify_approvers(booking)
    
    def booking_confirmed(self, booking: Booking):
        """Send notification when booking is confirmed."""
        self.service.create_notification(
            user=booking.user,
            notification_type='booking_confirmed',
            title=f'Booking Confirmed: {booking.resource.name}',
            message=f'Your booking "{booking.title}" has been confirmed for {booking.start_time.strftime("%B %d, %Y at %I:%M %p")}.',
            priority='medium',
            booking=booking,
            metadata={
                'booking_id': booking.id,
                'resource_name': booking.resource.name,
                'start_time': booking.start_time.isoformat(),
            }
        )
    
    def booking_cancelled(self, booking: Booking, cancelled_by):
        """Send notification when booking is cancelled."""
        if cancelled_by != booking.user:
            # Notify user if someone else cancelled their booking
            self.service.create_notification(
                user=booking.user,
                notification_type='booking_cancelled',
                title=f'Booking Cancelled: {booking.resource.name}',
                message=f'Your booking "{booking.title}" has been cancelled by {cancelled_by.get_full_name()}.',
                priority='high',
                booking=booking,
                metadata={
                    'booking_id': booking.id,
                    'cancelled_by': cancelled_by.get_full_name(),
                }
            )
    
    def booking_reminder(self, booking: Booking, hours_ahead: int = 24):
        """Send booking reminder notification."""
        self.service.create_notification(
            user=booking.user,
            notification_type='booking_reminder',
            title=f'Upcoming Booking: {booking.resource.name}',
            message=f'Reminder: You have a booking "{booking.title}" in {hours_ahead} hours.',
            priority='low',
            booking=booking,
            metadata={
                'booking_id': booking.id,
                'hours_ahead': hours_ahead,
            }
        )
    
    def conflict_detected(self, booking: Booking, conflicting_bookings: List[Booking]):
        """Send notification when booking conflicts are detected."""
        conflict_details = [
            f"{b.title} ({b.start_time.strftime('%m/%d %I:%M %p')} - {b.end_time.strftime('%I:%M %p')})"
            for b in conflicting_bookings
        ]
        
        self.service.create_notification(
            user=booking.user,
            notification_type='conflict_detected',
            title=f'Booking Conflict Detected: {booking.resource.name}',
            message=f'Your booking "{booking.title}" conflicts with: {", ".join(conflict_details)}',
            priority='high',
            booking=booking,
            metadata={
                'booking_id': booking.id,
                'conflicting_booking_ids': [b.id for b in conflicting_bookings],
            }
        )
    
    def booking_overridden(self, original_booking: Booking, overriding_booking: Booking, override_message: str = ''):
        """Send notification when a booking is overridden by a privileged user."""
        overrider_name = f"{overriding_booking.user.first_name} {overriding_booking.user.last_name}".strip()
        if not overrider_name:
            overrider_name = overriding_booking.user.username
        
        # Get the overrider's role for context
        overrider_role = "Administrator"
        try:
            profile = overriding_booking.user.userprofile
            role_display = {
                'lecturer': 'Lecturer',
                'technician': 'Technician',
                'lab_manager': 'Lab Manager',
                'sysadmin': 'System Administrator'
            }
            overrider_role = role_display.get(profile.role, 'Administrator')
        except:
            pass
        
        # Construct notification message
        message_parts = [
            f'Your booking "{original_booking.title}" for {original_booking.resource.name}',
            f'({original_booking.start_time.strftime("%m/%d %I:%M %p")} - {original_booking.end_time.strftime("%I:%M %p")})',
            f'has been overridden by {overrider_name} ({overrider_role}).'
        ]
        
        if override_message.strip():
            message_parts.append(f'\n\nMessage from {overrider_name}: {override_message.strip()}')
        
        # Cancel the original booking
        original_booking.status = 'cancelled'
        original_booking.save()
        
        # Send notification to original booking holder
        self.service.create_notification(
            user=original_booking.user,
            notification_type='booking_overridden',
            title=f'Booking Override: {original_booking.resource.name}',
            message=''.join(message_parts),
            priority='high',
            booking=original_booking,
            metadata={
                'original_booking_id': original_booking.id,
                'overriding_booking_id': overriding_booking.id,
                'overrider_id': overriding_booking.user.id,
                'overrider_name': overrider_name,
                'overrider_role': overrider_role,
                'override_message': override_message,
                'resource_id': original_booking.resource.id,
            }
        )
        
        # Log the override action
        logger.info(
            f"Booking override: {overrider_name} ({overrider_role}) overrode booking {original_booking.id} "
            f"by {original_booking.user.username} for {original_booking.resource.name}"
        )
    
    def _notify_approvers(self, booking: Booking):
        """Notify managers about approval requests."""
        # Get lab managers and system admins
        approvers = UserProfile.objects.filter(
            role__in=['lab_manager', 'sysadmin']
        ).select_related('user')
        
        for approver_profile in approvers:
            self.service.create_notification(
                user=approver_profile.user,
                notification_type='approval_request',
                title=f'Approval Required: {booking.resource.name}',
                message=f'New booking "{booking.title}" by {booking.user.get_full_name()} requires approval.',
                priority='medium',
                booking=booking,
                metadata={
                    'booking_id': booking.id,
                    'requester': booking.user.get_full_name(),
                }
            )


class MaintenanceNotifications:
    """Helper class for maintenance-specific notifications."""
    
    def __init__(self):
        self.service = NotificationService()
    
    def maintenance_scheduled(self, maintenance: Maintenance):
        """Send notification when maintenance is scheduled."""
        # Notify users with upcoming bookings for this resource
        affected_bookings = Booking.objects.filter(
            resource=maintenance.resource,
            start_time__gte=maintenance.start_time - timezone.timedelta(days=1),
            start_time__lte=maintenance.end_time + timezone.timedelta(days=1),
            status__in=['confirmed', 'pending']
        ).select_related('user')
        
        affected_users = set(booking.user for booking in affected_bookings)
        
        for user in affected_users:
            self.service.create_notification(
                user=user,
                notification_type='maintenance_alert',
                title=f'Maintenance Scheduled: {maintenance.resource.name}',
                message=f'Maintenance is scheduled for {maintenance.resource.name} from {maintenance.start_time.strftime("%B %d")} to {maintenance.end_time.strftime("%B %d")}. Your bookings may be affected.',
                priority='high',
                maintenance=maintenance,
                metadata={
                    'maintenance_id': maintenance.id,
                    'resource_name': maintenance.resource.name,
                }
            )


class AccessRequestNotifications:
    """Helper class for access request notifications."""
    
    def __init__(self):
        self.service = NotificationService()
    
    def access_request_submitted(self, access_request: AccessRequest):
        """Send notification when access request is submitted."""
        # Notify the user who submitted the request
        self.service.create_notification(
            user=access_request.user,
            notification_type='access_request_submitted',
            title=f'Access Request Submitted: {access_request.resource.name}',
            message=f'Your access request for {access_request.resource.name} has been submitted and is under review.',
            priority='medium',
            resource=access_request.resource,
            access_request=access_request,
            metadata={
                'access_request_id': access_request.id,
                'resource_name': access_request.resource.name,
            }
        )
        
        # Notify lab managers
        lab_managers = UserProfile.objects.filter(role='lab_manager').select_related('user')
        for manager_profile in lab_managers:
            self.service.create_notification(
                user=manager_profile.user,
                notification_type='access_request_submitted',
                title=f'New Access Request: {access_request.resource.name}',
                message=f'{access_request.user.get_full_name()} has requested access to {access_request.resource.name}.',
                priority='medium',
                resource=access_request.resource,
                access_request=access_request,
                metadata={
                    'access_request_id': access_request.id,
                    'requester': access_request.user.get_full_name(),
                    'requester_email': access_request.user.email,
                }
            )
    
    def access_request_approved(self, access_request: AccessRequest, approved_by):
        """Send notification when access request is approved."""
        self.service.create_notification(
            user=access_request.user,
            notification_type='access_request_approved',
            title=f'Access Granted: {access_request.resource.name}',
            message=f'Your access request for {access_request.resource.name} has been approved by {approved_by.get_full_name()}. You can now book this resource.',
            priority='high',
            resource=access_request.resource,
            access_request=access_request,
            metadata={
                'access_request_id': access_request.id,
                'approved_by': approved_by.get_full_name(),
                'resource_name': access_request.resource.name,
            }
        )
    
    def access_request_rejected(self, access_request: AccessRequest, rejected_by, reason=None):
        """Send notification when access request is rejected."""
        message = f'Your access request for {access_request.resource.name} has been declined by {rejected_by.get_full_name()}.'
        if reason:
            message += f' Reason: {reason}'
        message += ' Please contact the lab manager for more information.'
        
        self.service.create_notification(
            user=access_request.user,
            notification_type='access_request_rejected',
            title=f'Access Request Declined: {access_request.resource.name}',
            message=message,
            priority='high',
            resource=access_request.resource,
            access_request=access_request,
            metadata={
                'access_request_id': access_request.id,
                'rejected_by': rejected_by.get_full_name(),
                'reason': reason or '',
            }
        )


class TrainingRequestNotifications:
    """Helper class for training request notifications."""
    
    def __init__(self):
        self.service = NotificationService()
    
    def training_request_submitted(self, training_request: TrainingRequest):
        """Send notification when training request is submitted."""
        # Notify the user who submitted the request
        self.service.create_notification(
            user=training_request.user,
            notification_type='training_request_submitted',
            title=f'Training Request Submitted: {training_request.resource.name}',
            message=f'Your training request for {training_request.resource.name} has been submitted. You will be contacted with training details.',
            priority='medium',
            resource=training_request.resource,
            training_request=training_request,
            metadata={
                'training_request_id': training_request.id,
                'resource_name': training_request.resource.name,
            }
        )
        
        # Notify lab managers
        lab_managers = UserProfile.objects.filter(role='lab_manager').select_related('user')
        for manager_profile in lab_managers:
            self.service.create_notification(
                user=manager_profile.user,
                notification_type='training_request_submitted',
                title=f'New Training Request: {training_request.resource.name}',
                message=f'{training_request.user.get_full_name()} has requested training for {training_request.resource.name}.',
                priority='medium',
                resource=training_request.resource,
                training_request=training_request,
                metadata={
                    'training_request_id': training_request.id,
                    'requester': training_request.user.get_full_name(),
                    'requester_email': training_request.user.email,
                }
            )
    
    def training_request_scheduled(self, training_request: TrainingRequest, scheduled_date=None):
        """Send notification when training is scheduled."""
        message = f'Training for {training_request.resource.name} has been scheduled.'
        if scheduled_date:
            message += f' Training date: {scheduled_date.strftime("%B %d, %Y")}.'
        message += ' Check your email for detailed instructions.'
        
        self.service.create_notification(
            user=training_request.user,
            notification_type='training_request_scheduled',
            title=f'Training Scheduled: {training_request.resource.name}',
            message=message,
            priority='high',
            resource=training_request.resource,
            training_request=training_request,
            metadata={
                'training_request_id': training_request.id,
                'scheduled_date': scheduled_date.isoformat() if scheduled_date else None,
            }
        )
    
    def training_request_completed(self, training_request: TrainingRequest):
        """Send notification when training is completed."""
        self.service.create_notification(
            user=training_request.user,
            notification_type='training_request_completed',
            title=f'Training Completed: {training_request.resource.name}',
            message=f'You have successfully completed training for {training_request.resource.name}. You can now request access to this resource.',
            priority='high',
            resource=training_request.resource,
            training_request=training_request,
            metadata={
                'training_request_id': training_request.id,
                'resource_name': training_request.resource.name,
            }
        )
    
    def training_request_cancelled(self, training_request: TrainingRequest, cancelled_by, reason=None):
        """Send notification when training is cancelled."""
        message = f'Training for {training_request.resource.name} has been cancelled by {cancelled_by.get_full_name()}.'
        if reason:
            message += f' Reason: {reason}'
        
        self.service.create_notification(
            user=training_request.user,
            notification_type='training_request_cancelled',
            title=f'Training Cancelled: {training_request.resource.name}',
            message=message,
            priority='medium',
            resource=training_request.resource,
            training_request=training_request,
            metadata={
                'training_request_id': training_request.id,
                'cancelled_by': cancelled_by.get_full_name(),
                'reason': reason or '',
            }
        )


class ApprovalWorkflowNotifications:
    """Notifications for approval workflow events."""
    
    def __init__(self):
        self.service = NotificationService()
    
    # Risk Assessment Notifications
    def risk_assessment_assigned(self, user_assessment: UserRiskAssessment):
        """Send notification when risk assessment is assigned to user."""
        self.service.create_notification(
            user=user_assessment.user,
            notification_type='risk_assessment_assigned',
            title=f'Risk Assessment Required: {user_assessment.risk_assessment.title}',
            message=f'You have been assigned a {user_assessment.risk_assessment.get_assessment_type_display().lower()} risk assessment for {user_assessment.risk_assessment.resource.name}.',
            priority='medium',
            resource=user_assessment.risk_assessment.resource,
            metadata={
                'risk_assessment_id': user_assessment.risk_assessment.id,
                'user_assessment_id': user_assessment.id,
                'resource_name': user_assessment.risk_assessment.resource.name,
                'assessment_type': user_assessment.risk_assessment.assessment_type,
            }
        )
    
    def risk_assessment_submitted(self, user_assessment: UserRiskAssessment):
        """Send notification when risk assessment is submitted for review."""
        # Notify responsible persons
        responsible_persons = ResourceResponsible.objects.filter(
            resource=user_assessment.risk_assessment.resource,
            can_conduct_assessments=True,
            is_active=True
        )
        
        for responsible in responsible_persons:
            self.service.create_notification(
                user=responsible.user,
                notification_type='risk_assessment_submitted',
                title=f'Risk Assessment for Review: {user_assessment.user.get_full_name()}',
                message=f'{user_assessment.user.get_full_name()} has submitted a {user_assessment.risk_assessment.get_assessment_type_display().lower()} risk assessment for {user_assessment.risk_assessment.resource.name}.',
                priority='medium',
                resource=user_assessment.risk_assessment.resource,
                metadata={
                    'risk_assessment_id': user_assessment.risk_assessment.id,
                    'user_assessment_id': user_assessment.id,
                    'submitter_name': user_assessment.user.get_full_name(),
                }
            )
    
    def risk_assessment_approved(self, user_assessment: UserRiskAssessment):
        """Send notification when risk assessment is approved."""
        self.service.create_notification(
            user=user_assessment.user,
            notification_type='risk_assessment_approved',
            title=f'Risk Assessment Approved: {user_assessment.risk_assessment.title}',
            message=f'Your {user_assessment.risk_assessment.get_assessment_type_display().lower()} risk assessment for {user_assessment.risk_assessment.resource.name} has been approved.',
            priority='high',
            resource=user_assessment.risk_assessment.resource,
            metadata={
                'risk_assessment_id': user_assessment.risk_assessment.id,
                'user_assessment_id': user_assessment.id,
                'approved_by': user_assessment.reviewed_by.get_full_name() if user_assessment.reviewed_by else 'System',
            }
        )
    
    def risk_assessment_rejected(self, user_assessment: UserRiskAssessment, reason=None):
        """Send notification when risk assessment is rejected."""
        message = f'Your {user_assessment.risk_assessment.get_assessment_type_display().lower()} risk assessment for {user_assessment.risk_assessment.resource.name} has been rejected.'
        if reason:
            message += f' Reason: {reason}'
        
        self.service.create_notification(
            user=user_assessment.user,
            notification_type='risk_assessment_rejected',
            title=f'Risk Assessment Rejected: {user_assessment.risk_assessment.title}',
            message=message,
            priority='high',
            resource=user_assessment.risk_assessment.resource,
            metadata={
                'risk_assessment_id': user_assessment.risk_assessment.id,
                'user_assessment_id': user_assessment.id,
                'rejected_by': user_assessment.reviewed_by.get_full_name() if user_assessment.reviewed_by else 'System',
                'reason': reason or '',
            }
        )
    
    def risk_assessment_expiring(self, user_assessment: UserRiskAssessment, days_until_expiry: int):
        """Send notification when risk assessment is expiring."""
        self.service.create_notification(
            user=user_assessment.user,
            notification_type='risk_assessment_expiring',
            title=f'Risk Assessment Expiring: {user_assessment.risk_assessment.title}',
            message=f'Your {user_assessment.risk_assessment.get_assessment_type_display().lower()} risk assessment for {user_assessment.risk_assessment.resource.name} expires in {days_until_expiry} days.',
            priority='low',
            resource=user_assessment.risk_assessment.resource,
            metadata={
                'risk_assessment_id': user_assessment.risk_assessment.id,
                'user_assessment_id': user_assessment.id,
                'days_until_expiry': days_until_expiry,
                'expires_at': user_assessment.expires_at.isoformat() if user_assessment.expires_at else None,
            }
        )
    
    # Training Notifications
    def training_enrolled(self, user_training: UserTraining):
        """Send notification when user enrolls in training."""
        self.service.create_notification(
            user=user_training.user,
            notification_type='training_enrolled',
            title=f'Training Enrolled: {user_training.training_course.title}',
            message=f'You have successfully enrolled in {user_training.training_course.title} ({user_training.training_course.code}).',
            priority='medium',
            metadata={
                'training_course_id': user_training.training_course.id,
                'user_training_id': user_training.id,
                'course_code': user_training.training_course.code,
            }
        )
    
    def training_session_scheduled(self, user_training: UserTraining):
        """Send notification when training session is scheduled."""
        self.service.create_notification(
            user=user_training.user,
            notification_type='training_session_scheduled',
            title=f'Training Session Scheduled: {user_training.training_course.title}',
            message=f'Your training session for {user_training.training_course.title} has been scheduled for {user_training.session_date.strftime("%B %d, %Y at %I:%M %p")}.',
            priority='high',
            metadata={
                'training_course_id': user_training.training_course.id,
                'user_training_id': user_training.id,
                'session_date': user_training.session_date.isoformat() if user_training.session_date else None,
                'session_location': user_training.session_location or '',
                'instructor': user_training.instructor.get_full_name() if user_training.instructor else '',
            }
        )
    
    def training_session_reminder(self, user_training: UserTraining, hours_ahead: int = 24):
        """Send training session reminder notification."""
        self.service.create_notification(
            user=user_training.user,
            notification_type='training_session_reminder',
            title=f'Training Reminder: {user_training.training_course.title}',
            message=f'Reminder: Your training session for {user_training.training_course.title} starts in {hours_ahead} hours.',
            priority='medium',
            metadata={
                'training_course_id': user_training.training_course.id,
                'user_training_id': user_training.id,
                'hours_ahead': hours_ahead,
                'session_date': user_training.session_date.isoformat() if user_training.session_date else None,
            }
        )
    
    def training_completed(self, user_training: UserTraining):
        """Send notification when training is completed."""
        self.service.create_notification(
            user=user_training.user,
            notification_type='training_completed',
            title=f'Training Completed: {user_training.training_course.title}',
            message=f'Congratulations! You have successfully completed {user_training.training_course.title}.',
            priority='high',
            metadata={
                'training_course_id': user_training.training_course.id,
                'user_training_id': user_training.id,
                'completion_date': user_training.completed_at.isoformat() if user_training.completed_at else None,
                'overall_score': str(user_training.overall_score) if user_training.overall_score else '',
                'passed': user_training.passed,
            }
        )
    
    def training_failed(self, user_training: UserTraining):
        """Send notification when training is failed."""
        self.service.create_notification(
            user=user_training.user,
            notification_type='training_failed',
            title=f'Training Not Passed: {user_training.training_course.title}',
            message=f'Unfortunately, you did not pass {user_training.training_course.title}. Please contact your instructor for next steps.',
            priority='high',
            metadata={
                'training_course_id': user_training.training_course.id,
                'user_training_id': user_training.id,
                'overall_score': str(user_training.overall_score) if user_training.overall_score else '',
                'pass_mark': str(user_training.training_course.pass_mark_percentage),
            }
        )
    
    def training_certificate_issued(self, user_training: UserTraining):
        """Send notification when training certificate is issued."""
        self.service.create_notification(
            user=user_training.user,
            notification_type='training_certificate_issued',
            title=f'Certificate Issued: {user_training.training_course.title}',
            message=f'Your certificate for {user_training.training_course.title} has been issued. Certificate number: {user_training.certificate_number}',
            priority='medium',
            metadata={
                'training_course_id': user_training.training_course.id,
                'user_training_id': user_training.id,
                'certificate_number': user_training.certificate_number or '',
                'issued_at': user_training.certificate_issued_at.isoformat() if user_training.certificate_issued_at else None,
            }
        )
    
    def training_expiring(self, user_training: UserTraining, days_until_expiry: int):
        """Send notification when training is expiring."""
        self.service.create_notification(
            user=user_training.user,
            notification_type='training_expiring',
            title=f'Training Expiring: {user_training.training_course.title}',
            message=f'Your certification for {user_training.training_course.title} expires in {days_until_expiry} days. Please schedule renewal training.',
            priority='low',
            metadata={
                'training_course_id': user_training.training_course.id,
                'user_training_id': user_training.id,
                'days_until_expiry': days_until_expiry,
                'expires_at': user_training.expires_at.isoformat() if user_training.expires_at else None,
            }
        )
    
    # Resource Responsibility Notifications
    def resource_responsibility_assigned(self, responsible: ResourceResponsible):
        """Send notification when resource responsibility is assigned."""
        self.service.create_notification(
            user=responsible.user,
            notification_type='resource_responsibility_assigned',
            title=f'Resource Responsibility Assigned: {responsible.resource.name}',
            message=f'You have been assigned as {responsible.get_role_type_display().lower()} for {responsible.resource.name}.',
            priority='high',
            resource=responsible.resource,
            metadata={
                'resource_responsible_id': responsible.id,
                'resource_name': responsible.resource.name,
                'role_type': responsible.role_type,
                'assigned_by': responsible.assigned_by.get_full_name(),
            }
        )
    
    def compliance_check_required(self, access_request: AccessRequest):
        """Send notification when compliance check is required."""
        compliance = access_request.check_user_compliance()
        
        if not compliance['training_complete'] or not compliance['risk_assessments_complete']:
            required_actions = []
            if not compliance['training_complete']:
                required_actions.extend([f"Complete training: {t.title}" for t in compliance['missing_training']])
            if not compliance['risk_assessments_complete']:
                required_actions.extend([f"Complete assessment: {a.title}" for a in compliance['missing_assessments']])
            
            self.service.create_notification(
                user=access_request.user,
                notification_type='compliance_check_required',
                title=f'Compliance Required: {access_request.resource.name}',
                message=f'To access {access_request.resource.name}, you must complete: {", ".join(required_actions)}',
                priority='high',
                resource=access_request.resource,
                metadata={
                    'access_request_id': access_request.id,
                    'missing_training': [t.id for t in compliance['missing_training']],
                    'missing_assessments': [a.id for a in compliance['missing_assessments']],
                }
            )


# Global service instances
notification_service = NotificationService()
booking_notifications = BookingNotifications()
maintenance_notifications = MaintenanceNotifications()
access_request_notifications = AccessRequestNotifications()
training_request_notifications = TrainingRequestNotifications()
approval_workflow_notifications = ApprovalWorkflowNotifications()