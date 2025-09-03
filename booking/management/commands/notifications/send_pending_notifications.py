# booking/management/commands/send_pending_notifications.py
"""
Send pending notifications.

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
from booking.notifications import notification_service


class Command(BaseCommand):
    """Send pending notifications."""
    
    help = 'Send all pending notifications (for use in cron jobs)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum number of notifications to process'
        )
        
        parser.add_argument(
            '--send-digest',
            action='store_true',
            help='Also send digest notifications'
        )
        
        parser.add_argument(
            '--digest-frequency',
            type=str,
            choices=['daily_digest', 'weekly_digest'],
            default='daily_digest',
            help='Digest frequency to send'
        )
        
        parser.add_argument(
            '--send-escalations',
            action='store_true',
            help='Also send escalation notifications for overdue requests'
        )
    
    def handle(self, *args, **options):
        """Send pending notifications."""
        limit = options['limit']
        send_digest = options['send_digest']
        digest_frequency = options['digest_frequency']
        send_escalations = options['send_escalations']
        
        # Send immediate notifications
        self.stdout.write('Processing pending notifications...')
        sent_count = notification_service.send_pending_notifications()
        
        if sent_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully sent {sent_count} notifications')
            )
        else:
            self.stdout.write('No pending notifications to send')
        
        # Send digest notifications if requested
        if send_digest:
            self.stdout.write(f'Processing {digest_frequency} notifications...')
            try:
                notification_service.send_digest_notifications(digest_frequency)
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully sent {digest_frequency} notifications')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error sending digest notifications: {e}')
                )
        
        # Send escalation notifications if requested
        if send_escalations:
            self.stdout.write('Processing escalation notifications...')
            try:
                escalated_count = notification_service.send_escalation_notifications()
                if escalated_count > 0:
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully sent {escalated_count} escalation notifications')
                    )
                else:
                    self.stdout.write('No escalation notifications needed')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error sending escalation notifications: {e}')
                )
        
        self.stdout.write(self.style.SUCCESS('Notification processing complete'))