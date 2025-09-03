# booking/management/commands/process_waiting_lists.py
"""
Management command to process waiting lists and send availability notifications.

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
from booking.models import Resource, WaitingListEntry
from booking.waiting_list import waiting_list_service


class Command(BaseCommand):
    help = 'Process waiting lists and send availability notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--resource',
            type=int,
            help='Process waiting list for specific resource ID only',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up expired waiting list entries',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        
        if options['cleanup']:
            self.cleanup_expired_entries(options['dry_run'])
        
        if options['resource']:
            self.process_specific_resource(options['resource'], options['dry_run'])
        else:
            self.process_all_resources(options['dry_run'])
        
        end_time = timezone.now()
        processing_time = (end_time - start_time).total_seconds()
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Waiting list processing completed in {processing_time:.2f} seconds')
        )

    def cleanup_expired_entries(self, dry_run=False):
        """Clean up expired waiting list entries."""
        self.stdout.write('🧹 Cleaning up expired waiting list entries...')
        
        if dry_run:
            expired_count = WaitingListEntry.objects.filter(
                status='active',
                expires_at__lt=timezone.now()
            ).count()
            self.stdout.write(f'   Would mark {expired_count} entries as expired')
        else:
            expired_count = waiting_list_service.cleanup_expired_entries()
            self.stdout.write(f'   Marked {expired_count} entries as expired')

    def process_specific_resource(self, resource_id, dry_run=False):
        """Process waiting list for a specific resource."""
        try:
            resource = Resource.objects.get(id=resource_id)
            self.stdout.write(f'🔄 Processing waiting list for {resource.name}...')
            
            if dry_run:
                # Get active waiting list entries
                active_entries = WaitingListEntry.objects.filter(
                    resource=resource,
                    status='active'
                ).count()
                
                # Get available slots
                available_slots = waiting_list_service.check_availability_for_waiting_list(resource)
                
                self.stdout.write(f'   {active_entries} active waiting list entries')
                self.stdout.write(f'   {len(available_slots)} available time slots')
                self.stdout.write('   Would send notifications (dry run)')
            else:
                notifications_sent = waiting_list_service.process_waiting_list_for_resource(resource)
                self.stdout.write(f'   📬 Sent {notifications_sent} availability notifications')
                
        except Resource.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'❌ Resource with ID {resource_id} not found')
            )

    def process_all_resources(self, dry_run=False):
        """Process waiting lists for all resources with active entries."""
        self.stdout.write('🔄 Processing waiting lists for all resources...')
        
        # Get resources with active waiting list entries
        resources_with_waiting_lists = Resource.objects.filter(
            waiting_list__status='active'
        ).distinct()
        
        total_notifications = 0
        processed_resources = 0
        
        for resource in resources_with_waiting_lists:
            active_entries = resource.waiting_list.filter(status='active').count()
            
            if active_entries > 0:
                self.stdout.write(f'   🏷️  {resource.name}: {active_entries} waiting')
                
                if dry_run:
                    available_slots = waiting_list_service.check_availability_for_waiting_list(resource)
                    self.stdout.write(f'      {len(available_slots)} available slots (would process)')
                else:
                    notifications_sent = waiting_list_service.process_waiting_list_for_resource(resource)
                    if notifications_sent > 0:
                        self.stdout.write(f'      📬 {notifications_sent} notifications sent')
                        total_notifications += notifications_sent
                    else:
                        self.stdout.write('      No matching availability found')
                
                processed_resources += 1
        
        if not dry_run:
            self.stdout.write('')
            self.stdout.write(f'📊 Summary:')
            self.stdout.write(f'   Resources processed: {processed_resources}')
            self.stdout.write(f'   Total notifications sent: {total_notifications}')
        else:
            self.stdout.write('')
            self.stdout.write(f'📊 Dry run summary:')
            self.stdout.write(f'   Resources with waiting lists: {processed_resources}')
            self.stdout.write('   (No actual notifications sent)')

    def get_waiting_list_statistics(self):
        """Get overall waiting list statistics."""
        stats = waiting_list_service.get_waiting_list_statistics()
        
        self.stdout.write('')
        self.stdout.write('📈 Waiting List Statistics:')
        self.stdout.write(f'   Active entries: {stats["total_active"]}')
        self.stdout.write(f'   Notified entries: {stats["total_notified"]}')
        self.stdout.write(f'   Fulfilled entries: {stats["total_fulfilled"]}')
        self.stdout.write(f'   Expired entries: {stats["total_expired"]}')
        self.stdout.write(f'   Cancelled entries: {stats["total_cancelled"]}')
        
        if stats["avg_wait_time_hours"] > 0:
            self.stdout.write(f'   Average wait time: {stats["avg_wait_time_hours"]:.1f} hours')

    def handle_with_stats(self, *args, **options):
        """Enhanced handle method with statistics display."""
        # Show initial statistics
        self.get_waiting_list_statistics()
        
        # Run the main processing
        self.handle(*args, **options)
        
        # Show final statistics
        self.get_waiting_list_statistics()