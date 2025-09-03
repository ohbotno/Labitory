"""
Notification-related models for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta


class NotificationPreference(models.Model):
    """User notification preferences."""
    NOTIFICATION_TYPES = [
        ('booking_confirmed', 'Booking Confirmed'),
        ('booking_cancelled', 'Booking Cancelled'), 
        ('booking_reminder', 'Booking Reminder'),
        ('booking_overridden', 'Booking Overridden'),
        ('approval_request', 'Approval Request'),
        ('approval_decision', 'Approval Decision'),
        ('maintenance_alert', 'Maintenance Alert'),
        ('conflict_detected', 'Conflict Detected'),
        ('quota_warning', 'Quota Warning'),
        ('waitlist_joined', 'Joined Waiting List'),
        ('waitlist_availability', 'Waiting List Slot Available'),
        ('waitlist_cancelled', 'Left Waiting List'),
        ('access_request_submitted', 'Access Request Submitted'),
        ('access_request_approved', 'Access Request Approved'),
        ('access_request_rejected', 'Access Request Rejected'),
        ('training_request_submitted', 'Training Request Submitted'),
        ('training_request_scheduled', 'Training Scheduled'),
        ('training_request_completed', 'Training Completed'),
        ('training_request_cancelled', 'Training Cancelled'),
    ]
    
    DELIVERY_METHODS = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('in_app', 'In-App'),
        ('push', 'Push Notification'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notification_preferences')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_METHODS)
    is_enabled = models.BooleanField(default=True)
    frequency = models.CharField(max_length=20, default='immediate', choices=[
        ('immediate', 'Immediate'),
        ('daily_digest', 'Daily Digest'),
        ('weekly_digest', 'Weekly Digest'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_notificationpreference'
        unique_together = ['user', 'notification_type', 'delivery_method']
    
    def __str__(self):
        return f"{self.user.username} - {self.get_notification_type_display()} via {self.get_delivery_method_display()}"


class PushSubscription(models.Model):
    """User push notification subscription details."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.URLField(max_length=500)
    p256dh_key = models.CharField(max_length=100, help_text="Public key for encryption")
    auth_key = models.CharField(max_length=50, help_text="Authentication secret")
    user_agent = models.CharField(max_length=200, blank=True, help_text="Browser/device info")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_pushsubscription'
        unique_together = ['user', 'endpoint']
    
    def __str__(self):
        return f"{self.user.username} - {self.endpoint[:50]}..."
    
    def to_dict(self):
        """Convert subscription to dictionary format for pywebpush."""
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": self.p256dh_key,
                "auth": self.auth_key
            }
        }


