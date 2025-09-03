# booking/management/commands/generate_maintenance_schedule.py
"""
Management command to generate maintenance schedules for resources.

This command creates recommended maintenance schedules based on usage patterns,
maintenance history, and predictive analytics.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from booking.maintenance_service import maintenance_prediction_service
from booking.models import Resource, Maintenance


class Command(BaseCommand):
    help = 'Generate maintenance schedules for resources'

    def add_arguments(self, parser):
        parser.add_argument(
            '--resource-id',
            type=int,
            help='Generate schedule for specific resource by ID'
        )
        parser.add_argument(
            '--months-ahead',
            type=int,
            default=6,
            help='Number of months to schedule ahead (default: 6)'
        )
        parser.add_argument(
            '--create-schedules',
            action='store_true',
            help='Actually create maintenance entries (default: just preview)'
        )
        parser.add_argument(
            '--resource-type',
            type=str,
            help='Filter by resource type'
        )

    def handle(self, *args, **options):
        self.stdout.write('Generating maintenance schedules...')
        
        # Get resources to schedule
        if options['resource_id']:
            try:
                resources = [Resource.objects.get(id=options['resource_id'])]
            except Resource.DoesNotExist:
                self.stderr.write(f'Resource with ID {options["resource_id"]} not found')
                return
        else:
            resources = Resource.objects.all()
            if options['resource_type']:
                resources = resources.filter(resource_type__icontains=options['resource_type'])
        
        total_scheduled = 0
        months_ahead = options['months_ahead']
        create_actual = options['create_schedules']
        
        for resource in resources:
            self.stdout.write(f'\n--- Scheduling for {resource.name} ---')
            
            # Generate schedule
            schedule = maintenance_prediction_service.generate_maintenance_schedule(
                resource, months_ahead=months_ahead
            )
            
            if not schedule:
                self.stdout.write('  No maintenance needed based on current patterns')
                continue
            
            # Display schedule
            self.stdout.write(f'  Generated {len(schedule)} maintenance items:')
            
            for item in schedule:
                date_str = item['date'].strftime('%Y-%m-%d')
                duration_str = self._format_duration(item['estimated_duration'])
                priority_style = {
                    'high': self.style.ERROR,
                    'medium': self.style.WARNING,
                    'low': self.style.NOTICE
                }.get(item['priority'], self.style.NOTICE)
                
                self.stdout.write(
                    f'    {date_str}: {priority_style(item["type"].upper())} - {item["title"]} ({duration_str})'
                )
                
                if create_actual:
                    # Check if maintenance already exists for this date
                    existing = Maintenance.objects.filter(
                        resource=resource,
                        start_time__date=item['date'].date(),
                        maintenance_type=item['type']
                    ).first()
                    
                    if not existing:
                        # Create the maintenance entry
                        end_time = item['date'] + item['estimated_duration']
                        
                        maintenance = Maintenance.objects.create(
                            resource=resource,
                            title=item['title'],
                            description=item['description'],
                            start_time=item['date'],
                            end_time=end_time,
                            maintenance_type=item['type'],
                            priority=item['priority'],
                            status='scheduled',
                            is_internal=True,
                            created_by_id=1  # System user - you might want to make this configurable
                        )
                        
                        self.stdout.write(
                            f'      {self.style.SUCCESS("✓ Created")} maintenance entry'
                        )
                        total_scheduled += 1
                    else:
                        self.stdout.write(
                            f'      {self.style.WARNING("- Exists")} maintenance already scheduled'
                        )
        
        # Summary
        if create_actual:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nScheduling complete: {total_scheduled} new maintenance entries created'
                )
            )
        else:
            self.stdout.write(
                self.style.NOTICE(
                    f'\nPreview complete. Use --create-schedules to actually create entries.'
                )
            )
        
        # Show some statistics
        self._show_scheduling_stats(resources, months_ahead)

    def _format_duration(self, duration):
        """Format a timedelta for display."""
        hours = duration.total_seconds() / 3600
        if hours < 1:
            minutes = duration.total_seconds() / 60
            return f'{int(minutes)}min'
        elif hours < 24:
            return f'{hours:.1f}h'
        else:
            days = hours / 24
            return f'{days:.1f}d'

    def _show_scheduling_stats(self, resources, months_ahead):
        """Show scheduling statistics."""
        self.stdout.write('\n--- Scheduling Statistics ---')
        
        now = timezone.now()
        end_date = now + timedelta(days=months_ahead * 30)
        
        # Count existing scheduled maintenance
        existing_maintenance = Maintenance.objects.filter(
            resource__in=resources,
            start_time__gte=now,
            start_time__lte=end_date,
            status='scheduled'
        )
        
        by_type = {}
        by_priority = {}
        by_month = {}
        
        for maintenance in existing_maintenance:
            # By type
            mtype = maintenance.maintenance_type
            by_type[mtype] = by_type.get(mtype, 0) + 1
            
            # By priority
            priority = maintenance.priority
            by_priority[priority] = by_priority.get(priority, 0) + 1
            
            # By month
            month_key = maintenance.start_time.strftime('%Y-%m')
            by_month[month_key] = by_month.get(month_key, 0) + 1
        
        # Display statistics
        self.stdout.write(f'Total scheduled maintenance in next {months_ahead} months: {existing_maintenance.count()}')
        
        if by_type:
            self.stdout.write('\nBy Type:')
            for mtype, count in sorted(by_type.items()):
                self.stdout.write(f'  {mtype.title()}: {count}')
        
        if by_priority:
            self.stdout.write('\nBy Priority:')
            for priority, count in sorted(by_priority.items()):
                priority_style = {
                    'high': self.style.ERROR,
                    'critical': self.style.ERROR,
                    'emergency': self.style.ERROR,
                    'medium': self.style.WARNING,
                    'low': self.style.NOTICE
                }.get(priority, self.style.NOTICE)
                
                self.stdout.write(f'  {priority_style(priority.title())}: {count}')
        
        if by_month:
            self.stdout.write('\nBy Month:')
            for month, count in sorted(by_month.items()):
                self.stdout.write(f'  {month}: {count}')
        
        # Resource utilization
        resource_maintenance = {}
        for maintenance in existing_maintenance:
            resource = maintenance.resource
            if resource not in resource_maintenance:
                resource_maintenance[resource] = 0
            resource_maintenance[resource] += 1
        
        if resource_maintenance:
            self.stdout.write('\nTop Resources by Scheduled Maintenance:')
            sorted_resources = sorted(
                resource_maintenance.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            for resource, count in sorted_resources[:5]:
                self.stdout.write(f'  {resource.name}: {count} items')
        
        # Alert about high-maintenance resources
        high_maintenance_threshold = 5
        high_maintenance_resources = [
            resource for resource, count in resource_maintenance.items()
            if count >= high_maintenance_threshold
        ]
        
        if high_maintenance_resources:
            self.stdout.write(
                self.style.WARNING(
                    f'\nHigh-maintenance resources ({high_maintenance_threshold}+ items):'
                )
            )
            for resource in high_maintenance_resources:
                count = resource_maintenance[resource]
                self.stdout.write(f'  {resource.name}: {count} items')
                self.stdout.write('    Consider reviewing maintenance procedures or equipment condition')