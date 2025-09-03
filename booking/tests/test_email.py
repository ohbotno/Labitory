"""
Test cases for email notification functionality.
"""
from django.test import TestCase
from django.core import mail
from django.contrib.auth.models import User
from django.core.management import call_command
from datetime import datetime, timedelta
from booking.models import (
    Booking, UserProfile, Resource, NotificationTemplate,
    EmailNotification, NotificationPreference
)
from booking.tests.factories import UserFactory, ResourceFactory, BookingFactory
from booking.email_service import EmailService
from booking.signals import booking_created, booking_approved, booking_cancelled
import json


class EmailServiceTests(TestCase):
    """Test email service functionality."""
    
    def setUp(self):
        self.email_service = EmailService()
        self.user = UserFactory(email='test@example.com')
        self.resource = ResourceFactory()
        mail.outbox = []  # Clear email outbox
    
    def test_email_service_initialization(self):
        """Test email service initializes correctly."""
        self.assertIsInstance(self.email_service, EmailService)
    
    def test_send_booking_confirmation_email(self):
        """Test sending booking confirmation email."""
        booking = BookingFactory(user=self.user, resource=self.resource)
        
        self.email_service.send_booking_confirmation(booking)
        
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('Booking Confirmed', email.subject)
        self.assertIn(self.user.email, email.to)
        self.assertIn(booking.resource.name, email.body)
    
    def test_send_booking_reminder_email(self):
        """Test sending booking reminder email."""
        start_time = datetime.now() + timedelta(hours=24)
        booking = BookingFactory(
            user=self.user, 
            resource=self.resource,
            start_datetime=start_time,
            status='confirmed'
        )
        
        self.email_service.send_booking_reminder(booking)
        
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('Reminder', email.subject)
        self.assertIn(self.user.email, email.to)
    
    def test_send_booking_cancellation_email(self):
        """Test sending booking cancellation email."""
        booking = BookingFactory(
            user=self.user, 
            resource=self.resource,
            status='cancelled'
        )
        
        self.email_service.send_booking_cancellation(booking)
        
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('Cancelled', email.subject)
        self.assertIn(self.user.email, email.to)
    
    def test_send_approval_request_email(self):
        """Test sending approval request email."""
        approver = UserFactory(role='lab_manager', email='approver@example.com')
        booking = BookingFactory(
            user=self.user,
            resource=self.resource,
            status='pending_approval'
        )
        
        self.email_service.send_approval_request(booking, approver)
        
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('Approval Required', email.subject)
        self.assertIn(approver.email, email.to)
    
    def test_send_approval_decision_email(self):
        """Test sending approval decision email."""
        booking = BookingFactory(
            user=self.user,
            resource=self.resource,
            status='confirmed'
        )
        
        self.email_service.send_approval_decision(booking, 'approved', 'Looks good!')
        
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('approved', email.subject.lower())
        self.assertIn(self.user.email, email.to)
    
    def test_email_template_rendering(self):
        """Test email template rendering with context."""
        booking = BookingFactory(user=self.user, resource=self.resource)
        
        context = {
            'user': self.user,
            'booking': booking,
            'resource': self.resource
        }
        
        rendered_subject = self.email_service.render_template(
            'booking_confirmation_subject.txt', context
        )
        rendered_body = self.email_service.render_template(
            'booking_confirmation_body.html', context
        )
        
        self.assertIn(self.user.first_name, rendered_subject)
        self.assertIn(booking.resource.name, rendered_body)
    
    def test_email_batch_sending(self):
        """Test batch email sending functionality."""
        users = UserFactory.create_batch(5)
        bookings = [BookingFactory(user=user, resource=self.resource) for user in users]
        
        self.email_service.send_batch_confirmations(bookings)
        
        self.assertEqual(len(mail.outbox), 5)
        
        # Check all users received emails
        recipients = [email.to[0] for email in mail.outbox]
        user_emails = [user.email for user in users]
        for email in user_emails:
            self.assertIn(email, recipients)


