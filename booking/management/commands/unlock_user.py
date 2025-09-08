# booking/management/commands/unlock_user.py
"""
Django management command to unlock user accounts.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from ...utils.auth_utils import AccountLockout, BruteForceProtection


class Command(BaseCommand):
    help = 'Unlock a user account that has been locked due to security reasons'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            type=str,
            help='Username of the account to unlock'
        )
        parser.add_argument(
            '--clear-attempts',
            action='store_true',
            help='Also clear failed login attempt counters'
        )

    def handle(self, *args, **options):
        username = options['username']
        
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist.')
        
        # Check if user is currently locked
        lockout_info = AccountLockout.is_user_locked(user)
        
        if not lockout_info:
            self.stdout.write(
                self.style.SUCCESS(f'User "{username}" is not currently locked.')
            )
            return
        
        # Unlock the account
        success = AccountLockout.unlock_user_account(user)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully unlocked user account: {username}')
            )
            
            # Clear failed attempts if requested
            if options['clear_attempts']:
                BruteForceProtection.clear_failed_attempts(username, 'login')
                BruteForceProtection.clear_failed_attempts(user.email, 'login')
                self.stdout.write(
                    self.style.SUCCESS('Cleared failed login attempt counters')
                )
        else:
            self.stdout.write(
                self.style.ERROR(f'Failed to unlock user account: {username}')
            )