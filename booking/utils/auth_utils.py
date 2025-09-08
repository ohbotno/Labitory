# booking/utils/auth_utils.py
"""
Authentication utilities for brute force protection and account security.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class BruteForceProtection:
    """
    Brute force protection utility class.
    """
    
    @staticmethod
    def get_cache_key(identifier, attempt_type='login'):
        """Generate cache key for tracking attempts."""
        return f"auth_attempts:{attempt_type}:{identifier}"
    
    @staticmethod
    def get_lockout_key(identifier, attempt_type='login'):
        """Generate cache key for account lockout."""
        return f"auth_lockout:{attempt_type}:{identifier}"
    
    @staticmethod
    def record_failed_attempt(identifier, attempt_type='login'):
        """
        Record a failed authentication attempt.
        
        Args:
            identifier: IP address, username, or email
            attempt_type: Type of attempt (login, password_reset, etc.)
        """
        if not getattr(settings, 'RATELIMIT_ENABLE', True):
            return False
            
        cache_key = BruteForceProtection.get_cache_key(identifier, attempt_type)
        lockout_key = BruteForceProtection.get_lockout_key(identifier, attempt_type)
        
        # Get current attempt count
        attempts = cache.get(cache_key, 0) + 1
        
        # Set attempt count with 15 minute expiry
        cache.set(cache_key, attempts, 900)  # 15 minutes
        
        # Check if lockout threshold reached
        max_attempts = getattr(settings, 'AUTH_MAX_FAILED_ATTEMPTS', 5)
        if attempts >= max_attempts:
            lockout_duration = getattr(settings, 'AUTH_LOCKOUT_DURATION', 1800)  # 30 minutes
            cache.set(lockout_key, True, lockout_duration)
            
            logger.warning(f"Account locked due to {attempts} failed {attempt_type} attempts: {identifier}")
            return True
            
        logger.info(f"Failed {attempt_type} attempt {attempts}/{max_attempts} for: {identifier}")
        return False
    
    @staticmethod
    def is_locked_out(identifier, attempt_type='login'):
        """
        Check if an identifier is currently locked out.
        
        Args:
            identifier: IP address, username, or email
            attempt_type: Type of attempt (login, password_reset, etc.)
            
        Returns:
            bool: True if locked out, False otherwise
        """
        if not getattr(settings, 'RATELIMIT_ENABLE', True):
            return False
            
        lockout_key = BruteForceProtection.get_lockout_key(identifier, attempt_type)
        return cache.get(lockout_key, False)
    
    @staticmethod
    def get_lockout_time_remaining(identifier, attempt_type='login'):
        """
        Get remaining lockout time in seconds.
        
        Args:
            identifier: IP address, username, or email
            attempt_type: Type of attempt
            
        Returns:
            int: Remaining seconds, 0 if not locked out
        """
        if not getattr(settings, 'RATELIMIT_ENABLE', True):
            return 0
            
        lockout_key = BruteForceProtection.get_lockout_key(identifier, attempt_type)
        
        # Check if locked out
        if not cache.get(lockout_key, False):
            return 0
            
        # Get TTL from cache
        try:
            return cache.ttl(lockout_key) or 0
        except AttributeError:
            # Fallback for cache backends without TTL support
            return getattr(settings, 'AUTH_LOCKOUT_DURATION', 1800)
    
    @staticmethod
    def clear_failed_attempts(identifier, attempt_type='login'):
        """
        Clear failed attempts for successful authentication.
        
        Args:
            identifier: IP address, username, or email
            attempt_type: Type of attempt
        """
        cache_key = BruteForceProtection.get_cache_key(identifier, attempt_type)
        lockout_key = BruteForceProtection.get_lockout_key(identifier, attempt_type)
        
        cache.delete(cache_key)
        cache.delete(lockout_key)
        
        logger.info(f"Cleared failed {attempt_type} attempts for: {identifier}")
    
    @staticmethod
    def get_failed_attempt_count(identifier, attempt_type='login'):
        """
        Get current failed attempt count.
        
        Args:
            identifier: IP address, username, or email
            attempt_type: Type of attempt
            
        Returns:
            int: Current attempt count
        """
        cache_key = BruteForceProtection.get_cache_key(identifier, attempt_type)
        return cache.get(cache_key, 0)


class AccountLockout:
    """
    Account lockout management for user accounts.
    """
    
    @staticmethod
    def lock_user_account(user, reason='multiple_failed_attempts', duration_minutes=30):
        """
        Lock a user account by setting is_active to False and recording the lockout.
        
        Args:
            user: User instance
            reason: Reason for lockout
            duration_minutes: Lockout duration in minutes
        """
        if not isinstance(user, User):
            return False
            
        # Don't lock superuser accounts
        if user.is_superuser:
            logger.warning(f"Attempted to lock superuser account: {user.username}")
            return False
        
        # Set lockout in cache
        lockout_key = f"user_lockout:{user.id}"
        lockout_until = timezone.now() + timedelta(minutes=duration_minutes)
        
        cache.set(lockout_key, {
            'locked_at': timezone.now().isoformat(),
            'locked_until': lockout_until.isoformat(),
            'reason': reason
        }, duration_minutes * 60)
        
        # Update user profile if available
        try:
            profile = user.userprofile
            profile.account_locked = True
            profile.locked_until = lockout_until
            profile.lock_reason = reason
            profile.save()
        except:
            pass
            
        logger.warning(f"User account locked: {user.username} for {duration_minutes} minutes. Reason: {reason}")
        return True
    
    @staticmethod
    def is_user_locked(user):
        """
        Check if a user account is currently locked.
        
        Args:
            user: User instance
            
        Returns:
            dict: Lockout info if locked, None if not locked
        """
        if not isinstance(user, User):
            return None
            
        lockout_key = f"user_lockout:{user.id}"
        lockout_info = cache.get(lockout_key)
        
        if lockout_info:
            return lockout_info
            
        # Check user profile
        try:
            profile = user.userprofile
            if profile.account_locked and profile.locked_until:
                if timezone.now() < profile.locked_until:
                    return {
                        'locked_until': profile.locked_until.isoformat(),
                        'reason': profile.lock_reason or 'Account locked'
                    }
                else:
                    # Lockout expired, clear it
                    profile.account_locked = False
                    profile.locked_until = None
                    profile.lock_reason = None
                    profile.save()
        except:
            pass
            
        return None
    
    @staticmethod
    def unlock_user_account(user):
        """
        Unlock a user account.
        
        Args:
            user: User instance
        """
        if not isinstance(user, User):
            return False
            
        # Clear from cache
        lockout_key = f"user_lockout:{user.id}"
        cache.delete(lockout_key)
        
        # Clear from profile
        try:
            profile = user.userprofile
            profile.account_locked = False
            profile.locked_until = None
            profile.lock_reason = None
            profile.save()
        except:
            pass
            
        # Clear failed attempts
        BruteForceProtection.clear_failed_attempts(user.username, 'login')
        BruteForceProtection.clear_failed_attempts(user.email, 'login')
        
        logger.info(f"User account unlocked: {user.username}")
        return True


def get_client_ip(request):
    """
    Get the client's IP address from request headers.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip


