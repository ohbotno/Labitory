# booking/management/commands/fix_naive_datetimes.py
"""
Fix naive datetimes in the database.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from booking.models import Booking, Maintenance
import warnings


class Command(BaseCommand):
    """Fix naive datetimes in the database."""
    
    help = 'Fix naive datetime fields in the database by making them timezone-aware'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes'
        )
        
        parser.add_argument(
            '--suppress-warnings',
            action='store_true',
            help='Suppress naive datetime warnings during operation'
        )
    
    def handle(self, *args, **options):
        """Fix naive datetimes."""
        dry_run = options['dry_run']
        suppress_warnings = options['suppress_warnings']
        
        if suppress_warnings:
            warnings.filterwarnings('ignore', message='.*received a naive datetime.*')
        
        self.stdout.write('Checking for naive datetimes in the database...')
        
        fixed_count = 0
        
        with transaction.atomic():
            # Fix Booking datetimes
            self.stdout.write('Checking Booking records...')
            bookings_to_fix = []
            
            for booking in Booking.objects.all():
                needs_fix = False
                
                if booking.start_time and timezone.is_naive(booking.start_time):
                    needs_fix = True
                    if not dry_run:
                        booking.start_time = timezone.make_aware(booking.start_time)
                
                if booking.end_time and timezone.is_naive(booking.end_time):
                    needs_fix = True
                    if not dry_run:
                        booking.end_time = timezone.make_aware(booking.end_time)
                
                if needs_fix:
                    bookings_to_fix.append(booking)
                    if not dry_run:
                        booking.save(update_fields=['start_time', 'end_time'])
            
            if bookings_to_fix:
                self.stdout.write(
                    self.style.WARNING(f'Found {len(bookings_to_fix)} Booking records with naive datetimes')
                )
                if not dry_run:
                    self.stdout.write(
                        self.style.SUCCESS(f'Fixed {len(bookings_to_fix)} Booking records')
                    )
                fixed_count += len(bookings_to_fix)
            
            # Fix Maintenance datetimes
            self.stdout.write('Checking Maintenance records...')
            maintenance_to_fix = []
            
            for maintenance in Maintenance.objects.all():
                needs_fix = False
                
                if maintenance.start_time and timezone.is_naive(maintenance.start_time):
                    needs_fix = True
                    if not dry_run:
                        maintenance.start_time = timezone.make_aware(maintenance.start_time)
                
                if maintenance.end_time and timezone.is_naive(maintenance.end_time):
                    needs_fix = True
                    if not dry_run:
                        maintenance.end_time = timezone.make_aware(maintenance.end_time)
                
                if needs_fix:
                    maintenance_to_fix.append(maintenance)
                    if not dry_run:
                        maintenance.save(update_fields=['start_time', 'end_time'])
            
            if maintenance_to_fix:
                self.stdout.write(
                    self.style.WARNING(f'Found {len(maintenance_to_fix)} Maintenance records with naive datetimes')
                )
                if not dry_run:
                    self.stdout.write(
                        self.style.SUCCESS(f'Fixed {len(maintenance_to_fix)} Maintenance records')
                    )
                fixed_count += len(maintenance_to_fix)
            
            if dry_run and fixed_count > 0:
                self.stdout.write(
                    self.style.WARNING(f'DRY RUN: Would fix {fixed_count} records. Run without --dry-run to apply fixes.')
                )
                # Rollback transaction in dry run
                transaction.set_rollback(True)
            elif fixed_count == 0:
                self.stdout.write(
                    self.style.SUCCESS('No naive datetimes found. Database is already clean!')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully fixed {fixed_count} records with naive datetimes')
                )
        
        # Provide recommendations
        if fixed_count > 0 or dry_run:
            self.stdout.write('\n' + self.style.WARNING('Recommendations to prevent future naive datetime issues:'))
            self.stdout.write('1. Always use timezone.now() instead of datetime.now()')
            self.stdout.write('2. Use timezone.make_aware() for user-input datetimes')
            self.stdout.write('3. Check forms and APIs that accept datetime input')
            self.stdout.write('4. Consider adding validation in model save() methods')
        
        self.stdout.write('\nTimezone fix operation completed.')