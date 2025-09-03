# booking/maintenance_service.py
"""
Maintenance prediction and analytics service for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

from django.utils import timezone
from django.db.models import Q, Count, Sum, Avg
from datetime import datetime, timedelta
from collections import defaultdict
import logging
from .models import (
    Resource, Maintenance, MaintenanceAlert, MaintenanceAnalytics, 
    MaintenanceVendor, Booking
)

logger = logging.getLogger(__name__)


class MaintenancePredictionService:
    """Service for predictive maintenance analysis and alerts."""
    
    def __init__(self):
        self.alert_thresholds = {
            'usage_hours_per_week': 40,  # Alert if usage exceeds 40 hours/week
            'cost_increase_percentage': 25,  # Alert if costs increase by 25%
            'failure_probability': 0.7,  # Alert if failure probability > 70%
            'overdue_days': 7,  # Alert if maintenance overdue by 7+ days
            'vendor_response_hours': 48,  # Alert if vendor response > 48 hours
        }
    
    def analyze_all_resources(self):
        """Run predictive analysis for all resources."""
        results = []
        
        for resource in Resource.objects.all():
            try:
                analysis = self.analyze_resource(resource)
                if analysis:
                    results.append(analysis)
            except Exception as e:
                logger.error(f"Error analyzing resource {resource.id}: {e}")
        
        return results
    
    def analyze_resource(self, resource):
        """Perform comprehensive analysis for a single resource."""
        analysis = {
            'resource': resource,
            'alerts': [],
            'predictions': {},
            'recommendations': []
        }
        
        # Get or create analytics object
        analytics, created = MaintenanceAnalytics.objects.get_or_create(resource=resource)
        if created or not analytics.last_calculated or \
           analytics.last_calculated < timezone.now() - timedelta(hours=24):
            analytics.calculate_metrics()
        
        # Check usage patterns
        usage_alerts = self._analyze_usage_patterns(resource)
        analysis['alerts'].extend(usage_alerts)
        
        # Check maintenance patterns
        maintenance_alerts = self._analyze_maintenance_patterns(resource)
        analysis['alerts'].extend(maintenance_alerts)
        
        # Check cost trends
        cost_alerts = self._analyze_cost_trends(resource)
        analysis['alerts'].extend(cost_alerts)
        
        # Check vendor performance
        vendor_alerts = self._analyze_vendor_performance(resource)
        analysis['alerts'].extend(vendor_alerts)
        
        # Generate predictions
        analysis['predictions'] = self._generate_predictions(resource, analytics)
        
        # Generate recommendations
        analysis['recommendations'] = self._generate_recommendations(resource, analytics)
        
        return analysis
    
    def _analyze_usage_patterns(self, resource):
        """Analyze resource usage patterns for anomalies."""
        alerts = []
        now = timezone.now()
        
        # Check recent usage (last 4 weeks)
        recent_bookings = resource.bookings.filter(
            start_time__gte=now - timedelta(weeks=4),
            status__in=['confirmed', 'completed']
        )
        
        weekly_usage = defaultdict(float)
        for booking in recent_bookings:
            week = booking.start_time.isocalendar()[1]
            duration_hours = (booking.end_time - booking.start_time).total_seconds() / 3600
            weekly_usage[week] += duration_hours
        
        # Check for excessive usage
        for week, hours in weekly_usage.items():
            if hours > self.alert_thresholds['usage_hours_per_week']:
                alert = self._create_alert(
                    resource=resource,
                    alert_type='pattern_anomaly',
                    severity='warning',
                    title=f"High Usage Week {week}",
                    message=f"Resource usage was {hours:.1f} hours in week {week}, exceeding normal patterns.",
                    recommendation="Consider scheduling preventive maintenance to prevent wear.",
                    threshold_value=self.alert_thresholds['usage_hours_per_week'],
                    actual_value=hours
                )
                alerts.append(alert)
        
        # Check for booking concentration (too many bookings in short period)
        daily_bookings = defaultdict(int)
        for booking in recent_bookings:
            day = booking.start_time.date()
            daily_bookings[day] += 1
        
        max_daily_bookings = max(daily_bookings.values()) if daily_bookings else 0
        if max_daily_bookings > 8:  # More than 8 bookings per day
            alert = self._create_alert(
                resource=resource,
                alert_type='pattern_anomaly',
                severity='info',
                title="High Booking Density",
                message=f"Resource had {max_daily_bookings} bookings in a single day.",
                recommendation="Monitor for signs of overuse and consider usage limits.",
                actual_value=max_daily_bookings
            )
            alerts.append(alert)
        
        return alerts
    
    def _analyze_maintenance_patterns(self, resource):
        """Analyze maintenance patterns and schedules."""
        alerts = []
        now = timezone.now()
        
        # Check for overdue maintenance
        overdue_maintenance = resource.maintenances.filter(
            status__in=['scheduled', 'in_progress'],
            end_time__lt=now - timedelta(days=self.alert_thresholds['overdue_days'])
        )
        
        for maintenance in overdue_maintenance:
            days_overdue = (now - maintenance.end_time).days
            alert = self._create_alert(
                resource=resource,
                maintenance=maintenance,
                alert_type='overdue',
                severity='critical' if days_overdue > 14 else 'warning',
                title=f"Maintenance Overdue: {maintenance.title}",
                message=f"Maintenance has been overdue for {days_overdue} days.",
                recommendation="Complete maintenance immediately to prevent equipment damage.",
                threshold_value=self.alert_thresholds['overdue_days'],
                actual_value=days_overdue
            )
            alerts.append(alert)
        
        # Check maintenance frequency
        recent_maintenance = resource.maintenances.filter(
            completed_at__gte=now - timedelta(days=90),
            status='completed'
        )
        
        emergency_count = recent_maintenance.filter(maintenance_type='emergency').count()
        if emergency_count > 2:
            alert = self._create_alert(
                resource=resource,
                alert_type='pattern_anomaly',
                severity='warning',
                title="Frequent Emergency Maintenance",
                message=f"{emergency_count} emergency maintenance events in the last 90 days.",
                recommendation="Review preventive maintenance schedule and resource condition.",
                actual_value=emergency_count
            )
            alerts.append(alert)
        
        # Check for missing preventive maintenance
        last_preventive = resource.maintenances.filter(
            maintenance_type='preventive',
            status='completed'
        ).order_by('-completed_at').first()
        
        if last_preventive:
            days_since_preventive = (now - last_preventive.completed_at).days
            if days_since_preventive > 180:  # 6 months
                alert = self._create_alert(
                    resource=resource,
                    alert_type='due',
                    severity='warning',
                    title="Preventive Maintenance Due",
                    message=f"Last preventive maintenance was {days_since_preventive} days ago.",
                    recommendation="Schedule preventive maintenance to maintain equipment reliability.",
                    threshold_value=180,
                    actual_value=days_since_preventive
                )
                alerts.append(alert)
        
        return alerts
    
    def _analyze_cost_trends(self, resource):
        """Analyze maintenance cost trends."""
        alerts = []
        now = timezone.now()
        
        # Compare recent costs to historical average
        recent_period = now - timedelta(days=90)
        historical_period = now - timedelta(days=365)
        
        recent_costs = resource.maintenances.filter(
            completed_at__gte=recent_period,
            status='completed',
            actual_cost__isnull=False
        ).aggregate(total=Sum('actual_cost'))['total'] or 0
        
        historical_costs = resource.maintenances.filter(
            completed_at__gte=historical_period,
            completed_at__lt=recent_period,
            status='completed',
            actual_cost__isnull=False
        ).aggregate(avg=Avg('actual_cost'))['avg'] or 0
        
        if historical_costs > 0:
            # Annualize recent costs for comparison
            recent_annual = float(recent_costs) * (365 / 90)
            cost_increase = ((recent_annual - float(historical_costs)) / float(historical_costs)) * 100
            
            if cost_increase > self.alert_thresholds['cost_increase_percentage']:
                alert = self._create_alert(
                    resource=resource,
                    alert_type='cost_overrun',
                    severity='warning',
                    title="Rising Maintenance Costs",
                    message=f"Maintenance costs have increased by {cost_increase:.1f}% compared to historical average.",
                    recommendation="Review maintenance procedures and consider equipment replacement.",
                    threshold_value=self.alert_thresholds['cost_increase_percentage'],
                    actual_value=cost_increase
                )
                alerts.append(alert)
        
        return alerts
    
    def _analyze_vendor_performance(self, resource):
        """Analyze vendor performance issues."""
        alerts = []
        now = timezone.now()
        
        # Check vendor response times
        vendor_maintenance = resource.maintenances.filter(
            vendor__isnull=False,
            created_at__gte=now - timedelta(days=90),
            status__in=['completed', 'in_progress']
        ).select_related('vendor')
        
        vendor_performance = defaultdict(list)
        for maintenance in vendor_maintenance:
            if maintenance.status == 'completed' and maintenance.completed_at:
                response_time = (maintenance.completed_at - maintenance.created_at).total_seconds() / 3600
                vendor_performance[maintenance.vendor].append(response_time)
        
        for vendor, response_times in vendor_performance.items():
            avg_response = sum(response_times) / len(response_times)
            if avg_response > float(self.alert_thresholds['vendor_response_hours']):
                alert = self._create_alert(
                    resource=resource,
                    alert_type='vendor_performance',
                    severity='info',
                    title=f"Slow Vendor Response: {vendor.name}",
                    message=f"Average response time is {avg_response:.1f} hours.",
                    recommendation="Discuss response time expectations with vendor or consider alternatives.",
                    threshold_value=self.alert_thresholds['vendor_response_hours'],
                    actual_value=avg_response
                )
                alerts.append(alert)
        
        return alerts
    
    def _generate_predictions(self, resource, analytics):
        """Generate predictive maintenance recommendations."""
        predictions = {}
        now = timezone.now()
        
        # Predict next failure based on maintenance history
        completed_maintenance = resource.maintenances.filter(
            status='completed',
            maintenance_type__in=['corrective', 'emergency']
        ).order_by('completed_at')
        
        if completed_maintenance.count() >= 3:
            # Simple prediction based on average time between failures
            failure_intervals = []
            prev_maintenance = None
            
            for maintenance in completed_maintenance:
                if prev_maintenance:
                    interval = (maintenance.completed_at - prev_maintenance.completed_at).days
                    failure_intervals.append(interval)
                prev_maintenance = maintenance
            
            if failure_intervals:
                avg_interval = sum(failure_intervals) / len(failure_intervals)
                last_failure = completed_maintenance.last().completed_at
                next_failure_prediction = last_failure + timedelta(days=avg_interval)
                
                # Calculate failure probability based on time since last failure
                days_since_failure = (now - last_failure).days
                failure_probability = min(days_since_failure / avg_interval, 1.0)
                
                predictions['next_failure_date'] = next_failure_prediction
                predictions['failure_probability'] = failure_probability
                predictions['days_to_predicted_failure'] = (next_failure_prediction - now).days
                
                # Update analytics
                analytics.next_failure_prediction = next_failure_prediction
                analytics.failure_probability = failure_probability * 100
                analytics.save()
        
        # Predict optimal maintenance interval
        preventive_maintenance = resource.maintenances.filter(
            status='completed',
            maintenance_type='preventive'
        ).order_by('completed_at')
        
        if preventive_maintenance.count() >= 2:
            intervals = []
            prev_maintenance = None
            
            for maintenance in preventive_maintenance:
                if prev_maintenance:
                    interval = (maintenance.completed_at - prev_maintenance.completed_at).days
                    intervals.append(interval)
                prev_maintenance = maintenance
            
            if intervals:
                avg_interval = sum(intervals) / len(intervals)
                last_preventive = preventive_maintenance.last().completed_at
                next_recommended = last_preventive + timedelta(days=avg_interval)
                
                predictions['next_preventive_recommended'] = next_recommended
                predictions['recommended_interval_days'] = avg_interval
                
                # Update analytics
                analytics.recommended_maintenance_interval = timedelta(days=avg_interval)
                analytics.save()
        
        return predictions
    
    def _generate_recommendations(self, resource, analytics):
        """Generate maintenance recommendations based on analysis."""
        recommendations = []
        now = timezone.now()
        
        # Recommendation based on failure probability
        if analytics.failure_probability > self.alert_thresholds['failure_probability'] * 100:
            recommendations.append({
                'type': 'urgent',
                'title': 'Schedule Immediate Inspection',
                'description': f'Failure probability is {analytics.failure_probability:.1f}%. Schedule immediate inspection.',
                'priority': 'high'
            })
        
        # Recommendation based on cost trends
        if analytics.preventive_cost_ratio < 60:  # Less than 60% preventive
            recommendations.append({
                'type': 'cost_optimization',
                'title': 'Increase Preventive Maintenance',
                'description': f'Only {analytics.preventive_cost_ratio:.1f}% of costs are from preventive maintenance. Increase preventive maintenance to reduce overall costs.',
                'priority': 'medium'
            })
        
        # Recommendation based on vendor performance
        if analytics.external_maintenance_ratio > 70:
            recommendations.append({
                'type': 'vendor_management',
                'title': 'Review Vendor Dependency',
                'description': f'{analytics.external_maintenance_ratio:.1f}% of maintenance is external. Consider increasing internal capabilities.',
                'priority': 'low'
            })
        
        # Recommendation based on downtime
        if analytics.total_downtime_hours > 100:
            recommendations.append({
                'type': 'availability',
                'title': 'Reduce Downtime',
                'description': f'Total downtime is {analytics.total_downtime_hours:.1f} hours. Focus on reducing maintenance duration.',
                'priority': 'medium'
            })
        
        return recommendations
    
    def _create_alert(self, resource, alert_type, severity, title, message, 
                     recommendation, maintenance=None, threshold_value=None, 
                     actual_value=None, expires_hours=168):
        """Create a maintenance alert."""
        
        # Check if similar alert already exists
        existing_alert = MaintenanceAlert.objects.filter(
            resource=resource,
            alert_type=alert_type,
            title=title,
            is_active=True
        ).first()
        
        if existing_alert:
            # Update existing alert instead of creating duplicate
            existing_alert.message = message
            existing_alert.recommendation = recommendation
            existing_alert.actual_value = actual_value
            existing_alert.save()
            return existing_alert
        
        # Create new alert
        alert = MaintenanceAlert.objects.create(
            resource=resource,
            maintenance=maintenance,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            recommendation=recommendation,
            threshold_value=threshold_value,
            actual_value=actual_value,
            expires_at=timezone.now() + timedelta(hours=expires_hours)
        )
        
        return alert
    
    def generate_maintenance_schedule(self, resource, months_ahead=6):
        """Generate recommended maintenance schedule for a resource."""
        schedule = []
        now = timezone.now()
        end_date = now + timedelta(days=months_ahead * 30)
        
        # Get analytics for this resource
        try:
            analytics = resource.maintenance_analytics
        except MaintenanceAnalytics.DoesNotExist:
            analytics = MaintenanceAnalytics.objects.create(resource=resource)
            analytics.calculate_metrics()
        
        # Schedule preventive maintenance
        if analytics.recommended_maintenance_interval:
            interval_days = analytics.recommended_maintenance_interval.days
            
            # Find last preventive maintenance
            last_preventive = resource.maintenances.filter(
                maintenance_type='preventive',
                status='completed'
            ).order_by('-completed_at').first()
            
            start_date = last_preventive.completed_at if last_preventive else now
            current_date = start_date + timedelta(days=interval_days)
            
            while current_date <= end_date:
                schedule.append({
                    'date': current_date,
                    'type': 'preventive',
                    'title': f'Preventive Maintenance - {resource.name}',
                    'estimated_duration': timedelta(hours=4),
                    'priority': 'medium',
                    'description': 'Scheduled preventive maintenance based on historical patterns'
                })
                current_date += timedelta(days=interval_days)
        
        # Schedule inspections based on usage
        recent_usage = resource.bookings.filter(
            start_time__gte=now - timedelta(days=30),
            status__in=['confirmed', 'completed']
        ).count()
        
        if recent_usage > 20:  # High usage resource
            # Schedule monthly inspections
            current_date = now + timedelta(days=30)
            while current_date <= end_date:
                schedule.append({
                    'date': current_date,
                    'type': 'inspection',
                    'title': f'Monthly Inspection - {resource.name}',
                    'estimated_duration': timedelta(hours=1),
                    'priority': 'low',
                    'description': 'Regular inspection for high-usage resource'
                })
                current_date += timedelta(days=30)
        
        # Schedule calibration if resource type suggests it
        if 'calibration' in resource.resource_type.lower() or 'measurement' in resource.resource_type.lower():
            # Schedule quarterly calibration
            current_date = now + timedelta(days=90)
            while current_date <= end_date:
                schedule.append({
                    'date': current_date,
                    'type': 'calibration',
                    'title': f'Calibration - {resource.name}',
                    'estimated_duration': timedelta(hours=2),
                    'priority': 'high',
                    'description': 'Quarterly calibration to maintain accuracy'
                })
                current_date += timedelta(days=90)
        
        return sorted(schedule, key=lambda x: x['date'])
    
    def cleanup_old_alerts(self, days=30):
        """Clean up old, resolved alerts."""
        cutoff_date = timezone.now() - timedelta(days=days)
        
        deleted_count = MaintenanceAlert.objects.filter(
            Q(resolved_at__lt=cutoff_date) | Q(expires_at__lt=timezone.now()),
            is_active=False
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old maintenance alerts")
        return deleted_count


# Initialize the service
maintenance_prediction_service = MaintenancePredictionService()