@receiver(user_login_failed)
def handle_failed_login(sender, credentials, request, **kwargs):
    """
    Signal handler for failed login attempts.
    Records failed attempts and implements lockout logic.
    """
    if not getattr(settings, 'RATELIMIT_ENABLE', True):
        return
        
    username = credentials.get('username', '')
    ip_address = get_client_ip(request)
    
    # Record failed attempt by IP
    ip_locked = BruteForceProtection.record_failed_attempt(ip_address, 'login')
    
    # Record failed attempt by username if provided
    username_locked = False
    if username:
        username_locked = BruteForceProtection.record_failed_attempt(username, 'login')
        
        # Check if we should lock the user account
        failed_attempts = BruteForceProtection.get_failed_attempt_count(username, 'login')
        max_attempts = getattr(settings, 'AUTH_MAX_FAILED_ATTEMPTS', 5)
        
        if failed_attempts >= max_attempts:
            try:
                user = User.objects.get(username=username)
                AccountLockout.lock_user_account(
                    user, 
                    reason='multiple_failed_login_attempts',
                    duration_minutes=getattr(settings, 'AUTH_LOCKOUT_DURATION', 1800) // 60
                )
            except User.DoesNotExist:
                pass
    
    logger.warning(f"Failed login attempt - IP: {ip_address}, Username: {username}")