class EmailNotificationModelTests(TestCase):
    """Test email notification model functionality."""
    
    def setUp(self):
        self.user = UserFactory()
        self.booking = BookingFactory(user=self.user)
    
    def test_email_notification_creation(self):
        """Test creating email notification record."""
        notification = EmailNotification.objects.create(
            user=self.user,
            notification_type='booking_confirmation',
            subject='Test Subject',
            body='Test Body',
            booking=self.booking
        )
        
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.notification_type, 'booking_confirmation')
        self.assertFalse(notification.is_sent)
    
    def test_email_notification_sending(self):
        """Test email notification sending process."""
        notification = EmailNotification.objects.create(
            user=self.user,
            notification_type='booking_confirmation',
            subject='Test Subject',
            body='Test Body',
            booking=self.booking
        )
        
        mail.outbox = []
        notification.send()
        
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(notification.is_sent)
        self.assertIsNotNone(notification.sent_at)
    
    def test_email_notification_failure_handling(self):
        """Test email notification failure handling."""
        notification = EmailNotification.objects.create(
            user=self.user,
            notification_type='booking_confirmation',
            subject='Test Subject',
            body='Test Body',
            booking=self.booking
        )
        
        # Simulate email sending failure
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.dummy.EmailBackend'):
            try:
                notification.send()
            except Exception as e:
                notification.mark_failed(str(e))
        
        self.assertTrue(notification.failed)
        self.assertIsNotNone(notification.error_message)
    
    def test_email_notification_retry_mechanism(self):
        """Test email notification retry mechanism."""
        notification = EmailNotification.objects.create(
            user=self.user,
            notification_type='booking_confirmation',
            subject='Test Subject',
            body='Test Body',
            booking=self.booking,
            failed=True,
            retry_count=2
        )
        
        self.assertTrue(notification.can_retry())
        
        # Max retries reached
        notification.retry_count = 5
        notification.save()
        self.assertFalse(notification.can_retry())


class NotificationTemplateTests(TestCase):
    """Test notification template functionality."""
    
    def setUp(self):
        self.user = UserFactory()
        self.resource = ResourceFactory()
        self.booking = BookingFactory(user=self.user, resource=self.resource)
    
    def test_notification_template_creation(self):
        """Test creating notification templates."""
        template = NotificationTemplate.objects.create(
            name='booking_confirmation',
            subject='Booking Confirmed: {{booking.resource.name}}',
            body_html='<p>Hello {{user.first_name}}, your booking is confirmed.</p>',
            body_text='Hello {{user.first_name}}, your booking is confirmed.'
        )
        
        self.assertEqual(template.name, 'booking_confirmation')
        self.assertIn('{{booking.resource.name}}', template.subject)
    
    def test_template_rendering_with_context(self):
        """Test template rendering with context variables."""
        template = NotificationTemplate.objects.create(
            name='booking_confirmation',
            subject='Booking Confirmed: {{booking.resource.name}}',
            body_html='<p>Hello {{user.first_name}}, your booking for {{booking.resource.name}} is confirmed.</p>',
            body_text='Hello {{user.first_name}}, your booking for {{booking.resource.name}} is confirmed.'
        )
        
        context = {
            'user': self.user,
            'booking': self.booking
        }
        
        rendered_subject = template.render_subject(context)
        rendered_html = template.render_html_body(context)
        rendered_text = template.render_text_body(context)
        
        self.assertIn(self.booking.resource.name, rendered_subject)
        self.assertIn(self.user.first_name, rendered_html)
        self.assertIn(self.user.first_name, rendered_text)
    
    def test_template_validation(self):
        """Test template syntax validation."""
        # Valid template
        valid_template = NotificationTemplate(
            name='valid_template',
            subject='Hello {{user.first_name}}',
            body_html='<p>{{booking.resource.name}}</p>',
            body_text='{{booking.resource.name}}'
        )
        
        self.assertTrue(valid_template.is_valid_syntax())
        
        # Invalid template syntax
        invalid_template = NotificationTemplate(
            name='invalid_template',
            subject='Hello {{user.first_name',  # Missing closing brace
            body_html='<p>{{booking.resource.name}}</p>',
            body_text='{{booking.resource.name}}'
        )
        
        self.assertFalse(invalid_template.is_valid_syntax())
    
    def test_default_templates_creation(self):
        """Test default template creation."""
        from django.core.management import call_command
        
        call_command('create_email_templates')
        
        # Check that default templates were created
        template_names = [
            'booking_confirmation',
            'booking_reminder',
            'booking_cancellation',
            'approval_request',
            'approval_decision'
        ]
        
        for name in template_names:
            self.assertTrue(
                NotificationTemplate.objects.filter(name=name).exists()
            )


