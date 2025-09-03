# booking/management/commands/run_maintenance_analysis.py
"""
Management command to run predictive maintenance analysis.

This command analyzes all resources for maintenance patterns, generates alerts,
and updates analytics data.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from booking.maintenance_service import maintenance_prediction_service
from booking.models import Resource, MaintenanceAlert


class Command(BaseCommand):
    help = 'Run predictive maintenance analysis for all resources'

    def add_arguments(self, parser):
        parser.add_argument(
            '--resource-id',
            type=int,
            help='Analyze specific resource by ID'
        )
        parser.add_argument(
            '--cleanup-alerts',
            action='store_true',
            help='Clean up old alerts after analysis'
        )
        parser.add_argument(
            '--days-ahead',
            type=int,
            default=30,
            help='Number of days to look ahead for predictions'
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        self.stdout.write('Starting maintenance analysis...')
        
        if options['resource_id']:
            # Analyze specific resource
            try:
                resource = Resource.objects.get(id=options['resource_id'])
                self.stdout.write(f'Analyzing resource: {resource.name}')
                
                analysis = maintenance_prediction_service.analyze_resource(resource)
                self._report_analysis(analysis)
                
            except Resource.DoesNotExist:
                self.stderr.write(f'Resource with ID {options["resource_id"]} not found')
                return
        else:
            # Analyze all resources
            self.stdout.write('Analyzing all resources...')
            
            analyses = maintenance_prediction_service.analyze_all_resources()
            
            total_alerts = 0
            total_resources = len(analyses)
            
            for analysis in analyses:
                alert_count = len(analysis['alerts'])
                total_alerts += alert_count
                
                if alert_count > 0:
                    self.stdout.write(
                        f'  {analysis["resource"].name}: {alert_count} alerts generated'
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Analysis complete: {total_resources} resources, {total_alerts} total alerts'
                )
            )
        
        # Clean up old alerts if requested
        if options['cleanup_alerts']:
            self.stdout.write('Cleaning up old alerts...')
            cleaned = maintenance_prediction_service.cleanup_old_alerts()
            self.stdout.write(f'Cleaned up {cleaned} old alerts')
        
        # Show summary of active alerts
        self._show_alert_summary()
        
        duration = timezone.now() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f'Maintenance analysis completed in {duration.total_seconds():.2f} seconds'
            )
        )

    def _report_analysis(self, analysis):
        """Report analysis results for a single resource."""
        resource = analysis['resource']
        alerts = analysis['alerts']
        predictions = analysis['predictions']
        recommendations = analysis['recommendations']
        
        self.stdout.write(f'\n--- Analysis for {resource.name} ---')
        
        # Report alerts
        if alerts:
            self.stdout.write(f'Alerts generated: {len(alerts)}')
            for alert in alerts:
                severity_style = {
                    'critical': self.style.ERROR,
                    'warning': self.style.WARNING,
                    'info': self.style.NOTICE,
                    'urgent': self.style.ERROR
                }.get(alert.severity, self.style.NOTICE)
                
                self.stdout.write(
                    f'  {severity_style(alert.severity.upper())}: {alert.title}'
                )
        else:
            self.stdout.write('No alerts generated')
        
        # Report predictions
        if predictions:
            self.stdout.write('Predictions:')
            if 'failure_probability' in predictions:
                prob = predictions['failure_probability']
                style = self.style.ERROR if prob > 0.7 else self.style.WARNING if prob > 0.4 else self.style.SUCCESS
                self.stdout.write(f'  Failure probability: {style(f"{prob:.1%}")}')
            
            if 'days_to_predicted_failure' in predictions:
                days = predictions['days_to_predicted_failure']
                self.stdout.write(f'  Predicted failure in: {days} days')
            
            if 'recommended_interval_days' in predictions:
                interval = predictions['recommended_interval_days']
                self.stdout.write(f'  Recommended maintenance interval: {interval} days')
        
        # Report recommendations
        if recommendations:
            self.stdout.write('Recommendations:')
            for rec in recommendations:
                priority_style = {
                    'high': self.style.ERROR,
                    'medium': self.style.WARNING,
                    'low': self.style.NOTICE
                }.get(rec['priority'], self.style.NOTICE)
                
                self.stdout.write(
                    f'  {priority_style(rec["priority"].upper())}: {rec["title"]}'
                )
                self.stdout.write(f'    {rec["description"]}')

    def _show_alert_summary(self):
        """Show summary of all active alerts."""
        self.stdout.write('\n--- Active Alert Summary ---')
        
        active_alerts = MaintenanceAlert.objects.filter(is_active=True)
        
        if not active_alerts.exists():
            self.stdout.write('No active alerts')
            return
        
        # Group by severity
        by_severity = {}
        for alert in active_alerts:
            if alert.severity not in by_severity:
                by_severity[alert.severity] = []
            by_severity[alert.severity].append(alert)
        
        for severity in ['critical', 'urgent', 'warning', 'info']:
            if severity in by_severity:
                count = len(by_severity[severity])
                severity_style = {
                    'critical': self.style.ERROR,
                    'urgent': self.style.ERROR,
                    'warning': self.style.WARNING,
                    'info': self.style.NOTICE
                }.get(severity, self.style.NOTICE)
                
                self.stdout.write(f'{severity_style(severity.upper())}: {count} alerts')
                
                # Show top 3 alerts for each severity
                for alert in by_severity[severity][:3]:
                    self.stdout.write(f'  - {alert.resource.name}: {alert.title}')
                
                if len(by_severity[severity]) > 3:
                    remaining = len(by_severity[severity]) - 3
                    self.stdout.write(f'  ... and {remaining} more')