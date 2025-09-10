"""
Authentication-related models for the Labitory.

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
from django.utils import timezone
from datetime import timedelta
import uuid
import secrets
import string


class PasswordResetToken(models.Model):
    """Password reset tokens for users."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'booking_passwordresettoken'
    
    def is_expired(self):
        """Check if token is expired (1 hour)."""
        return timezone.now() > self.created_at + timedelta(hours=1)
    
    def __str__(self):
        return f"Password reset token for {self.user.username}"


class EmailVerificationToken(models.Model):
    """Email verification tokens for user registration."""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'booking_emailverificationtoken'
    
    def is_expired(self):
        """Check if token is expired (24 hours)."""
        return timezone.now() > self.created_at + timedelta(hours=24)
    
    def __str__(self):
        return f"Verification token for {self.user.username}"


class TwoFactorAuthentication(models.Model):
    """Two-Factor Authentication settings for users."""
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='two_factor_auth'
    )
    is_enabled = models.BooleanField(default=False)
    secret_key = models.CharField(max_length=32, blank=True)
    backup_codes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    
    # Recovery settings
    recovery_email = models.EmailField(blank=True)
    recovery_phone = models.CharField(max_length=20, blank=True)
    
    # Security tracking
    failed_attempts = models.IntegerField(default=0)
    last_failed_attempt = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'booking_twofactorauthentication'
        verbose_name = 'Two-Factor Authentication'
        verbose_name_plural = 'Two-Factor Authentications'
    
    def generate_backup_codes(self, count=10):
        """Generate backup codes for recovery."""
        codes = []
        for _ in range(count):
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) 
                          for _ in range(8))
            codes.append(code)
        self.backup_codes = codes
        self.save()
        return codes
    
    def use_backup_code(self, code):
        """Use a backup code (one-time use)."""
        if code in self.backup_codes:
            self.backup_codes.remove(code)
            self.last_used_at = timezone.now()
            self.save()
            return True
        return False
    
    def reset_failed_attempts(self):
        """Reset failed attempt counter."""
        self.failed_attempts = 0
        self.last_failed_attempt = None
        self.save()
    
    def increment_failed_attempts(self):
        """Increment failed attempt counter."""
        self.failed_attempts += 1
        self.last_failed_attempt = timezone.now()
        self.save()
    
    def is_locked(self):
        """Check if 2FA is locked due to failed attempts."""
        if self.failed_attempts >= 5:
            if self.last_failed_attempt:
                lockout_duration = timedelta(minutes=30)
                if timezone.now() < self.last_failed_attempt + lockout_duration:
                    return True
                else:
                    self.reset_failed_attempts()
        return False
    
    def __str__(self):
        return f"2FA for {self.user.username} - {'Enabled' if self.is_enabled else 'Disabled'}"


class TwoFactorSession(models.Model):
    """Track 2FA verification sessions."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session_key = models.CharField(max_length=40)
    verified_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        db_table = 'booking_twofactorsession'
        indexes = [
            models.Index(fields=['user', 'session_key']),
            models.Index(fields=['expires_at']),
        ]
    
    def is_expired(self):
        """Check if session is expired."""
        return timezone.now() > self.expires_at
    
    def __str__(self):
        return f"2FA session for {self.user.username}"


class APIToken(models.Model):
    """API tokens for JWT authentication with rotation support."""
    
    TOKEN_TYPES = [
        ('access', 'Access Token'),
        ('refresh', 'Refresh Token'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_tokens')
    jti = models.CharField(max_length=50, unique=True, db_index=True)  # JWT ID
    token_type = models.CharField(max_length=10, choices=TOKEN_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata for security tracking
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'booking_apitoken'
        indexes = [
            models.Index(fields=['jti']),
            models.Index(fields=['user', 'token_type']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['is_revoked']),
        ]
        verbose_name = 'API Token'
        verbose_name_plural = 'API Tokens'
    
    def is_expired(self):
        """Check if token is expired."""
        return timezone.now() > self.expires_at
    
    def revoke(self):
        """Revoke the token."""
        self.is_revoked = True
        self.revoked_at = timezone.now()
        self.save()
    
    def is_valid(self):
        """Check if token is valid (not expired and not revoked)."""
        return not self.is_expired() and not self.is_revoked
    
    def update_usage(self, ip_address=None, user_agent=None):
        """Update token usage metadata."""
        self.last_used_at = timezone.now()
        if ip_address:
            self.ip_address = ip_address
        if user_agent:
            self.user_agent = user_agent
        self.save()
    
    def __str__(self):
        return f"{self.get_token_type_display()} for {self.user.username} ({'Revoked' if self.is_revoked else 'Active'})"


class SecurityEvent(models.Model):
    """Track security-related events for monitoring."""
    
    EVENT_TYPES = [
        ('login_attempt', 'Login Attempt'),
        ('failed_login', 'Failed Login'),
        ('password_change', 'Password Change'),
        ('2fa_enabled', '2FA Enabled'),
        ('2fa_disabled', '2FA Disabled'),
        ('token_created', 'API Token Created'),
        ('token_revoked', 'API Token Revoked'),
        ('suspicious_activity', 'Suspicious Activity'),
        ('account_locked', 'Account Locked'),
        ('permission_denied', 'Permission Denied'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Additional context data
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'booking_securityevent'
        indexes = [
            models.Index(fields=['user', 'event_type']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['event_type', 'timestamp']),
            models.Index(fields=['ip_address']),
        ]
        verbose_name = 'Security Event'
        verbose_name_plural = 'Security Events'
    
    def __str__(self):
        user_info = f"{self.user.username}" if self.user else "Anonymous"
        return f"{self.get_event_type_display()} - {user_info} at {self.timestamp}"