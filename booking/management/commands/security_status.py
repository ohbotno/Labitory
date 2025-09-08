# booking/management/commands/security_status.py
"""
Django management command to check security status and locked accounts.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from ...utils.auth_utils import AccountLockout, BruteForceProtection


class Command(BaseCommand):
    help = 'Show security status including locked accounts and failed attempt statistics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--locked-only',
            action='store_true',
            help='Show only locked accounts'
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed security information'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Security Status Report')
        )
        self.stdout.write('=' * 50)
        
        # Show configuration
        self.show_security_config()
        
        # Show locked accounts
        self.show_locked_accounts(options['locked_only'])
        
        if options['detailed']:
            self.show_detailed_info()

    def show_security_config(self):
        """Display current security configuration."""
        self.stdout.write('')
        self.stdout.write('Security Configuration:')
        self.stdout.write('-' * 25)
        
        rate_limit_enabled = getattr(settings, 'RATELIMIT_ENABLE', True)
        max_attempts = getattr(settings, 'AUTH_MAX_FAILED_ATTEMPTS', 5)
        lockout_duration = getattr(settings, 'AUTH_LOCKOUT_DURATION', 1800)
        track_attempts = getattr(settings, 'AUTH_TRACK_FAILED_ATTEMPTS', True)
        
        self.stdout.write(f'  Rate Limiting Enabled: {rate_limit_enabled}')
        self.stdout.write(f'  Max Failed Attempts: {max_attempts}')
        self.stdout.write(f'  Lockout Duration: {lockout_duration // 60} minutes')
        self.stdout.write(f'  Track Failed Attempts: {track_attempts}')

    def show_locked_accounts(self, locked_only=False):
        """Display information about locked accounts."""
        self.stdout.write('')
        self.stdout.write('Account Status:')
        self.stdout.write('-' * 15)
        
        all_users = User.objects.all().order_by('username')
        locked_count = 0
        total_count = 0
        
        for user in all_users:
            total_count += 1
            lockout_info = AccountLockout.is_user_locked(user)
            
            if lockout_info:
                locked_count += 1
                self.stdout.write(
                    self.style.ERROR(f'  LOCKED: {user.username} ({user.email})')
                )
                if 'reason' in lockout_info:
                    self.stdout.write(f'    Reason: {lockout_info["reason"]}')
                if 'locked_until' in lockout_info:
                    self.stdout.write(f'    Until: {lockout_info["locked_until"]}')
            elif not locked_only:
                # Check if user has recent failed attempts
                failed_attempts = BruteForceProtection.get_failed_attempt_count(user.username, 'login')
                if failed_attempts > 0:
                    self.stdout.write(
                        self.style.WARNING(f'  WARNING: {user.username} - {failed_attempts} failed attempts')
                    )
                else:
                    self.stdout.write(f'  OK: {user.username}')
        
        self.stdout.write('')
        self.stdout.write(f'Summary: {locked_count} locked accounts out of {total_count} total users')

    def show_detailed_info(self):
        """Show detailed security information."""
        self.stdout.write('')
        self.stdout.write('Detailed Security Information:')
        self.stdout.write('-' * 30)
        
        # Check cache backend
        try:
            cache_backend = settings.CACHES['default']['BACKEND']
            self.stdout.write(f'  Cache Backend: {cache_backend}')
            
            # Test cache functionality
            test_key = 'security_status_test'
            cache.set(test_key, 'test_value', 60)
            test_result = cache.get(test_key)
            cache.delete(test_key)
            
            if test_result == 'test_value':
                self.stdout.write('  Cache Status: Working')
            else:
                self.stdout.write(
                    self.style.WARNING('  Cache Status: Not working properly')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  Cache Status: Error - {e}')
            )
        
        # Show recent failed attempts by IP
        self.stdout.write('')
        self.stdout.write('Recent Failed Login Attempts by IP:')
        
        # Note: This would require scanning cache keys, which isn't easily portable
        # across different cache backends. For now, just show that the feature exists.
        self.stdout.write('  (Use system logs or cache inspection tools for detailed IP statistics)')
        
        # Show users with failed attempts tracked in profile
        users_with_failures = User.objects.filter(
            userprofile__failed_login_attempts__gt=0
        ).select_related('userprofile')
        
        if users_with_failures:
            self.stdout.write('')
            self.stdout.write('Users with Recent Failed Attempts:')
            for user in users_with_failures:
                profile = user.userprofile
                self.stdout.write(
                    f'  {user.username}: {profile.failed_login_attempts} attempts'
                )
                if profile.last_failed_login:
                    self.stdout.write(f'    Last failed: {profile.last_failed_login}')
        
        self.stdout.write('')
        self.stdout.write('Rate Limiting Settings:')
        login_attempts = getattr(settings, 'RATELIMIT_LOGIN_ATTEMPTS', 5)
        api_requests = getattr(settings, 'RATELIMIT_API_REQUESTS', 100)
        booking_requests = getattr(settings, 'RATELIMIT_BOOKING_REQUESTS', 10)
        password_reset = getattr(settings, 'RATELIMIT_PASSWORD_RESET', 3)
        
        self.stdout.write(f'  Login Attempts: {login_attempts}/15min')
        self.stdout.write(f'  API Requests: {api_requests}/hour')
        self.stdout.write(f'  Booking Requests: {booking_requests}/15min')
        self.stdout.write(f'  Password Reset: {password_reset}/hour')