class Notification(models.Model):
    """Individual notification instances."""
    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('read', 'Read'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=NotificationPreference.NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default='medium')
    delivery_method = models.CharField(max_length=20, choices=NotificationPreference.DELIVERY_METHODS)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    
    # Related objects
    booking = models.ForeignKey('Booking', on_delete=models.CASCADE, null=True, blank=True)
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, null=True, blank=True)
    maintenance = models.ForeignKey('Maintenance', on_delete=models.CASCADE, null=True, blank=True)
    access_request = models.ForeignKey('AccessRequest', on_delete=models.CASCADE, null=True, blank=True)
    training_request = models.ForeignKey('TrainingRequest', on_delete=models.CASCADE, null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Retry logic
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'booking_notification'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['notification_type', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.user.username} ({self.status})"
    
    def mark_as_sent(self):
        """Mark notification as sent."""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at', 'updated_at'])
    
    def mark_as_read(self):
        """Mark notification as read."""
        self.status = 'read'
        self.read_at = timezone.now()
        self.save(update_fields=['status', 'read_at', 'updated_at'])
    
    def mark_as_failed(self, reason=None):
        """Mark notification as failed and handle retry logic."""
        self.status = 'failed'
        self.retry_count += 1
        if self.retry_count < self.max_retries:
            # Exponential backoff: 5min, 15min, 45min
            delay_minutes = 5 * (3 ** (self.retry_count - 1))
            self.next_retry_at = timezone.now() + timedelta(minutes=delay_minutes)
            self.status = 'pending'  # Reset to pending for retry
        
        # Store the failure reason in metadata
        if reason:
            if 'failure_reasons' not in self.metadata:
                self.metadata['failure_reasons'] = []
            self.metadata['failure_reasons'].append({
                'reason': reason,
                'timestamp': timezone.now().isoformat(),
                'retry_count': self.retry_count
            })
        
        self.save(update_fields=['status', 'retry_count', 'next_retry_at', 'metadata', 'updated_at'])
    
    def get_notification_url(self):
        """Get the appropriate URL for this notification based on its related object."""
        from django.urls import reverse
        
        try:
            # Check for related objects in order of priority
            if self.booking:
                return reverse('booking:booking_detail', kwargs={'booking_id': self.booking.id})
            elif self.resource:
                return reverse('booking:resource_detail', kwargs={'resource_id': self.resource.id})
            elif self.access_request:
                return reverse('booking:resource_detail', kwargs={'resource_id': self.access_request.resource.id})
            elif self.training_request:
                return reverse('booking:resource_detail', kwargs={'resource_id': self.training_request.resource.id})
            elif self.maintenance:
                return reverse('booking:resource_detail', kwargs={'resource_id': self.maintenance.resource.id})
            else:
                # Default to notifications page if no specific object
                return reverse('booking:notifications')
        except Exception:
            # Fallback to notifications page if URL generation fails
            return reverse('booking:notifications')
    
    def can_retry(self):
        """Check if notification can be retried."""
        return (
            self.retry_count < self.max_retries and
            self.next_retry_at and
            timezone.now() >= self.next_retry_at
        )


class EmailTemplate(models.Model):
    """Email templates for different notification types."""
    name = models.CharField(max_length=100, unique=True)
    notification_type = models.CharField(max_length=30, choices=NotificationPreference.NOTIFICATION_TYPES)
    subject_template = models.CharField(max_length=200)
    html_template = models.TextField()
    text_template = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Template variables documentation
    available_variables = models.JSONField(default=list, help_text="List of available template variables")
    
    class Meta:
        db_table = 'booking_emailtemplate'
    
    def __str__(self):
        return f"{self.name} ({self.get_notification_type_display()})"
    
    def render_subject(self, context):
        """Render subject with context variables."""
        from django.template import Template, Context
        template = Template(self.subject_template)
        return template.render(Context(context))
    
    def render_html(self, context):
        """Render HTML content with context variables."""
        from django.template import Template, Context
        template = Template(self.html_template)
        return template.render(Context(context))
    
    def render_text(self, context):
        """Render text content with context variables."""
        from django.template import Template, Context
        template = Template(self.text_template)
        return template.render(Context(context))


class EmailConfiguration(models.Model):
    """Store and manage email configuration settings."""
    
    # Email Backend Configuration
    BACKEND_CHOICES = [
        ('django.core.mail.backends.smtp.EmailBackend', 'SMTP Email Backend'),
        ('django.core.mail.backends.console.EmailBackend', 'Console Email Backend (Development)'),
        ('django.core.mail.backends.filebased.EmailBackend', 'File-based Email Backend (Testing)'),
        ('django.core.mail.backends.locmem.EmailBackend', 'In-memory Email Backend (Testing)'),
        ('django.core.mail.backends.dummy.EmailBackend', 'Dummy Email Backend (No emails sent)'),
    ]
    
    # Basic Configuration
    is_active = models.BooleanField(
        default=False,
        help_text="Enable this configuration as the active email settings"
    )
    name = models.CharField(
        max_length=100,
        help_text="Descriptive name for this email configuration"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of this configuration"
    )
    
    # Email Backend Settings
    email_backend = models.CharField(
        max_length=100,
        choices=BACKEND_CHOICES,
        default='django.core.mail.backends.smtp.EmailBackend',
        help_text="Django email backend to use"
    )
    
    # SMTP Server Settings
    email_host = models.CharField(
        max_length=255,
        help_text="SMTP server hostname (e.g., smtp.gmail.com)"
    )
    email_port = models.PositiveIntegerField(
        default=587,
        help_text="SMTP server port (587 for TLS, 465 for SSL, 25 for standard)"
    )
    email_use_tls = models.BooleanField(
        default=True,
        help_text="Use TLS (Transport Layer Security) encryption"
    )
    email_use_ssl = models.BooleanField(
        default=False,
        help_text="Use SSL (Secure Sockets Layer) encryption"
    )
    
    # Authentication Settings
    email_host_user = models.CharField(
        max_length=255,
        blank=True,
        help_text="SMTP server username/email address"
    )
    email_host_password = models.CharField(
        max_length=255,
        blank=True,
        help_text="SMTP server password (stored encrypted)"
    )
    
    # Email Addresses
    default_from_email = models.EmailField(
        help_text="Default 'from' email address for outgoing emails"
    )
    server_email = models.EmailField(
        blank=True,
        help_text="Email address used for error messages from Django"
    )
    
    # Advanced Settings
    email_timeout = models.PositiveIntegerField(
        default=10,
        help_text="Timeout in seconds for SMTP connections"
    )
    
    # File-based Backend Settings (for testing)
    email_file_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Directory path for file-based email backend"
    )
    
    # Validation and Testing
    is_validated = models.BooleanField(
        default=False,
        help_text="Whether this configuration has been successfully tested"
    )
    last_test_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this configuration was tested"
    )
    last_test_result = models.TextField(
        blank=True,
        help_text="Result of the last configuration test"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_email_configs',
        help_text="User who created this configuration"
    )
    
    class Meta:
        verbose_name = "Email Configuration"
        verbose_name_plural = "Email Configurations"
        ordering = ['-is_active', '-updated_at']
    
    def __str__(self):
        active_indicator = " (Active)" if self.is_active else ""
        return f"{self.name}{active_indicator}"
    
    def clean(self):
        """Validate the configuration settings."""
        super().clean()
        
        # Validate that only one configuration can be active
        if self.is_active:
            existing_active = EmailConfiguration.objects.filter(is_active=True)
            if self.pk:
                existing_active = existing_active.exclude(pk=self.pk)
            
            if existing_active.exists():
                raise ValidationError(
                    "Only one email configuration can be active at a time. "
                    "Please deactivate the current active configuration first."
                )
        
        # Validate SMTP settings for SMTP backend
        if self.email_backend == 'django.core.mail.backends.smtp.EmailBackend':
            if not self.email_host:
                raise ValidationError("Email host is required for SMTP backend.")
            
            if self.email_use_tls and self.email_use_ssl:
                raise ValidationError("Cannot use both TLS and SSL simultaneously.")
        
        # Validate file path for file-based backend
        if self.email_backend == 'django.core.mail.backends.filebased.EmailBackend':
            if not self.email_file_path:
                raise ValidationError("File path is required for file-based email backend.")
    
    def save(self, *args, **kwargs):
        """Override save to ensure only one active configuration."""
        self.full_clean()
        
        # If this configuration is being set as active, deactivate others
        if self.is_active:
            EmailConfiguration.objects.filter(is_active=True).update(is_active=False)
        
        super().save(*args, **kwargs)
    
    def activate(self):
        """Activate this configuration and deactivate others."""
        EmailConfiguration.objects.filter(is_active=True).update(is_active=False)
        self.is_active = True
        self.save()
    
    def deactivate(self):
        """Deactivate this configuration."""
        self.is_active = False
        self.save()
    
    def test_configuration(self, test_email=None):
        """Test this email configuration by sending a test email."""
        from django.core.mail import send_mail
        from django.conf import settings
        import tempfile
        import os
        
        # Temporarily apply this configuration
        original_settings = {}
        test_settings = {
            'EMAIL_BACKEND': self.email_backend,
            'EMAIL_HOST': self.email_host,
            'EMAIL_PORT': self.email_port,
            'EMAIL_USE_TLS': self.email_use_tls,
            'EMAIL_USE_SSL': self.email_use_ssl,
            'EMAIL_HOST_USER': self.email_host_user,
            'EMAIL_HOST_PASSWORD': self.email_host_password,
            'DEFAULT_FROM_EMAIL': self.default_from_email,
            'EMAIL_TIMEOUT': self.email_timeout,
        }
        
        # Handle file-based backend
        if self.email_backend == 'django.core.mail.backends.filebased.EmailBackend':
            if self.email_file_path:
                test_settings['EMAIL_FILE_PATH'] = self.email_file_path
            else:
                test_settings['EMAIL_FILE_PATH'] = tempfile.gettempdir()
        
        # Save original settings
        for key in test_settings:
            if hasattr(settings, key):
                original_settings[key] = getattr(settings, key)
        
        try:
            # Apply test settings
            for key, value in test_settings.items():
                setattr(settings, key, value)
            
            # Send test email
            test_recipient = test_email or self.default_from_email
            subject = f"Email Configuration Test - {self.name}"
            message = f"""
Email Configuration Test

This is a test email sent to verify the email configuration "{self.name}".

Configuration Details:
- Backend: {self.email_backend}
- Host: {self.email_host}
- Port: {self.email_port}
- Use TLS: {self.email_use_tls}
- Use SSL: {self.email_use_ssl}
- From: {self.default_from_email}

If you received this email, the configuration is working correctly!

--
Labitory System
            """.strip()
            
            send_mail(
                subject=subject,
                message=message,
                from_email=self.default_from_email,
                recipient_list=[test_recipient],
                fail_silently=False
            )
            
            # Update test results
            self.is_validated = True
            self.last_test_date = timezone.now()
            self.last_test_result = f"Success: Test email sent to {test_recipient}"
            self.save()
            
            return True, f"Test email sent successfully to {test_recipient}"
            
        except Exception as e:
            # Update test results with error
            self.is_validated = False
            self.last_test_date = timezone.now()
            self.last_test_result = f"Error: {str(e)}"
            self.save()
            
            return False, f"Test failed: {str(e)}"
            
        finally:
            # Restore original settings
            for key, value in original_settings.items():
                setattr(settings, key, value)
            
            # Remove any test settings that weren't originally present
            for key in test_settings:
                if key not in original_settings and hasattr(settings, key):
                    delattr(settings, key)
    
    def apply_to_settings(self):
        """Apply this configuration to Django settings."""
        from django.conf import settings
        
        if not self.is_active:
            return False
        
        # Apply configuration to settings
        settings.EMAIL_BACKEND = self.email_backend
        settings.EMAIL_HOST = self.email_host
        settings.EMAIL_PORT = self.email_port
        settings.EMAIL_USE_TLS = self.email_use_tls
        settings.EMAIL_USE_SSL = self.email_use_ssl
        settings.EMAIL_HOST_USER = self.email_host_user
        settings.EMAIL_HOST_PASSWORD = self.email_host_password
        settings.DEFAULT_FROM_EMAIL = self.default_from_email
        settings.EMAIL_TIMEOUT = self.email_timeout
        
        if self.server_email:
            settings.SERVER_EMAIL = self.server_email
        
        if self.email_backend == 'django.core.mail.backends.filebased.EmailBackend' and self.email_file_path:
            settings.EMAIL_FILE_PATH = self.email_file_path
        
        return True
    
    def get_configuration_dict(self):
        """Return configuration as a dictionary."""
        config = {
            'EMAIL_BACKEND': self.email_backend,
            'EMAIL_HOST': self.email_host,
            'EMAIL_PORT': self.email_port,
            'EMAIL_USE_TLS': self.email_use_tls,
            'EMAIL_USE_SSL': self.email_use_ssl,
            'EMAIL_HOST_USER': self.email_host_user,
            'EMAIL_HOST_PASSWORD': '***' if self.email_host_password else '',
            'DEFAULT_FROM_EMAIL': self.default_from_email,
            'EMAIL_TIMEOUT': self.email_timeout,
        }
        
        if self.server_email:
            config['SERVER_EMAIL'] = self.server_email
        
        if self.email_backend == 'django.core.mail.backends.filebased.EmailBackend' and self.email_file_path:
            config['EMAIL_FILE_PATH'] = self.email_file_path
        
        return config
    
    @classmethod
    def get_active_configuration(cls):
        """Get the currently active email configuration."""
        return cls.objects.filter(is_active=True).first()
    
    @classmethod
    def get_common_configurations(cls):
        """Return a list of common email provider configurations."""
        return [
            {
                'name': 'Gmail SMTP',
                'email_host': 'smtp.gmail.com',
                'email_port': 587,
                'email_use_tls': True,
                'email_use_ssl': False,
                'description': 'Google Gmail SMTP configuration'
            },
            {
                'name': 'Outlook/Hotmail SMTP',
                'email_host': 'smtp-mail.outlook.com',
                'email_port': 587,
                'email_use_tls': True,
                'email_use_ssl': False,
                'description': 'Microsoft Outlook/Hotmail SMTP configuration'
            },
            {
                'name': 'Yahoo Mail SMTP',
                'email_host': 'smtp.mail.yahoo.com',
                'email_port': 587,
                'email_use_tls': True,
                'email_use_ssl': False,
                'description': 'Yahoo Mail SMTP configuration'
            },
            {
                'name': 'SendGrid SMTP',
                'email_host': 'smtp.sendgrid.net',
                'email_port': 587,
                'email_use_tls': True,
                'email_use_ssl': False,
                'description': 'SendGrid email service SMTP configuration'
            },
            {
                'name': 'Mailgun SMTP',
                'email_host': 'smtp.mailgun.org',
                'email_port': 587,
                'email_use_tls': True,
                'email_use_ssl': False,
                'description': 'Mailgun email service SMTP configuration'
            }
        ]