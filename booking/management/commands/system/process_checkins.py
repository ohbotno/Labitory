# booking/management/commands/process_checkins.py
"""
Management command to process check-in/check-out reminders and automatic actions.

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
from booking.checkin_service import checkin_service


class Command(BaseCommand):
    help = 'Process check-in/check-out reminders and automatic actions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--action',
            type=str,
            choices=['reminders', 'auto-checkout', 'all'],
            default='all',
            help='Specify which action to perform',
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        dry_run = options['dry_run']
        action = options['action']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
        
        total_actions = 0
        
        if action in ['reminders', 'all']:
            total_actions += self.process_reminders(dry_run)
        
        if action in ['auto-checkout', 'all']:
            total_actions += self.process_auto_checkouts(dry_run)
        
        end_time = timezone.now()
        processing_time = (end_time - start_time).total_seconds()
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Dry run completed in {processing_time:.2f} seconds')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Processing completed in {processing_time:.2f} seconds - {total_actions} actions taken')
            )

    def process_reminders(self, dry_run=False):
        """Process check-in and check-out reminders."""
        self.stdout.write('📧 Processing reminders...')
        
        actions_taken = 0
        
        # Check-in reminders
        if dry_run:
            # Get bookings that would receive check-in reminders
            reminder_start = timezone.now() + timezone.timedelta(minutes=5)
            reminder_end = timezone.now() + timezone.timedelta(minutes=15)
            
            from booking.models import Booking
            checkin_reminders = Booking.objects.filter(
                start_time__gte=reminder_start,
                start_time__lte=reminder_end,
                checked_in_at__isnull=True,
                no_show=False,
                check_in_reminder_sent=False,
                status__in=['approved', 'confirmed']
            ).count()
            
            self.stdout.write(f'   Would send {checkin_reminders} check-in reminders')
            actions_taken += checkin_reminders
            
        else:
            checkin_reminders_sent = checkin_service.send_checkin_reminders()
            if checkin_reminders_sent > 0:
                self.stdout.write(f'   📬 Sent {checkin_reminders_sent} check-in reminders')
                actions_taken += checkin_reminders_sent
        
        # Check-out reminders
        if dry_run:
            # Get bookings that would receive check-out reminders
            reminder_start = timezone.now() + timezone.timedelta(minutes=5)
            reminder_end = timezone.now() + timezone.timedelta(minutes=15)
            
            checkout_reminders = Booking.objects.filter(
                end_time__gte=reminder_start,
                end_time__lte=reminder_end,
                checked_in_at__isnull=False,
                checked_out_at__isnull=True,
                check_out_reminder_sent=False,
                status__in=['approved', 'confirmed']
            ).count()
            
            self.stdout.write(f'   Would send {checkout_reminders} check-out reminders')
            actions_taken += checkout_reminders
            
        else:
            checkout_reminders_sent = checkin_service.send_checkout_reminders()
            if checkout_reminders_sent > 0:
                self.stdout.write(f'   📬 Sent {checkout_reminders_sent} check-out reminders')
                actions_taken += checkout_reminders_sent
        
        if not dry_run and actions_taken == 0:
            self.stdout.write('   No reminders needed')
        
        return actions_taken

    def process_auto_checkouts(self, dry_run=False):
        """Process automatic check-outs for overdue bookings."""
        self.stdout.write('🚪 Processing automatic check-outs...')
        
        if dry_run:
            overdue_bookings = checkin_service.get_overdue_checkouts()
            overdue_count = len(overdue_bookings)
            
            if overdue_count > 0:
                self.stdout.write(f'   Would auto check-out {overdue_count} overdue bookings:')
                for booking in overdue_bookings:
                    minutes_overdue = int((timezone.now() - booking.end_time).total_seconds() // 60)
                    self.stdout.write(
                        f'     - {booking.title} ({booking.resource.name}) - {minutes_overdue}min overdue'
                    )
            else:
                self.stdout.write('   No overdue check-outs found')
            
            return overdue_count
        
        else:
            checked_out_count = checkin_service.process_automatic_checkouts()
            
            if checked_out_count > 0:
                self.stdout.write(f'   🚪 Auto checked-out {checked_out_count} overdue bookings')
            else:
                self.stdout.write('   No overdue check-outs found')
            
            return checked_out_count

    def get_statistics(self):
        """Get and display current check-in/check-out statistics."""
        self.stdout.write('')
        self.stdout.write('📊 Current Statistics:')
        
        # Current check-ins
        current_checkins = checkin_service.get_current_checkins()
        self.stdout.write(f'   Currently checked in: {len(current_checkins)}')
        
        # Overdue check-ins
        overdue_checkins = checkin_service.get_overdue_checkins()
        self.stdout.write(f'   Overdue check-ins: {len(overdue_checkins)}')
        
        # Overdue check-outs
        overdue_checkouts = checkin_service.get_overdue_checkouts()
        self.stdout.write(f'   Overdue check-outs: {len(overdue_checkouts)}')
        
        # Today's usage analytics
        analytics = checkin_service.get_usage_analytics(
            start_date=timezone.now() - timezone.timedelta(days=1),
            end_date=timezone.now()
        )
        
        if analytics.get('total_bookings', 0) > 0:
            self.stdout.write('')
            self.stdout.write('📈 Today\'s Usage:')
            self.stdout.write(f'   Total bookings: {analytics.get("total_bookings", 0)}')
            self.stdout.write(f'   Completed: {analytics.get("completed_bookings", 0)}')
            self.stdout.write(f'   No shows: {analytics.get("no_show_bookings", 0)}')
            
            completion_rate = analytics.get('completion_rate', 0)
            self.stdout.write(f'   Completion rate: {completion_rate:.1f}%')
            
            avg_efficiency = analytics.get('avg_efficiency', 0)
            if avg_efficiency:
                self.stdout.write(f'   Average efficiency: {avg_efficiency:.1%}')

    def handle_with_stats(self, *args, **options):
        """Enhanced handle method with statistics display."""
        # Show initial statistics
        self.get_statistics()
        
        # Run the main processing
        self.handle(*args, **options)
        
        # Show final statistics if not dry run
        if not options.get('dry_run', False):
            self.get_statistics()