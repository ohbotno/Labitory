"""
Maintenance-related models for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
from .resources import Resource
from .bookings import Booking


class MaintenanceVendor(models.Model):
    """Vendors and service providers for maintenance."""
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    website = models.URLField(blank=True)
    
    # Vendor capabilities
    specialties = models.JSONField(default=list, help_text="Areas of expertise (e.g., electrical, mechanical)")
    certifications = models.JSONField(default=list, help_text="Relevant certifications")
    service_areas = models.JSONField(default=list, help_text="Geographic service areas")
    
    # Performance metrics
    average_response_time = models.DurationField(null=True, blank=True, help_text="Average response time for service calls")
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True, help_text="Vendor rating (1-5)")
    
    # Business details
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    emergency_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    contract_start_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'booking_maintenancevendor'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def contract_active(self):
        """Check if vendor contract is currently active."""
        if not self.contract_start_date or not self.contract_end_date:
            return True  # No contract dates = always active
        today = timezone.now().date()
        return self.contract_start_date <= today <= self.contract_end_date


class Maintenance(models.Model):
    """Enhanced maintenance schedules for resources with cost tracking and vendor management."""
    MAINTENANCE_TYPES = [
        ('preventive', 'Preventive Maintenance'),
        ('corrective', 'Corrective Maintenance'),
        ('emergency', 'Emergency Repair'),
        ('calibration', 'Calibration'),
        ('inspection', 'Inspection'),
        ('upgrade', 'Upgrade'),
        ('installation', 'Installation'),
        ('decommission', 'Decommission'),
    ]
    
    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
        ('emergency', 'Emergency'),
    ]
    
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('postponed', 'Postponed'),
        ('overdue', 'Overdue'),
    ]
    
    # Basic maintenance information
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='maintenances')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    maintenance_type = models.CharField(max_length=20, choices=MAINTENANCE_TYPES, default='preventive')
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    
    # Vendor and cost information
    vendor = models.ForeignKey(MaintenanceVendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenances')
    is_internal = models.BooleanField(default=True, help_text="Performed by internal staff")
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    actual_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    labor_hours = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    parts_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Recurrence and scheduling
    is_recurring = models.BooleanField(default=False)
    recurring_pattern = models.JSONField(null=True, blank=True)
    next_maintenance_date = models.DateTimeField(null=True, blank=True, help_text="When next maintenance is due")
    
    # Impact and dependencies
    blocks_booking = models.BooleanField(default=True)
    affects_other_resources = models.ManyToManyField(Resource, blank=True, related_name='affected_by_maintenance')
    prerequisite_maintenances = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='dependent_maintenances')
    
    # Completion tracking
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(blank=True)
    issues_found = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    
    # Audit fields
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_maintenances')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_maintenances')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_maintenances')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'booking_maintenance'
        ordering = ['start_time']
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')),
                name='maintenance_end_after_start'
            )
        ]

    def __str__(self):
        return f"{self.title} - {self.resource.name} ({self.start_time.strftime('%Y-%m-%d')})"

    def clean(self):
        """Validate maintenance schedule."""
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("End time must be after start time.")
        
        # Validate cost relationships
        if self.actual_cost and self.labor_hours and self.parts_cost:
            if self.vendor and self.vendor.hourly_rate:
                calculated_labor = self.labor_hours * self.vendor.hourly_rate
                expected_total = calculated_labor + self.parts_cost
                if abs(float(self.actual_cost) - float(expected_total)) > 0.01:
                    raise ValidationError("Actual cost should equal labor cost plus parts cost.")

    def save(self, *args, **kwargs):
        # Auto-calculate total cost if not provided
        if not self.actual_cost and self.labor_hours and self.parts_cost:
            if self.vendor and self.vendor.hourly_rate:
                labor_cost = self.labor_hours * self.vendor.hourly_rate
                self.actual_cost = labor_cost + self.parts_cost
        
        # Update status based on dates
        if self.status == 'scheduled':
            now = timezone.now()
            if self.start_time <= now <= self.end_time:
                self.status = 'in_progress'
            elif self.end_time < now and self.status != 'completed':
                self.status = 'overdue'
        
        # Set completion timestamp
        if self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()
        
        super().save(*args, **kwargs)

    def overlaps_with_booking(self, booking):
        """Check if maintenance overlaps with a booking."""
        return (self.start_time < booking.end_time and 
                self.end_time > booking.start_time)
    
    @property
    def duration(self):
        """Return maintenance duration as timedelta."""
        return self.end_time - self.start_time
    
    @property
    def is_overdue(self):
        """Check if maintenance is overdue."""
        return (self.status in ['scheduled', 'in_progress'] and 
                self.end_time < timezone.now())
    
    @property
    def cost_variance(self):
        """Calculate variance between estimated and actual cost."""
        if self.estimated_cost and self.actual_cost:
            return self.actual_cost - self.estimated_cost
        return None
    
    @property
    def cost_variance_percentage(self):
        """Calculate cost variance as percentage."""
        if self.estimated_cost and self.actual_cost and self.estimated_cost > 0:
            return ((self.actual_cost - self.estimated_cost) / self.estimated_cost) * 100
        return None
    
    def get_affected_bookings(self):
        """Get bookings that are affected by this maintenance."""
        if not self.blocks_booking:
            return Booking.objects.none()
        
        affected_resources = [self.resource] + list(self.affects_other_resources.all())
        return Booking.objects.filter(
            resource__in=affected_resources,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time,
            status__in=['pending', 'approved']
        )
    
    def calculate_impact_score(self):
        """Calculate impact score based on affected bookings and resource importance."""
        affected_bookings = self.get_affected_bookings().count()
        resource_usage = self.resource.bookings.filter(
            start_time__gte=timezone.now() - timedelta(days=30)
        ).count()
        
        # Base impact on number of affected bookings and recent usage
        impact_score = (affected_bookings * 2) + (resource_usage * 0.1)
        
        # Adjust for priority
        priority_multipliers = {
            'low': 0.5,
            'medium': 1.0,
            'high': 1.5,
            'critical': 2.0,
            'emergency': 3.0
        }
        
        return impact_score * priority_multipliers.get(self.priority, 1.0)


class MaintenanceDocument(models.Model):
    """Documentation and files related to maintenance activities."""
    maintenance = models.ForeignKey(Maintenance, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    document_type = models.CharField(max_length=50, choices=[
        ('manual', 'Service Manual'),
        ('checklist', 'Maintenance Checklist'),
        ('invoice', 'Invoice/Receipt'),
        ('report', 'Maintenance Report'),
        ('photo', 'Photograph'),
        ('certificate', 'Certificate'),
        ('warranty', 'Warranty Document'),
        ('other', 'Other'),
    ], default='other')
    
    file = models.FileField(upload_to='maintenance_docs/%Y/%m/')
    file_size = models.PositiveIntegerField(null=True, blank=True, help_text="File size in bytes")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # Document metadata
    tags = models.JSONField(default=list, help_text="Tags for categorization")
    is_public = models.BooleanField(default=False, help_text="Viewable by all users")
    version = models.CharField(max_length=20, blank=True, help_text="Document version")
    
    class Meta:
        db_table = 'booking_maintenancedocument'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.title} ({self.maintenance.title})"
    
    def save(self, *args, **kwargs):
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)


class MaintenanceAlert(models.Model):
    """Predictive maintenance alerts and notifications."""
    ALERT_TYPES = [
        ('due', 'Maintenance Due'),
        ('overdue', 'Maintenance Overdue'),
        ('cost_overrun', 'Cost Overrun'),
        ('vendor_performance', 'Vendor Performance Issue'),
        ('pattern_anomaly', 'Usage Pattern Anomaly'),
        ('predictive', 'Predictive Alert'),
        ('compliance', 'Compliance Reminder'),
    ]
    
    SEVERITY_LEVELS = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
        ('urgent', 'Urgent'),
    ]
    
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='maintenance_alerts')
    maintenance = models.ForeignKey(Maintenance, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS, default='info')
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    recommendation = models.TextField(blank=True, help_text="Recommended action")
    
    # Alert data
    alert_data = models.JSONField(default=dict, help_text="Additional alert context")
    threshold_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    actual_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Status tracking
    is_active = models.BooleanField(default=True)
    acknowledged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'booking_maintenancealert'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['resource', 'is_active']),
            models.Index(fields=['alert_type', 'severity']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.resource.name}"
    
    @property
    def is_expired(self):
        """Check if alert has expired."""
        return self.expires_at and timezone.now() > self.expires_at
    
    def acknowledge(self, user):
        """Acknowledge the alert."""
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        self.save()
    
    def resolve(self):
        """Mark alert as resolved."""
        self.resolved_at = timezone.now()
        self.is_active = False
        self.save()


class MaintenanceAnalytics(models.Model):
    """Analytics and metrics for maintenance activities."""
    resource = models.OneToOneField(Resource, on_delete=models.CASCADE, related_name='maintenance_analytics')
    
    # Cost metrics
    total_maintenance_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    average_maintenance_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    preventive_cost_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Percentage of costs from preventive maintenance")
    
    # Time metrics
    total_downtime_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    average_repair_time = models.DurationField(null=True, blank=True)
    planned_vs_unplanned_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Frequency metrics
    total_maintenance_count = models.PositiveIntegerField(default=0)
    preventive_maintenance_count = models.PositiveIntegerField(default=0)
    corrective_maintenance_count = models.PositiveIntegerField(default=0)
    emergency_maintenance_count = models.PositiveIntegerField(default=0)
    
    # Performance metrics
    first_time_fix_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Percentage of issues fixed on first attempt")
    mean_time_between_failures = models.DurationField(null=True, blank=True)
    mean_time_to_repair = models.DurationField(null=True, blank=True)
    
    # Vendor metrics
    vendor_performance_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    external_maintenance_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Prediction data
    next_failure_prediction = models.DateTimeField(null=True, blank=True)
    failure_probability = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    recommended_maintenance_interval = models.DurationField(null=True, blank=True)
    
    last_calculated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_maintenanceanalytics'
        verbose_name_plural = 'Maintenance Analytics'
    
    def __str__(self):
        return f"Analytics for {self.resource.name}"
    
    def calculate_metrics(self):
        """Recalculate all maintenance metrics for this resource."""
        maintenances = self.resource.maintenances.all()
        completed_maintenances = maintenances.filter(status='completed')
        
        if not completed_maintenances.exists():
            return
        
        # Cost metrics
        costs = completed_maintenances.exclude(actual_cost__isnull=True).values_list('actual_cost', flat=True)
        if costs:
            self.total_maintenance_cost = sum(costs)
            self.average_maintenance_cost = sum(costs) / len(costs)
        
        preventive_costs = completed_maintenances.filter(
            maintenance_type='preventive'
        ).exclude(actual_cost__isnull=True).aggregate(
            total=models.Sum('actual_cost')
        )['total'] or 0
        
        if self.total_maintenance_cost > 0:
            self.preventive_cost_ratio = (preventive_costs / self.total_maintenance_cost) * 100
        
        # Frequency metrics
        self.total_maintenance_count = maintenances.count()
        self.preventive_maintenance_count = maintenances.filter(maintenance_type='preventive').count()
        self.corrective_maintenance_count = maintenances.filter(maintenance_type='corrective').count()
        self.emergency_maintenance_count = maintenances.filter(maintenance_type='emergency').count()
        
        # Time metrics
        durations = []
        for maintenance in completed_maintenances:
            if maintenance.completed_at and maintenance.start_time:
                duration = maintenance.completed_at - maintenance.start_time
                durations.append(duration.total_seconds() / 3600)  # Convert to hours
        
        if durations:
            self.total_downtime_hours = sum(durations)
            avg_hours = sum(durations) / len(durations)
            self.average_repair_time = timedelta(hours=avg_hours)
        
        # Performance metrics
        # Simple first-time fix rate calculation
        if completed_maintenances.count() > 0:
            repeated_issues = 0
            for maintenance in completed_maintenances:
                # Check if there's another maintenance within 30 days for same type of issue
                related = completed_maintenances.filter(
                    maintenance_type=maintenance.maintenance_type,
                    start_time__gt=maintenance.completed_at,
                    start_time__lt=maintenance.completed_at + timedelta(days=30)
                ).exists()
                if related:
                    repeated_issues += 1
            
            self.first_time_fix_rate = ((completed_maintenances.count() - repeated_issues) / completed_maintenances.count()) * 100
        
        self.save()