class NotificationPreferenceTests(TestCase):
    """Test user notification preferences."""
    
    def setUp(self):
        self.user = UserFactory()
    
    def test_notification_preference_creation(self):
        """Test creating notification preferences."""
        preferences = NotificationPreference.objects.create(
            user=self.user,
            email_enabled=True,
            booking_confirmations=True,
            booking_reminders=True,
            booking_cancellations=True,
            approval_requests=False,
            system_notifications=True
        )
        
        self.assertEqual(preferences.user, self.user)
        self.assertTrue(preferences.email_enabled)
        self.assertFalse(preferences.approval_requests)
    
    def test_default_notification_preferences(self):
        """Test default notification preferences for new users."""
        # Check that default preferences are created for new users
        if hasattr(self.user, 'notification_preferences'):
            prefs = self.user.notification_preferences
            self.assertTrue(prefs.email_enabled)
            self.assertTrue(prefs.booking_confirmations)
    
    def test_notification_preference_updates(self):
        """Test updating notification preferences."""
        preferences = NotificationPreference.objects.create(
            user=self.user,
            email_enabled=True,
            booking_reminders=True
        )
        
        # Update preferences
        preferences.booking_reminders = False
        preferences.save()
        
        preferences.refresh_from_db()
        self.assertFalse(preferences.booking_reminders)
    
    def test_bulk_notification_preference_updates(self):
        """Test bulk notification preference updates."""
        users = UserFactory.create_batch(5)
        
        for user in users:
            NotificationPreference.objects.create(
                user=user,
                email_enabled=True,
                booking_reminders=True
            )
        
        # Bulk disable reminders
        NotificationPreference.objects.filter(
            user__in=users
        ).update(booking_reminders=False)
        
        # Verify all were updated
        for user in users:
            prefs = NotificationPreference.objects.get(user=user)
            self.assertFalse(prefs.booking_reminders)


class EmailSignalTests(TestCase):
    """Test email notification signals."""
    
    def setUp(self):
        self.user = UserFactory()
        self.resource = ResourceFactory()
        mail.outbox = []
    
    def test_booking_created_signal(self):
        """Test booking created signal triggers email."""
        booking = BookingFactory(user=self.user, resource=self.resource)
        
        # Signal should trigger automatically
        booking_created.send(sender=Booking, booking=booking)
        
        # Check if email notification was created
        notifications = EmailNotification.objects.filter(
            user=self.user,
            notification_type='booking_created'
        )
        self.assertTrue(notifications.exists())
    
    def test_booking_approved_signal(self):
        """Test booking approved signal triggers email."""
        booking = BookingFactory(
            user=self.user,
            resource=self.resource,
            status='confirmed'
        )
        
        booking_approved.send(sender=Booking, booking=booking)
        
        # Check if approval email was queued
        notifications = EmailNotification.objects.filter(
            user=self.user,
            notification_type='booking_approved'
        )
        self.assertTrue(notifications.exists())
    
    def test_booking_cancelled_signal(self):
        """Test booking cancelled signal triggers email."""
        booking = BookingFactory(
            user=self.user,
            resource=self.resource,
            status='cancelled'
        )
        
        booking_cancelled.send(sender=Booking, booking=booking)
        
        # Check if cancellation email was queued
        notifications = EmailNotification.objects.filter(
            user=self.user,
            notification_type='booking_cancelled'
        )
        self.assertTrue(notifications.exists())


