"""
Management command to reset 2FA for users.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from booking.models import TwoFactorAuthentication, TwoFactorSession


class Command(BaseCommand):
    help = 'Reset two-factor authentication for a user'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            type=str,
            help='Username or email of the user'
        )
        parser.add_argument(
            '--disable',
            action='store_true',
            help='Disable 2FA for the user'
        )
        parser.add_argument(
            '--clear-sessions',
            action='store_true',
            help='Clear all 2FA sessions for the user'
        )
        parser.add_argument(
            '--reset-attempts',
            action='store_true',
            help='Reset failed attempt counter'
        )
        parser.add_argument(
            '--generate-codes',
            action='store_true',
            help='Generate new backup codes'
        )

    def handle(self, *args, **options):
        username = options['username']
        
        # Find user by username or email
        try:
            if '@' in username:
                user = User.objects.get(email=username)
            else:
                user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist')
        
        # Get or create 2FA record
        try:
            two_factor = user.two_factor_auth
        except TwoFactorAuthentication.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                f'User {user.username} does not have 2FA configured'
            ))
            return
        
        actions_taken = []
        
        # Disable 2FA if requested
        if options['disable']:
            two_factor.is_enabled = False
            two_factor.secret_key = ''
            two_factor.backup_codes = []
            two_factor.save()
            actions_taken.append('Disabled 2FA')
        
        # Clear 2FA sessions
        if options['clear_sessions']:
            count = TwoFactorSession.objects.filter(user=user).delete()[0]
            actions_taken.append(f'Cleared {count} 2FA sessions')
        
        # Reset failed attempts
        if options['reset_attempts']:
            two_factor.reset_failed_attempts()
            actions_taken.append('Reset failed attempt counter')
        
        # Generate new backup codes
        if options['generate_codes'] and two_factor.is_enabled:
            codes = two_factor.generate_backup_codes()
            actions_taken.append(f'Generated {len(codes)} new backup codes')
            
            # Display codes
            self.stdout.write('\nNew backup codes:')
            for i, code in enumerate(codes, 1):
                self.stdout.write(f'  {i}. {code}')
        
        if actions_taken:
            self.stdout.write(self.style.SUCCESS(
                f'\n2FA management for user {user.username}:\n' + 
                '\n'.join(f'  ✓ {action}' for action in actions_taken)
            ))
        else:
            self.stdout.write(self.style.WARNING(
                'No actions taken. Use --help to see available options.'
            ))