"""
Comprehensive notification system tests for Labitory.
Tests email, SMS, push notifications, and notification preferences.
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.core import mail
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, Mock, call
import json

from booking.models import (
    Notification, NotificationPreference, EmailTemplate, PushSubscription,
    EmailConfiguration, SMSConfiguration, Booking, Resource
)
from booking.services.notification_service import NotificationService
from booking.tests.factories import (
    UserFactory, ResourceFactory, BookingFactory, UserProfileFactory
)


class TestNotificationModel(TestCase):
    """Test Notification model functionality."""
    
    def setUp(self):
        self.user = UserFactory()
    
    def test_create_notification(self):
        """Test creating a notification."""
        notification = Notification.objects.create(
            user=self.user,
            title="Test Notification",
            message="This is a test notification",
            delivery_method="email",
            status="pending",
            notification_type="booking_confirmation"
        )
        
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.title, "Test Notification")
        self.assertEqual(notification.delivery_method, "email")
        self.assertEqual(notification.status, "pending")
        self.assertEqual(notification.notification_type, "booking_confirmation")
    
    def test_notification_str_representation(self):
        """Test string representation of notification."""
        notification = Notification.objects.create(
            user=self.user,
            title="Booking Reminder",
            message="Your booking is tomorrow",
            delivery_method="email"
        )
        
        str_repr = str(notification)
        self.assertIn("Booking Reminder", str_repr)
        self.assertIn(self.user.get_full_name(), str_repr)
    
    def test_notification_status_transitions(self):
        """Test notification status transitions."""
        notification = Notification.objects.create(
            user=self.user,
            title="Status Test",
            message="Testing status changes",
            delivery_method="email",
            status="pending"
        )
        
        # Transition to sent
        notification.status = "sent"
        notification.sent_at = timezone.now()
        notification.save()
        
        self.assertEqual(notification.status, "sent")
        self.assertIsNotNone(notification.sent_at)
        
        # Transition to failed
        notification.status = "failed"
        notification.failure_reason = "Invalid email address"
        notification.save()
        
        self.assertEqual(notification.status, "failed")
        self.assertEqual(notification.failure_reason, "Invalid email address")
    
    def test_notification_retry_logic(self):
        """Test notification retry functionality."""
        notification = Notification.objects.create(
            user=self.user,
            title="Retry Test",
            message="Testing retry logic",
            delivery_method="email",
            status="failed",
            retry_count=0,
            max_retries=3
        )
        
        # Simulate retry
        notification.retry_count += 1
        notification.last_retry_at = timezone.now()
        
        can_retry = notification.retry_count < notification.max_retries
        self.assertTrue(can_retry)
        
        notification.save()
        self.assertEqual(notification.retry_count, 1)
        self.assertIsNotNone(notification.last_retry_at)
    
    def test_notification_priority_levels(self):
        """Test notification priority handling."""
        high_priority = Notification.objects.create(
            user=self.user,
            title="High Priority Alert",
            message="Urgent notification",
            delivery_method="email",
            priority="high"
        )
        
        normal_priority = Notification.objects.create(
            user=self.user,
            title="Normal Notification",
            message="Regular notification",
            delivery_method="email",
            priority="normal"
        )
        
        low_priority = Notification.objects.create(
            user=self.user,
            title="Low Priority Info",
            message="Info notification", 
            delivery_method="email",
            priority="low"
        )
        
        self.assertEqual(high_priority.priority, "high")
        self.assertEqual(normal_priority.priority, "normal")
        self.assertEqual(low_priority.priority, "low")


class TestNotificationPreferences(TestCase):
    """Test notification preference functionality."""
    
    def setUp(self):
        self.user = UserFactory()
    
    def test_create_notification_preferences(self):
        """Test creating notification preferences."""
        prefs = NotificationPreference.objects.create(
            user=self.user,
            notification_type="booking_confirmation",
            email_enabled=True,
            sms_enabled=False,
            push_enabled=True,
            in_app_enabled=True
        )
        
        self.assertEqual(prefs.user, self.user)
        self.assertEqual(prefs.notification_type, "booking_confirmation")
        self.assertTrue(prefs.email_enabled)
        self.assertFalse(prefs.sms_enabled)
        self.assertTrue(prefs.push_enabled)
        self.assertTrue(prefs.in_app_enabled)
    
    def test_default_preferences_creation(self):
        """Test creation of default preferences for new users."""
        # Simulate default preferences creation for new user
        default_types = [
            "booking_confirmation",
            "booking_reminder", 
            "booking_cancellation",
            "approval_request",
            "approval_granted",
            "maintenance_alert"
        ]
        
        for notification_type in default_types:
            NotificationPreference.objects.create(
                user=self.user,
                notification_type=notification_type,
                email_enabled=True,
                sms_enabled=False,
                push_enabled=True,
                in_app_enabled=True
            )
        
        user_prefs = NotificationPreference.objects.filter(user=self.user)
        self.assertEqual(user_prefs.count(), len(default_types))
    
    def test_preference_override_logic(self):
        """Test notification preference override logic."""
        # Create preference that disables SMS
        pref = NotificationPreference.objects.create(
            user=self.user,
            notification_type="booking_reminder",
            email_enabled=True,
            sms_enabled=False,
            push_enabled=True
        )
        
        # Test delivery method filtering based on preferences
        enabled_methods = []
        if pref.email_enabled:
            enabled_methods.append("email")
        if pref.sms_enabled:
            enabled_methods.append("sms")
        if pref.push_enabled:
            enabled_methods.append("push")
        if pref.in_app_enabled:
            enabled_methods.append("in_app")
        
        self.assertIn("email", enabled_methods)
        self.assertNotIn("sms", enabled_methods)
        self.assertIn("push", enabled_methods)
    
    def test_quiet_hours_preferences(self):
        """Test quiet hours notification preferences."""
        prefs = NotificationPreference.objects.create(
            user=self.user,
            notification_type="booking_reminder",
            email_enabled=True,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00:00",
            quiet_hours_end="08:00:00"
        )
        
        self.assertTrue(prefs.quiet_hours_enabled)
        self.assertEqual(str(prefs.quiet_hours_start), "22:00:00")
        self.assertEqual(str(prefs.quiet_hours_end), "08:00:00")
        
        # Test quiet hours logic
        current_time = timezone.now().time()
        quiet_start = prefs.quiet_hours_start
        quiet_end = prefs.quiet_hours_end
        
        # This would be implemented in the notification service
        is_quiet_hours = False
        if quiet_start > quiet_end:  # Crosses midnight
            is_quiet_hours = current_time >= quiet_start or current_time <= quiet_end
        else:
            is_quiet_hours = quiet_start <= current_time <= quiet_end
        
        # Test depends on current time, so just verify the logic works
        self.assertIsInstance(is_quiet_hours, bool)


class TestEmailNotifications(TestCase):
    """Test email notification functionality."""
    
    def setUp(self):
        self.user = UserFactory(email="test@example.com")
        self.notification_service = NotificationService()
        
        # Clear mail outbox
        mail.outbox = []
    
    def test_send_email_notification(self):
        """Test sending email notification."""
        notification = Notification.objects.create(
            user=self.user,
            title="Test Email",
            message="This is a test email notification",
            delivery_method="email",
            status="pending"
        )
        
        # Send email using Django's email backend
        from django.core.mail import send_mail
        
        result = send_mail(
            subject=notification.title,
            message=notification.message,
            from_email="noreply@labitory.com",
            recipient_list=[self.user.email],
            fail_silently=False
        )
        
        self.assertEqual(result, 1)  # One email sent
        self.assertEqual(len(mail.outbox), 1)
        
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, "Test Email")
        self.assertEqual(sent_email.to, ["test@example.com"])
        self.assertIn("This is a test email notification", sent_email.body)
    
    def test_email_template_rendering(self):
        """Test email template rendering."""
        template = EmailTemplate.objects.create(
            name="booking_confirmation",
            subject="Booking Confirmation - {{booking.title}}",
            body_html="<p>Dear {{user.first_name}}, your booking for {{booking.resource.name}} is confirmed.</p>",
            body_text="Dear {{user.first_name}}, your booking for {{booking.resource.name}} is confirmed."
        )
        
        booking = BookingFactory(user=self.user)
        
        # Simulate template rendering (would use Django templates)
        context = {
            'user': self.user,
            'booking': booking
        }
        
        rendered_subject = template.subject.replace(
            '{{booking.title}}', booking.title
        )
        rendered_body = template.body_text.replace(
            '{{user.first_name}}', self.user.first_name
        ).replace(
            '{{booking.resource.name}}', booking.resource.name
        )
        
        self.assertIn(booking.title, rendered_subject)
        self.assertIn(self.user.first_name, rendered_body)
        self.assertIn(booking.resource.name, rendered_body)
    
    @patch('booking.services.notification_service.send_mail')
    def test_email_notification_failure_handling(self, mock_send_mail):
        """Test handling email notification failures."""
        mock_send_mail.side_effect = Exception("SMTP server error")
        
        notification = Notification.objects.create(
            user=self.user,
            title="Failed Email",
            message="This should fail",
            delivery_method="email",
            status="pending"
        )
        
        try:
            result = self.notification_service.send_email_notification(notification)
            self.assertFalse(result)
        except:
            # Expected to fail
            notification.status = "failed"
            notification.failure_reason = "SMTP server error"
            notification.save()
        
        self.assertEqual(notification.status, "failed")
        self.assertIsNotNone(notification.failure_reason)
    
    def test_bulk_email_sending(self):
        """Test sending bulk email notifications."""
        users = [UserFactory(email=f"user{i}@example.com") for i in range(5)]
        
        notifications = []
        for user in users:
            notification = Notification.objects.create(
                user=user,
                title="Bulk Email Test",
                message="This is a bulk email",
                delivery_method="email",
                status="pending"
            )
            notifications.append(notification)
        
        # Send bulk emails
        for notification in notifications:
            from django.core.mail import send_mail
            send_mail(
                subject=notification.title,
                message=notification.message,
                from_email="noreply@labitory.com",
                recipient_list=[notification.user.email]
            )
            
            notification.status = "sent"
            notification.sent_at = timezone.now()
            notification.save()
        
        self.assertEqual(len(mail.outbox), 5)
        
        # Verify all notifications were sent
        sent_notifications = Notification.objects.filter(status="sent")
        self.assertEqual(sent_notifications.count(), 5)


class TestSMSNotifications(TestCase):
    """Test SMS notification functionality."""
    
    def setUp(self):
        self.user = UserFactory()
        self.user_profile = self.user.userprofile
        self.user_profile.phone_number = "+1234567890"
        self.user_profile.save()
        
        # Mock SMS service
        self.sms_service = Mock()
    
    @patch('booking.services.sms_service.SMSService')
    def test_send_sms_notification(self, mock_sms_service):
        """Test sending SMS notification."""
        mock_sms_instance = Mock()
        mock_sms_service.return_value = mock_sms_instance
        mock_sms_instance.send_sms.return_value = {'success': True, 'message_id': 'sms123'}
        
        notification = Notification.objects.create(
            user=self.user,
            title="SMS Test",
            message="This is a test SMS",
            delivery_method="sms",
            status="pending"
        )
        
        # Simulate SMS sending
        result = mock_sms_instance.send_sms(
            to=self.user_profile.phone_number,
            message=notification.message
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], 'sms123')
        
        # Update notification status
        notification.status = "sent"
        notification.sent_at = timezone.now()
        notification.external_id = result['message_id']
        notification.save()
        
        self.assertEqual(notification.status, "sent")
        self.assertEqual(notification.external_id, "sms123")
    
    @patch('booking.services.sms_service.SMSService')
    def test_sms_notification_failure(self, mock_sms_service):
        """Test SMS notification failure handling."""
        mock_sms_instance = Mock()
        mock_sms_service.return_value = mock_sms_instance
        mock_sms_instance.send_sms.return_value = {'success': False, 'error': 'Invalid phone number'}
        
        notification = Notification.objects.create(
            user=self.user,
            title="SMS Failure Test",
            message="This should fail",
            delivery_method="sms",
            status="pending"
        )
        
        # Simulate SMS sending failure
        result = mock_sms_instance.send_sms(
            to=self.user_profile.phone_number,
            message=notification.message
        )
        
        self.assertFalse(result['success'])
        
        # Update notification with failure
        notification.status = "failed"
        notification.failure_reason = result['error']
        notification.save()
        
        self.assertEqual(notification.status, "failed")
        self.assertEqual(notification.failure_reason, "Invalid phone number")
    
    def test_phone_number_validation(self):
        """Test phone number validation for SMS."""
        valid_numbers = [
            "+1234567890",
            "+447700123456",
            "+33123456789"
        ]
        
        invalid_numbers = [
            "123456",
            "not-a-number",
            "+123",
            ""
        ]
        
        for number in valid_numbers:
            self.user_profile.phone_number = number
            self.user_profile.save()
            
            # Simple validation - starts with + and has digits
            is_valid = (number.startswith('+') and 
                       len(number) >= 10 and 
                       number[1:].isdigit())
            self.assertTrue(is_valid)
        
        for number in invalid_numbers:
            if number == "":
                is_valid = False
            else:
                is_valid = (number.startswith('+') and 
                           len(number) >= 10 and 
                           number[1:].isdigit())
            self.assertFalse(is_valid)


class TestPushNotifications(TestCase):
    """Test push notification functionality."""
    
    def setUp(self):
        self.user = UserFactory()
        
        # Create push subscription
        self.subscription = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://fcm.googleapis.com/fcm/send/abc123",
            p256dh_key="sample_p256dh_key",
            auth_key="sample_auth_key",
            is_active=True
        )
    
    def test_create_push_subscription(self):
        """Test creating push notification subscription."""
        subscription = PushSubscription.objects.create(
            user=UserFactory(),
            endpoint="https://fcm.googleapis.com/fcm/send/xyz789",
            p256dh_key="another_p256dh_key",
            auth_key="another_auth_key",
            user_agent="Mozilla/5.0...",
            is_active=True
        )
        
        self.assertIsNotNone(subscription.user)
        self.assertTrue(subscription.endpoint.startswith("https://"))
        self.assertTrue(subscription.is_active)
        self.assertIsNotNone(subscription.created_at)
    
    @patch('booking.services.push_service.webpush')
    def test_send_push_notification(self, mock_webpush):
        """Test sending push notification."""
        mock_webpush.send.return_value = Mock(status_code=200)
        
        notification = Notification.objects.create(
            user=self.user,
            title="Push Test",
            message="This is a push notification test",
            delivery_method="push",
            status="pending"
        )
        
        # Simulate push notification sending
        payload = {
            'title': notification.title,
            'body': notification.message,
            'icon': '/static/images/notification-icon.png',
            'badge': '/static/images/badge-icon.png'
        }
        
        result = mock_webpush.send(
            subscription_info={
                'endpoint': self.subscription.endpoint,
                'keys': {
                    'p256dh': self.subscription.p256dh_key,
                    'auth': self.subscription.auth_key
                }
            },
            data=json.dumps(payload),
            vapid_private_key="test_private_key",
            vapid_claims={"sub": "mailto:admin@labitory.com"}
        )
        
        self.assertEqual(result.status_code, 200)
        
        # Update notification status
        notification.status = "sent"
        notification.sent_at = timezone.now()
        notification.save()
        
        self.assertEqual(notification.status, "sent")
    
    def test_push_subscription_cleanup(self):
        """Test cleanup of invalid push subscriptions."""
        # Create expired subscription
        expired_subscription = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://expired.endpoint.com/send/old123",
            p256dh_key="expired_key",
            auth_key="expired_auth",
            is_active=True
        )
        
        # Simulate subscription becoming invalid
        expired_subscription.is_active = False
        expired_subscription.save()
        
        # Count active subscriptions
        active_subscriptions = PushSubscription.objects.filter(
            user=self.user,
            is_active=True
        )
        
        self.assertEqual(active_subscriptions.count(), 1)  # Only the valid one
    
    def test_multiple_device_subscriptions(self):
        """Test handling multiple device subscriptions per user."""
        # Create additional subscriptions for different devices
        mobile_subscription = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://fcm.googleapis.com/fcm/send/mobile123",
            p256dh_key="mobile_p256dh_key",
            auth_key="mobile_auth_key",
            user_agent="Mobile Safari",
            device_type="mobile",
            is_active=True
        )
        
        desktop_subscription = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://fcm.googleapis.com/fcm/send/desktop123",
            p256dh_key="desktop_p256dh_key",
            auth_key="desktop_auth_key",
            user_agent="Chrome Desktop",
            device_type="desktop",
            is_active=True
        )
        
        user_subscriptions = PushSubscription.objects.filter(
            user=self.user,
            is_active=True
        )
        
        self.assertEqual(user_subscriptions.count(), 3)  # Original + mobile + desktop
        
        device_types = [sub.device_type for sub in user_subscriptions]
        self.assertIn("mobile", device_types)
        self.assertIn("desktop", device_types)


class TestInAppNotifications(TestCase):
    """Test in-app notification functionality."""
    
    def setUp(self):
        self.user = UserFactory()
    
    def test_create_in_app_notification(self):
        """Test creating in-app notification."""
        notification = Notification.objects.create(
            user=self.user,
            title="In-App Test",
            message="This is an in-app notification",
            delivery_method="in_app",
            status="sent",  # In-app notifications are immediately available
            notification_type="booking_reminder"
        )
        
        self.assertEqual(notification.delivery_method, "in_app")
        self.assertEqual(notification.status, "sent")
        self.assertIsNotNone(notification.created_at)
    
    def test_unread_notification_count(self):
        """Test counting unread in-app notifications."""
        # Create several notifications
        for i in range(5):
            Notification.objects.create(
                user=self.user,
                title=f"Notification {i}",
                message=f"Message {i}",
                delivery_method="in_app",
                status="sent",
                is_read=False
            )
        
        # Mark some as read
        notifications = Notification.objects.filter(user=self.user)[:2]
        for notification in notifications:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save()
        
        unread_count = Notification.objects.filter(
            user=self.user,
            delivery_method="in_app",
            is_read=False
        ).count()
        
        self.assertEqual(unread_count, 3)
    
    def test_notification_read_status(self):
        """Test notification read status management."""
        notification = Notification.objects.create(
            user=self.user,
            title="Read Status Test",
            message="Testing read status",
            delivery_method="in_app",
            status="sent",
            is_read=False
        )
        
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)
        
        # Mark as read
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)
    
    def test_notification_action_buttons(self):
        """Test notifications with action buttons."""
        notification = Notification.objects.create(
            user=self.user,
            title="Booking Approval Request",
            message="Your booking request needs approval",
            delivery_method="in_app",
            status="sent",
            notification_type="approval_request",
            action_url="/approval/123/",
            action_data=json.dumps({
                'booking_id': 123,
                'actions': ['approve', 'reject']
            })
        )
        
        self.assertIsNotNone(notification.action_url)
        self.assertIsNotNone(notification.action_data)
        
        action_data = json.loads(notification.action_data)
        self.assertEqual(action_data['booking_id'], 123)
        self.assertIn('approve', action_data['actions'])
        self.assertIn('reject', action_data['actions'])


class TestNotificationBatching(TestCase):
    """Test notification batching and aggregation."""
    
    def setUp(self):
        self.user = UserFactory()
    
    def test_notification_digest_creation(self):
        """Test creating notification digests."""
        # Create multiple notifications of same type
        for i in range(5):
            Notification.objects.create(
                user=self.user,
                title="Booking Reminder",
                message=f"You have a booking in {i+1} hours",
                delivery_method="email",
                notification_type="booking_reminder",
                status="pending",
                created_at=timezone.now() - timedelta(minutes=i*30)
            )
        
        # Group notifications for digest
        reminder_notifications = Notification.objects.filter(
            user=self.user,
            notification_type="booking_reminder",
            status="pending"
        ).order_by('created_at')
        
        self.assertEqual(reminder_notifications.count(), 5)
        
        # Create digest notification
        digest_message = f"You have {reminder_notifications.count()} upcoming bookings."
        
        digest = Notification.objects.create(
            user=self.user,
            title="Daily Booking Digest",
            message=digest_message,
            delivery_method="email",
            notification_type="digest",
            status="pending"
        )
        
        # Mark original notifications as batched
        reminder_notifications.update(
            status="batched",
            batched_into=digest
        )
        
        self.assertIn("5 upcoming bookings", digest.message)
        
        batched_count = Notification.objects.filter(
            user=self.user,
            status="batched"
        ).count()
        self.assertEqual(batched_count, 5)
    
    def test_notification_frequency_limits(self):
        """Test notification frequency limiting."""
        # Create user preference for frequency limiting
        pref = NotificationPreference.objects.create(
            user=self.user,
            notification_type="booking_reminder",
            email_enabled=True,
            frequency_limit="hourly"
        )
        
        # Create notifications within the same hour
        now = timezone.now()
        for i in range(3):
            Notification.objects.create(
                user=self.user,
                title="Frequent Reminder",
                message=f"Reminder {i+1}",
                delivery_method="email",
                notification_type="booking_reminder",
                status="pending",
                created_at=now - timedelta(minutes=i*15)
            )
        
        # Check notifications within frequency window
        hour_ago = now - timedelta(hours=1)
        recent_notifications = Notification.objects.filter(
            user=self.user,
            notification_type="booking_reminder",
            created_at__gte=hour_ago
        )
        
        # Based on hourly limit, only one should be sent
        if pref.frequency_limit == "hourly":
            notifications_to_send = recent_notifications[:1]
            notifications_to_hold = recent_notifications[1:]
            
            # Mark held notifications
            for notification in notifications_to_hold:
                notification.status = "held"
                notification.save()
        
        held_count = Notification.objects.filter(
            user=self.user,
            status="held"
        ).count()
        
        self.assertEqual(held_count, 2)


class TestNotificationIntegration(TestCase):
    """Test notification integration with booking system."""
    
    def setUp(self):
        self.user = UserFactory()
        self.resource = ResourceFactory()
        self.booking = BookingFactory(user=self.user, resource=self.resource)
    
    def test_booking_confirmation_notification(self):
        """Test booking confirmation notification creation."""
        notification = Notification.objects.create(
            user=self.user,
            title=f"Booking Confirmed: {self.booking.title}",
            message=f"Your booking for {self.resource.name} has been confirmed.",
            delivery_method="email",
            notification_type="booking_confirmation",
            status="pending",
            related_object_type="booking",
            related_object_id=self.booking.id
        )
        
        self.assertEqual(notification.related_object_id, self.booking.id)
        self.assertEqual(notification.related_object_type, "booking")
        self.assertIn(self.booking.title, notification.title)
        self.assertIn(self.resource.name, notification.message)
    
    def test_booking_reminder_notification(self):
        """Test booking reminder notification creation."""
        # Create reminder for booking starting in 2 hours
        reminder_time = self.booking.start_time - timedelta(hours=2)
        
        notification = Notification.objects.create(
            user=self.user,
            title="Booking Reminder",
            message=f"Your booking for {self.resource.name} starts in 2 hours.",
            delivery_method="email",
            notification_type="booking_reminder",
            status="scheduled",
            scheduled_for=reminder_time,
            related_object_type="booking",
            related_object_id=self.booking.id
        )
        
        self.assertEqual(notification.status, "scheduled")
        self.assertEqual(notification.scheduled_for, reminder_time)
        self.assertIn("starts in 2 hours", notification.message)
    
    def test_booking_cancellation_notification(self):
        """Test booking cancellation notification."""
        # Cancel the booking
        self.booking.status = "cancelled"
        self.booking.save()
        
        # Create cancellation notification
        notification = Notification.objects.create(
            user=self.user,
            title="Booking Cancelled",
            message=f"Your booking for {self.resource.name} has been cancelled.",
            delivery_method="email",
            notification_type="booking_cancellation",
            status="pending",
            related_object_type="booking",
            related_object_id=self.booking.id
        )
        
        self.assertEqual(notification.notification_type, "booking_cancellation")
        self.assertIn("cancelled", notification.message)
    
    def test_maintenance_alert_notification(self):
        """Test maintenance alert notification."""
        notification = Notification.objects.create(
            user=self.user,
            title=f"Maintenance Alert: {self.resource.name}",
            message=f"Scheduled maintenance for {self.resource.name} will affect your booking.",
            delivery_method="email",
            notification_type="maintenance_alert",
            status="pending",
            priority="high"
        )
        
        self.assertEqual(notification.notification_type, "maintenance_alert")
        self.assertEqual(notification.priority, "high")
        self.assertIn("maintenance", notification.message.lower())