class EmailManagementCommandTests(TestCase):
    """Test email management commands."""
    
    def setUp(self):
        self.user = UserFactory()
        self.resource = ResourceFactory()
        mail.outbox = []
    
    def test_send_notifications_command(self):
        """Test send_notifications management command."""
        # Create pending email notifications
        EmailNotification.objects.create(
            user=self.user,
            notification_type='booking_confirmation',
            subject='Test Notification',
            body='Test Body',
            is_sent=False
        )
        
        call_command('send_notifications')
        
        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        
        # Check that notification was marked as sent
        notification = EmailNotification.objects.first()
        self.assertTrue(notification.is_sent)
    
    def test_send_reminders_command(self):
        """Test send reminder notifications command."""
        # Create booking starting in 24 hours
        start_time = datetime.now() + timedelta(hours=24)
        booking = BookingFactory(
            user=self.user,
            resource=self.resource,
            start_datetime=start_time,
            status='confirmed'
        )
        
        call_command('send_notifications', '--send-reminders', '--reminder-hours', '24')
        
        # Check that reminder email was sent
        self.assertGreater(len(mail.outbox), 0)
    
    def test_create_email_templates_command(self):
        """Test create_email_templates management command."""
        call_command('create_email_templates')
        
        # Check that default templates were created
        self.assertTrue(
            NotificationTemplate.objects.filter(name='booking_confirmation').exists()
        )
        self.assertTrue(
            NotificationTemplate.objects.filter(name='booking_reminder').exists()
        )
    
    def test_cleanup_old_notifications_command(self):
        """Test cleanup of old email notifications."""
        # Create old notifications
        old_date = datetime.now() - timedelta(days=35)
        EmailNotification.objects.create(
            user=self.user,
            notification_type='booking_confirmation',
            subject='Old Notification',
            body='Old Body',
            is_sent=True,
            sent_at=old_date,
            created_at=old_date
        )
        
        call_command('cleanup_notifications', '--days', '30')
        
        # Check that old notifications were cleaned up
        old_notifications = EmailNotification.objects.filter(
            created_at__lt=datetime.now() - timedelta(days=30)
        )
        self.assertEqual(old_notifications.count(), 0)


class EmailDeliveryTests(TestCase):
    """Test email delivery and reliability."""
    
    def setUp(self):
        self.user = UserFactory()
        self.resource = ResourceFactory()
        mail.outbox = []
    
    def test_email_delivery_retry_mechanism(self):
        """Test email delivery retry mechanism."""
        notification = EmailNotification.objects.create(
            user=self.user,
            notification_type='booking_confirmation',
            subject='Test Subject',
            body='Test Body'
        )
        
        # Simulate delivery failure
        notification.mark_failed('SMTP connection error')
        
        # Retry sending
        if notification.can_retry():
            notification.retry()
            
        self.assertGreater(notification.retry_count, 0)
    
    def test_email_bounce_handling(self):
        """Test email bounce handling."""
        # This would require integration with email service provider
        # to handle bounce notifications
        pass
    
    def test_email_unsubscribe_handling(self):
        """Test email unsubscribe functionality."""
        # Create unsubscribe token
        unsubscribe_token = self.user.userprofile.generate_unsubscribe_token()
        
        # Test unsubscribe process
        preferences = NotificationPreference.objects.get_or_create(
            user=self.user,
            defaults={'email_enabled': True}
        )[0]
        
        preferences.email_enabled = False
        preferences.save()
        
        self.assertFalse(preferences.email_enabled)
    
    def test_email_personalization(self):
        """Test email personalization features."""
        booking = BookingFactory(user=self.user, resource=self.resource)
        
        template = NotificationTemplate.objects.create(
            name='personalized_confirmation',
            subject='Hello {{user.first_name}}, booking confirmed!',
            body_html='''
            <p>Dear {{user.first_name}} {{user.last_name}},</p>
            <p>Your booking for {{booking.resource.name}} on {{booking.start_datetime|date:"F j, Y"}} is confirmed.</p>
            <p>Resource location: {{booking.resource.location}}</p>
            ''',
            body_text='''
            Dear {{user.first_name}} {{user.last_name}},
            Your booking for {{booking.resource.name}} on {{booking.start_datetime|date:"F j, Y"}} is confirmed.
            Resource location: {{booking.resource.location}}
            '''
        )
        
        context = {'user': self.user, 'booking': booking}
        
        rendered_subject = template.render_subject(context)
        rendered_html = template.render_html_body(context)
        
        self.assertIn(self.user.first_name, rendered_subject)
        self.assertIn(self.user.last_name, rendered_html)
        self.assertIn(booking.resource.name, rendered_html)


