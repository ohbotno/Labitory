"""
Billing models for the Labitory.

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
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
import calendar


class BillingPeriod(models.Model):
    """Defines billing periods for resource usage charging."""
    PERIOD_TYPES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
        ('custom', 'Custom Period'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('draft', 'Draft'),
    ]
    
    name = models.CharField(max_length=100, help_text="e.g., 'January 2025' or 'Q1 2025'")
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES, default='monthly')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Billing configuration
    is_current = models.BooleanField(default=False, help_text="Only one period can be current at a time")
    auto_close_date = models.DateTimeField(null=True, blank=True, help_text="When to automatically close this period")
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_billing_periods')
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_billing_periods')
    
    class Meta:
        db_table = 'booking_billingperiod'
        ordering = ['-start_date']
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gt=models.F('start_date')),
                name='billing_period_end_after_start'
            )
        ]
    
    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"
    
    def clean(self):
        """Validate billing period constraints."""
        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError("End date must be after start date.")
        
        # Only one current period allowed
        if self.is_current:
            current_periods = BillingPeriod.objects.filter(is_current=True)
            if self.pk:
                current_periods = current_periods.exclude(pk=self.pk)
            if current_periods.exists():
                raise ValidationError("Only one billing period can be current at a time.")
    
    def save(self, *args, **kwargs):
        self.full_clean()
        
        # If setting as current, unset all others
        if self.is_current:
            BillingPeriod.objects.filter(is_current=True).update(is_current=False)
        
        super().save(*args, **kwargs)
    
    @classmethod
    def get_current_period(cls):
        """Get the currently active billing period."""
        return cls.objects.filter(is_current=True, status='active').first()
    
    @classmethod
    def get_period_for_date(cls, date):
        """Get the billing period that contains a specific date."""
        return cls.objects.filter(
            start_date__lte=date,
            end_date__gte=date
        ).first()
    
    @classmethod
    def create_monthly_period(cls, year, month, user=None):
        """Create a monthly billing period."""
        start_date = timezone.datetime(year, month, 1).date()
        _, last_day = calendar.monthrange(year, month)
        end_date = timezone.datetime(year, month, last_day).date()
        
        month_name = calendar.month_name[month]
        name = f"{month_name} {year}"
        
        return cls.objects.create(
            name=name,
            period_type='monthly',
            start_date=start_date,
            end_date=end_date,
            created_by=user
        )
    
    def close_period(self, user=None):
        """Close this billing period."""
        self.status = 'closed'
        self.closed_at = timezone.now()
        self.closed_by = user
        self.is_current = False
        self.save()
    
    @property
    def is_closed(self):
        """Check if this period is closed."""
        return self.status == 'closed'
    
    @property
    def total_charges(self):
        """Get total charges for this billing period."""
        return self.billing_records.aggregate(
            total=models.Sum('total_charge')
        )['total'] or Decimal('0.00')
    
    @property
    def total_hours(self):
        """Get total billable hours for this period."""
        return self.billing_records.aggregate(
            total=models.Sum('billable_hours')
        )['total'] or Decimal('0.00')


class BillingRate(models.Model):
    """Defines billing rates for resources with various configurations."""
    RATE_TYPES = [
        ('standard', 'Standard Rate'),
        ('peak', 'Peak Hours Rate'),
        ('off_peak', 'Off-Peak Hours Rate'),
        ('weekend', 'Weekend Rate'),
        ('holiday', 'Holiday Rate'),
    ]
    
    USER_TYPE_CHOICES = [
        ('all', 'All Users'),
        ('student', 'Students'),
        ('researcher', 'Researchers'),
        ('academic', 'Academics'),
        ('technician', 'Technicians'),
        ('external', 'External Users'),
    ]
    
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, related_name='billing_rates')
    rate_type = models.CharField(max_length=20, choices=RATE_TYPES, default='standard')
    
    # Rate configuration
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, help_text="Rate per hour")
    minimum_charge_minutes = models.PositiveIntegerField(default=0, help_text="Minimum billable time in minutes")
    rounding_minutes = models.PositiveIntegerField(default=1, help_text="Round billing to nearest X minutes")
    
    # Conditions for applying this rate
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='all')
    department = models.ForeignKey('Department', on_delete=models.CASCADE, null=True, blank=True, 
                                  help_text="Apply to specific department only (optional)")
    
    # Time-based conditions
    applies_from_time = models.TimeField(null=True, blank=True, help_text="Start time for this rate (e.g., 09:00 for peak)")
    applies_to_time = models.TimeField(null=True, blank=True, help_text="End time for this rate (e.g., 17:00 for peak)")
    applies_weekdays_only = models.BooleanField(default=False, help_text="Only apply on weekdays")
    applies_weekends_only = models.BooleanField(default=False, help_text="Only apply on weekends")
    
    # Validity period
    valid_from = models.DateField(default=timezone.now)
    valid_until = models.DateField(null=True, blank=True, help_text="Leave blank for no expiry")
    
    # Priority for rate selection
    priority = models.PositiveIntegerField(default=1, help_text="Higher number = higher priority")
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_billing_rates')
    
    class Meta:
        db_table = 'booking_billingrate'
        ordering = ['-priority', 'rate_type']
    
    def __str__(self):
        conditions = []
        if self.user_type != 'all':
            conditions.append(self.get_user_type_display())
        if self.department:
            conditions.append(f"Dept: {self.department.name}")
        if self.applies_from_time and self.applies_to_time:
            conditions.append(f"{self.applies_from_time}-{self.applies_to_time}")
        
        condition_str = f" ({', '.join(conditions)})" if conditions else ""
        return f"{self.resource.name} - £{self.hourly_rate}/hr ({self.get_rate_type_display()}){condition_str}"
    
    def clean(self):
        """Validate billing rate constraints."""
        if self.applies_weekdays_only and self.applies_weekends_only:
            raise ValidationError("Cannot apply to both weekdays only and weekends only.")
        
        if self.valid_until and self.valid_from >= self.valid_until:
            raise ValidationError("Valid until date must be after valid from date.")
        
        if self.rounding_minutes <= 0:
            raise ValidationError("Rounding minutes must be greater than 0.")
    
    def is_applicable(self, booking, usage_datetime):
        """Check if this rate applies to a specific booking and usage time."""
        # Check if rate is active and valid for the date
        if not self.is_active:
            return False
        
        usage_date = usage_datetime.date()
        if usage_date < self.valid_from:
            return False
        if self.valid_until and usage_date > self.valid_until:
            return False
        
        # Check user type
        try:
            user_role = booking.user.userprofile.role
            if self.user_type != 'all' and user_role != self.user_type:
                return False
        except:
            if self.user_type != 'all':
                return False
        
        # Check department
        if self.department:
            try:
                user_dept = booking.user.userprofile.department
                if user_dept != self.department:
                    return False
            except:
                return False
        
        # Check day of week
        is_weekend = usage_datetime.weekday() >= 5  # Saturday=5, Sunday=6
        if self.applies_weekdays_only and is_weekend:
            return False
        if self.applies_weekends_only and not is_weekend:
            return False
        
        # Check time of day
        usage_time = usage_datetime.time()
        if self.applies_from_time and usage_time < self.applies_from_time:
            return False
        if self.applies_to_time and usage_time > self.applies_to_time:
            return False
        
        return True
    
    def calculate_charge(self, duration_minutes):
        """Calculate charge for a given duration in minutes."""
        # Apply minimum charge
        billable_minutes = max(duration_minutes, self.minimum_charge_minutes)
        
        # Round to nearest rounding_minutes
        if self.rounding_minutes > 1:
            remainder = billable_minutes % self.rounding_minutes
            if remainder > 0:
                billable_minutes = billable_minutes + (self.rounding_minutes - remainder)
        
        # Calculate charge
        billable_hours = Decimal(billable_minutes) / Decimal('60')
        total_charge = (billable_hours * self.hourly_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        return {
            'billable_minutes': billable_minutes,
            'billable_hours': billable_hours,
            'total_charge': total_charge,
            'rate_applied': self.hourly_rate
        }
    
    @classmethod
    def get_applicable_rate(cls, resource, booking, usage_datetime):
        """Get the best applicable rate for a booking at a specific time."""
        rates = cls.objects.filter(
            resource=resource,
            is_active=True
        ).order_by('-priority', '-created_at')
        
        for rate in rates:
            if rate.is_applicable(booking, usage_datetime):
                return rate
        
        return None


class BillingRecord(models.Model):
    """Individual billing record for a resource usage session."""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('billed', 'Billed'),
        ('disputed', 'Disputed'),
        ('adjusted', 'Adjusted'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Core relationships
    booking = models.OneToOneField('Booking', on_delete=models.CASCADE, related_name='billing_record')
    billing_period = models.ForeignKey(BillingPeriod, on_delete=models.CASCADE, related_name='billing_records')
    billing_rate = models.ForeignKey(BillingRate, on_delete=models.SET_NULL, null=True, related_name='billing_records')
    
    # Usage details
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, related_name='billing_records')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='billing_records')
    department = models.ForeignKey('Department', on_delete=models.CASCADE, null=True, blank=True, related_name='billing_records')
    
    # Project/grant information (for advanced billing)
    project_code = models.CharField(max_length=50, blank=True, help_text="Project or grant code to charge")
    cost_center = models.CharField(max_length=50, blank=True, help_text="Cost center code")
    
    # Time tracking
    session_start = models.DateTimeField(help_text="When resource usage actually started")
    session_end = models.DateTimeField(help_text="When resource usage actually ended")
    duration_minutes = models.PositiveIntegerField(help_text="Actual usage duration in minutes")
    
    # Billing calculations
    billable_minutes = models.PositiveIntegerField(help_text="Billable minutes after rounding and minimums")
    billable_hours = models.DecimalField(max_digits=8, decimal_places=2, help_text="Billable hours (minutes/60)")
    hourly_rate_applied = models.DecimalField(max_digits=8, decimal_places=2, help_text="Rate used for calculation")
    total_charge = models.DecimalField(max_digits=10, decimal_places=2, help_text="Total charge amount")
    
    # Status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='confirmed_billing_records')
    
    # Adjustment tracking
    original_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                        help_text="Original charge before adjustments")
    adjustment_reason = models.TextField(blank=True, help_text="Reason for any charge adjustments")
    adjusted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='adjusted_billing_records')
    adjusted_at = models.DateTimeField(null=True, blank=True)
    
    # Notes and metadata
    notes = models.TextField(blank=True)
    billing_metadata = models.JSONField(default=dict, blank=True, help_text="Additional billing information")
    
    class Meta:
        db_table = 'booking_billingrecord'
        ordering = ['-session_start']
        indexes = [
            models.Index(fields=['billing_period', 'department']),
            models.Index(fields=['user', 'session_start']),
            models.Index(fields=['resource', 'session_start']),
            models.Index(fields=['status', 'billing_period']),
        ]
    
    def __str__(self):
        return f"{self.resource.name} - {self.user.get_full_name()} - {self.session_start.date()} (£{self.total_charge})"
    
    def clean(self):
        """Validate billing record constraints."""
        if self.session_start and self.session_end:
            if self.session_start >= self.session_end:
                raise ValidationError("Session end must be after session start.")
            
            # Validate duration calculation
            calculated_duration = int((self.session_end - self.session_start).total_seconds() / 60)
            if abs(self.duration_minutes - calculated_duration) > 1:  # Allow 1 minute tolerance
                raise ValidationError("Duration minutes doesn't match session start/end times.")
    
    @classmethod
    def create_from_booking(cls, booking):
        """Create a billing record from a completed booking."""
        if not booking.actual_start_time or not booking.actual_end_time:
            raise ValueError("Booking must have actual start and end times")
        
        if not booking.resource.is_billable:
            raise ValueError("Resource is not billable")
        
        # Get billing period
        billing_period = BillingPeriod.get_period_for_date(booking.actual_start_time.date())
        if not billing_period:
            raise ValueError("No billing period found for booking date")
        
        # Get applicable billing rate
        billing_rate = BillingRate.get_applicable_rate(
            booking.resource, booking, booking.actual_start_time
        )
        if not billing_rate:
            raise ValueError("No applicable billing rate found")
        
        # Calculate duration
        duration = booking.actual_end_time - booking.actual_start_time
        duration_minutes = int(duration.total_seconds() / 60)
        
        # Calculate charges
        charge_info = billing_rate.calculate_charge(duration_minutes)
        
        # Get user's department
        try:
            department = booking.user.userprofile.department
        except:
            department = None
        
        # Create billing record
        billing_record = cls(
            booking=booking,
            billing_period=billing_period,
            billing_rate=billing_rate,
            resource=booking.resource,
            user=booking.user,
            department=department,
            session_start=booking.actual_start_time,
            session_end=booking.actual_end_time,
            duration_minutes=duration_minutes,
            billable_minutes=charge_info['billable_minutes'],
            billable_hours=charge_info['billable_hours'],
            hourly_rate_applied=charge_info['rate_applied'],
            total_charge=charge_info['total_charge'],
        )
        billing_record.save()
        
        return billing_record
    
    def confirm(self, user=None):
        """Confirm this billing record."""
        if self.status != 'draft':
            raise ValueError("Only draft records can be confirmed")
        
        self.status = 'confirmed'
        self.confirmed_at = timezone.now()
        self.confirmed_by = user
        self.save()
    
    def adjust_charge(self, new_charge, reason, user=None):
        """Adjust the charge for this record."""
        if not self.original_charge:
            self.original_charge = self.total_charge
        
        self.total_charge = Decimal(str(new_charge))
        self.adjustment_reason = reason
        self.adjusted_by = user
        self.adjusted_at = timezone.now()
        self.status = 'adjusted'
        self.save()
    
    @property
    def has_been_adjusted(self):
        """Check if this record has been adjusted."""
        return self.original_charge is not None
    
    @property
    def adjustment_amount(self):
        """Get the adjustment amount (positive = increase, negative = decrease)."""
        if not self.has_been_adjusted:
            return Decimal('0.00')
        return self.total_charge - self.original_charge


class DepartmentBilling(models.Model):
    """Aggregated billing summary for departments by billing period."""
    department = models.ForeignKey('Department', on_delete=models.CASCADE, related_name='billing_summaries')
    billing_period = models.ForeignKey(BillingPeriod, on_delete=models.CASCADE, related_name='department_summaries')
    
    # Aggregated totals
    total_sessions = models.PositiveIntegerField(default=0)
    total_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Breakdown by status
    draft_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    confirmed_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    billed_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Resource usage breakdown (JSON for flexibility)
    resource_breakdown = models.JSONField(default=dict, help_text="Breakdown by resource type")
    user_breakdown = models.JSONField(default=dict, help_text="Breakdown by user")
    
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_departmentbilling'
        unique_together = ['department', 'billing_period']
        ordering = ['-billing_period__start_date', 'department__name']
    
    def __str__(self):
        return f"{self.department.name} - {self.billing_period.name} (£{self.total_charges})"
    
    def refresh_totals(self):
        """Recalculate totals from billing records."""
        records = BillingRecord.objects.filter(
            department=self.department,
            billing_period=self.billing_period
        )
        
        # Basic totals
        aggregates = records.aggregate(
            total_sessions=models.Count('id'),
            total_hours=models.Sum('billable_hours'),
            total_charges=models.Sum('total_charge'),
            draft_charges=models.Sum('total_charge', filter=models.Q(status='draft')),
            confirmed_charges=models.Sum('total_charge', filter=models.Q(status='confirmed')),
            billed_charges=models.Sum('total_charge', filter=models.Q(status='billed')),
        )
        
        self.total_sessions = aggregates['total_sessions'] or 0
        self.total_hours = aggregates['total_hours'] or Decimal('0.00')
        self.total_charges = aggregates['total_charges'] or Decimal('0.00')
        self.draft_charges = aggregates['draft_charges'] or Decimal('0.00')
        self.confirmed_charges = aggregates['confirmed_charges'] or Decimal('0.00')
        self.billed_charges = aggregates['billed_charges'] or Decimal('0.00')
        
        # Resource breakdown
        resource_breakdown = {}
        resource_totals = records.values('resource__name').annotate(
            hours=models.Sum('billable_hours'),
            charges=models.Sum('total_charge'),
            sessions=models.Count('id')
        ).order_by('-charges')
        
        for item in resource_totals:
            resource_breakdown[item['resource__name']] = {
                'hours': float(item['hours'] or 0),
                'charges': float(item['charges'] or 0),
                'sessions': item['sessions']
            }
        self.resource_breakdown = resource_breakdown
        
        # User breakdown
        user_breakdown = {}
        user_totals = records.values('user__username', 'user__first_name', 'user__last_name').annotate(
            hours=models.Sum('billable_hours'),
            charges=models.Sum('total_charge'),
            sessions=models.Count('id')
        ).order_by('-charges')
        
        for item in user_totals:
            full_name = f"{item['user__first_name']} {item['user__last_name']}".strip()
            display_name = full_name if full_name else item['user__username']
            user_breakdown[display_name] = {
                'username': item['user__username'],
                'hours': float(item['hours'] or 0),
                'charges': float(item['charges'] or 0),
                'sessions': item['sessions']
            }
        self.user_breakdown = user_breakdown
        
        self.save()
    
    @classmethod
    def get_or_create_for_period(cls, department, billing_period):
        """Get or create department billing summary for a period."""
        summary, created = cls.objects.get_or_create(
            department=department,
            billing_period=billing_period
        )
        if created or summary.last_updated < timezone.now() - timedelta(hours=1):
            summary.refresh_totals()
        return summary