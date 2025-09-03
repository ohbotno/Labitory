# booking/management/commands/send_notifications.py
"""
Management command to send pending notifications.

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
from datetime import timedelta
from booking.notifications import notification_service, booking_notifications
from booking.models import Booking


class Command(BaseCommand):
    help = 'Send pending notifications and booking reminders'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-reminders',
            action='store_true',
            help='Send booking reminders for upcoming bookings',
        )
        parser.add_argument(
            '--reminder-hours',
            type=int,
            default=24,
            help='Hours ahead to send reminders (default: 24)',
        )

    def handle(self, *args, **options):
        # Send pending notifications
        sent_count = notification_service.send_pending_notifications()
        self.stdout.write(
            self.style.SUCCESS(f'Sent {sent_count} pending notifications')
        )

        # Send booking reminders if requested
        if options['send_reminders']:
            reminder_count = self.send_booking_reminders(options['reminder_hours'])
            self.stdout.write(
                self.style.SUCCESS(f'Sent {reminder_count} booking reminders')
            )

    def send_booking_reminders(self, hours_ahead):
        """Send reminders for bookings starting soon."""
        now = timezone.now()
        reminder_time = now + timedelta(hours=hours_ahead)
        
        # Find confirmed bookings starting within the reminder window
        upcoming_bookings = Booking.objects.filter(
            status='confirmed',
            start_time__gte=now,
            start_time__lte=reminder_time,
            # Avoid sending duplicate reminders
            notifications__notification_type='booking_reminder',
            notifications__created_at__gte=now - timedelta(hours=1)
        ).exclude(
            notifications__notification_type='booking_reminder'
        ).select_related('user', 'resource')

        reminder_count = 0
        for booking in upcoming_bookings:
            try:
                booking_notifications.booking_reminder(booking, hours_ahead)
                reminder_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Failed to send reminder for booking {booking.id}: {str(e)}')
                )

        return reminder_count