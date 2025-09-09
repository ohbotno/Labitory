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
    
    def is_valid(self):
        """Check if session is still valid."""
        return timezone.now() < self.expires_at
    
    @classmethod
    def create_session(cls, user, session_key, ip_address=None, user_agent=''):
        """Create a new 2FA session."""
        expires_at = timezone.now() + timedelta(hours=12)  # 12-hour validity
        return cls.objects.create(
            user=user,
            session_key=session_key,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @classmethod
    def cleanup_expired(cls):
        """Remove expired sessions."""
        cls.objects.filter(expires_at__lt=timezone.now()).delete()
    
    def __str__(self):
        return f"2FA Session for {self.user.username} - Expires: {self.expires_at}"