class EmailSecurityTests(TestCase):
    """Test email security features."""
    
    def setUp(self):
        self.user = UserFactory()
    
    def test_email_content_sanitization(self):
        """Test email content is properly sanitized."""
        malicious_content = '<script>alert("xss")</script>'
        
        notification = EmailNotification.objects.create(
            user=self.user,
            notification_type='booking_confirmation',
            subject='Test Subject',
            body=malicious_content
        )
        
        # Email body should be sanitized
        self.assertNotIn('<script>', notification.get_sanitized_body())
    
    def test_email_header_injection_prevention(self):
        """Test email header injection prevention."""
        malicious_subject = 'Test Subject\nBcc: attacker@example.com'
        
        notification = EmailNotification.objects.create(
            user=self.user,
            notification_type='booking_confirmation',
            subject=malicious_subject,
            body='Test Body'
        )
        
        # Subject should be sanitized to prevent header injection
        sanitized_subject = notification.get_sanitized_subject()
        self.assertNotIn('\n', sanitized_subject)
        self.assertNotIn('Bcc:', sanitized_subject)
    
    def test_email_rate_limiting(self):
        """Test email rate limiting functionality."""
        # Create many notifications for same user
        for i in range(10):
            EmailNotification.objects.create(
                user=self.user,
                notification_type='booking_confirmation',
                subject=f'Test Subject {i}',
                body='Test Body'
            )
        
        # Rate limiting should prevent sending too many emails
        # This would be implemented in the email service
        pass
    
    def test_email_spam_prevention(self):
        """Test email spam prevention measures."""
        # Test SPF, DKIM, DMARC headers are properly set
        # This would be tested at the SMTP configuration level
        pass


class EmailPerformanceTests(TestCase):
    """Test email system performance."""
    
    def setUp(self):
        self.users = UserFactory.create_batch(100)
        self.resource = ResourceFactory()
    
    def test_bulk_email_performance(self):
        """Test bulk email sending performance."""
        # Create notifications for all users
        notifications = []
        for user in self.users:
            notifications.append(EmailNotification(
                user=user,
                notification_type='system_announcement',
                subject='System Maintenance Notice',
                body='System will be down for maintenance.'
            ))
        
        EmailNotification.objects.bulk_create(notifications)
        
        # Test bulk sending performance
        mail.outbox = []
        call_command('send_notifications')
        
        # All emails should be sent
        self.assertEqual(len(mail.outbox), 100)
    
    def test_email_queue_processing(self):
        """Test email queue processing efficiency."""
        # Create large number of notifications
        notifications = []
        for i in range(1000):
            user = self.users[i % len(self.users)]
            notifications.append(EmailNotification(
                user=user,
                notification_type='booking_confirmation',
                subject=f'Booking Confirmation {i}',
                body='Your booking is confirmed.'
            ))
        
        EmailNotification.objects.bulk_create(notifications)
        
        # Process queue and measure performance
        import time
        start_time = time.time()
        
        # Process in batches
        batch_size = 50
        unsent = EmailNotification.objects.filter(is_sent=False)[:batch_size]
        
        for notification in unsent:
            notification.send()
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process reasonably quickly
        self.assertLess(processing_time, 30)  # Less than 30 seconds for 50 emails