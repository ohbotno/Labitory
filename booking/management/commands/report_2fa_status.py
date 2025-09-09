"""
Management command to report 2FA adoption status.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db.models import Count, Q, F
from django.utils import timezone
from datetime import timedelta
from booking.models import TwoFactorAuthentication, TwoFactorSession
from tabulate import tabulate


class Command(BaseCommand):
    help = 'Generate a report on 2FA adoption and usage'

    def add_arguments(self, parser):
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed user-level information'
        )
        parser.add_argument(
            '--export',
            type=str,
            help='Export report to CSV file'
        )
        parser.add_argument(
            '--role',
            type=str,
            choices=['student', 'lecturer', 'researcher', 'technician', 'admin', 'sysadmin'],
            help='Filter by user role'
        )

    def handle(self, *args, **options):
        # Get all users
        users = User.objects.filter(is_active=True)
        
        # Filter by role if specified
        if options['role']:
            users = users.filter(userprofile__role=options['role'])
        
        total_users = users.count()
        
        # Get 2FA statistics
        users_with_2fa = TwoFactorAuthentication.objects.filter(
            user__in=users,
            is_enabled=True
        ).count()
        
        users_without_2fa = total_users - users_with_2fa
        adoption_rate = (users_with_2fa / total_users * 100) if total_users > 0 else 0
        
        # Get usage statistics
        recent_usage = TwoFactorAuthentication.objects.filter(
            user__in=users,
            is_enabled=True,
            last_used_at__gte=timezone.now() - timedelta(days=30)
        ).count()
        
        # Get lockout statistics
        locked_accounts = TwoFactorAuthentication.objects.filter(
            user__in=users,
            failed_attempts__gte=5,
            last_failed_attempt__gte=timezone.now() - timedelta(minutes=30)
        ).count()
        
        # Display summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('2FA ADOPTION REPORT'))
        self.stdout.write('='*60)
        
        summary_data = [
            ['Total Active Users', total_users],
            ['Users with 2FA Enabled', f'{users_with_2fa} ({adoption_rate:.1f}%)'],
            ['Users without 2FA', users_without_2fa],
            ['Recently Used (30 days)', recent_usage],
            ['Currently Locked', locked_accounts],
        ]
        
        self.stdout.write('\n' + tabulate(summary_data, headers=['Metric', 'Value'], tablefmt='grid'))
        
        # Role-based breakdown
        self.stdout.write('\n' + self.style.SUCCESS('2FA Adoption by Role:'))
        role_data = []
        
        for role, role_name in [
            ('student', 'Students'),
            ('lecturer', 'Lecturers'),
            ('researcher', 'Researchers'),
            ('technician', 'Technicians'),
            ('admin', 'Admins'),
            ('sysadmin', 'System Admins'),
        ]:
            role_users = users.filter(userprofile__role=role)
            role_total = role_users.count()
            if role_total > 0:
                role_2fa = TwoFactorAuthentication.objects.filter(
                    user__in=role_users,
                    is_enabled=True
                ).count()
                role_rate = (role_2fa / role_total * 100)
                role_data.append([role_name, role_total, role_2fa, f'{role_rate:.1f}%'])
        
        if role_data:
            self.stdout.write('\n' + tabulate(
                role_data,
                headers=['Role', 'Total', 'With 2FA', 'Adoption'],
                tablefmt='grid'
            ))
        
        # Detailed user list if requested
        if options['detailed']:
            self.stdout.write('\n' + self.style.SUCCESS('Detailed User Status:'))
            
            user_data = []
            for user in users.select_related('userprofile'):
                try:
                    two_factor = user.two_factor_auth
                    if two_factor.is_enabled:
                        status = '✓ Enabled'
                        last_used = two_factor.last_used_at.strftime('%Y-%m-%d') if two_factor.last_used_at else 'Never'
                        backup_codes = len(two_factor.backup_codes)
                    else:
                        status = '✗ Disabled'
                        last_used = '-'
                        backup_codes = '-'
                except TwoFactorAuthentication.DoesNotExist:
                    status = '✗ Not Setup'
                    last_used = '-'
                    backup_codes = '-'
                
                role = getattr(user.userprofile, 'role', 'unknown')
                user_data.append([
                    user.username,
                    user.email,
                    role.title(),
                    status,
                    last_used,
                    backup_codes
                ])
            
            self.stdout.write('\n' + tabulate(
                user_data,
                headers=['Username', 'Email', 'Role', '2FA Status', 'Last Used', 'Backup Codes'],
                tablefmt='grid'
            ))
        
        # Export to CSV if requested
        if options['export']:
            import csv
            
            with open(options['export'], 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Username', 'Email', 'Role', '2FA Enabled', 'Last Used', 'Backup Codes'])
                
                for user in users.select_related('userprofile'):
                    try:
                        two_factor = user.two_factor_auth
                        enabled = 'Yes' if two_factor.is_enabled else 'No'
                        last_used = two_factor.last_used_at.isoformat() if two_factor.last_used_at else ''
                        backup_codes = len(two_factor.backup_codes) if two_factor.is_enabled else 0
                    except TwoFactorAuthentication.DoesNotExist:
                        enabled = 'No'
                        last_used = ''
                        backup_codes = 0
                    
                    role = getattr(user.userprofile, 'role', 'unknown')
                    writer.writerow([
                        user.username,
                        user.email,
                        role,
                        enabled,
                        last_used,
                        backup_codes
                    ])
            
            self.stdout.write(self.style.SUCCESS(f'\nReport exported to {options["export"]}'))