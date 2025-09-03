# booking/management/commands/send_emergency_notification.py
"""
Send emergency notifications.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

from django.core.management.base import BaseCommand, CommandError
from booking.emergency_notifications import emergency_notification_system
from booking.models import Resource


class Command(BaseCommand):
    """Send emergency notifications."""
    
    help = 'Send emergency notifications to users'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'notification_type',
            choices=['system', 'resource', 'safety', 'evacuation', 'maintenance'],
            help='Type of emergency notification to send'
        )
        
        parser.add_argument(
            'title',
            help='Emergency notification title'
        )
        
        parser.add_argument(
            'message',
            help='Emergency notification message'
        )
        
        parser.add_argument(
            '--resource-ids',
            nargs='+',
            type=int,
            help='Resource IDs affected by the emergency (for resource/maintenance notifications)'
        )
        
        parser.add_argument(
            '--locations',
            nargs='+',
            help='Affected locations (for safety/evacuation notifications)'
        )
        
        parser.add_argument(
            '--duration',
            help='Estimated duration (for maintenance notifications)'
        )
        
        parser.add_argument(
            '--notify-users',
            action='store_true',
            help='Also notify regular users (for resource emergencies)'
        )
        
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm before sending (required for evacuation notices)'
        )
    
    def handle(self, *args, **options):
        """Send the emergency notification."""
        notification_type = options['notification_type']
        title = options['title']
        message = options['message']
        resource_ids = options.get('resource_ids', [])
        locations = options.get('locations', [])
        duration = options.get('duration')
        notify_users = options.get('notify_users', False)
        confirm = options.get('confirm', False)
        
        # Get resources if specified
        resources = []
        if resource_ids:
            try:
                resources = Resource.objects.filter(id__in=resource_ids)
                if len(resources) != len(resource_ids):
                    raise CommandError('One or more resource IDs not found')
            except Exception as e:
                raise CommandError(f'Error fetching resources: {e}')
        
        # Confirmation for critical notifications
        if notification_type == 'evacuation' and not confirm:
            raise CommandError('Evacuation notices require --confirm flag due to their critical nature')
        
        if notification_type in ['safety', 'evacuation'] and not locations:
            raise CommandError(f'{notification_type} notifications require --locations argument')
        
        if notification_type in ['resource', 'maintenance'] and not resources:
            raise CommandError(f'{notification_type} notifications require --resource-ids argument')
        
        # Send the notification
        try:
            sent_count = 0
            
            if notification_type == 'system':
                sent_count = emergency_notification_system.send_system_emergency(
                    title=title,
                    message=message,
                    affected_resources=resources if resources else None
                )
                
            elif notification_type == 'resource':
                for resource in resources:
                    sent_count += emergency_notification_system.send_resource_emergency(
                        resource=resource,
                        title=title,
                        message=message,
                        notify_users=notify_users
                    )
                    
            elif notification_type == 'safety':
                sent_count = emergency_notification_system.send_safety_alert(
                    title=title,
                    message=message,
                    affected_resources=resources if resources else None,
                    affected_locations=locations
                )
                
            elif notification_type == 'evacuation':
                sent_count = emergency_notification_system.send_evacuation_notice(
                    title=title,
                    message=message,
                    affected_locations=locations
                )
                
            elif notification_type == 'maintenance':
                sent_count = emergency_notification_system.send_maintenance_emergency(
                    title=title,
                    message=message,
                    resources=resources,
                    estimated_duration=duration
                )
            
            if sent_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully sent {notification_type} emergency notification to {sent_count} recipients'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING('No notifications were sent - check your parameters')
                )
                
        except Exception as e:
            raise CommandError(f'Failed to send emergency notification: {e}')
        
        # Show emergency contacts
        if notification_type in ['evacuation', 'safety']:
            self.stdout.write('\n' + self.style.WARNING('Emergency Contacts:'))
            contacts = emergency_notification_system.get_emergency_contact_list()
            for contact in contacts:
                self.stdout.write(f"  - {contact['name']} ({contact['role']}): {contact['email']}")
        
        self.stdout.write(
            self.style.SUCCESS(f'\nEmergency notification process completed for: {title}')
        )