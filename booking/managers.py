"""
Custom model managers with query optimization for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors
"""

from django.db import models
from django.db.models import Q, Count, Prefetch, F, Sum, Avg
from django.utils import timezone
from datetime import timedelta


class BookingManager(models.Manager):
    """Optimized manager for Booking model with common query patterns."""
    
    def get_queryset(self):
        """Base queryset with essential select_related."""
        return super().get_queryset().select_related(
            'resource',
            'user',
            'user__userprofile',
            'approved_by'
        )
    
    def with_attendees(self):
        """Include attendee information."""
        from .models import BookingAttendee
        return self.get_queryset().prefetch_related(
            Prefetch(
                'bookingattendee_set',
                queryset=BookingAttendee.objects.select_related('user', 'user__userprofile')
            )
        )
    
    def with_billing(self):
        """Include billing information."""
        return self.get_queryset().select_related(
            'billing_record',
            'billing_record__billing_rate',
            'billing_record__billing_period'
        )
    
    def active(self):
        """Get active bookings (approved or pending)."""
        return self.get_queryset().filter(
            status__in=['approved', 'pending']
        )
    
    def upcoming(self, days=7):
        """Get upcoming bookings within specified days."""
        end_date = timezone.now() + timedelta(days=days)
        return self.active().filter(
            start_time__gte=timezone.now(),
            start_time__lte=end_date
        ).order_by('start_time')
    
    def for_resource(self, resource):
        """Get bookings for a specific resource."""
        return self.get_queryset().filter(resource=resource)
    
    def for_user(self, user):
        """Get bookings for a specific user."""
        return self.get_queryset().filter(
            Q(user=user) | Q(attendees=user)
        ).distinct()
    
    def conflicts_with(self, resource, start_time, end_time, exclude_booking=None):
        """Find bookings that conflict with given time range."""
        queryset = self.active().filter(
            resource=resource,
            start_time__lt=end_time,
            end_time__gt=start_time
        )
        if exclude_booking:
            queryset = queryset.exclude(pk=exclude_booking.pk)
        return queryset
    
    def needs_checkin_reminder(self):
        """Get bookings that need check-in reminders."""
        reminder_time = timezone.now() + timedelta(minutes=15)
        return self.filter(
            status='approved',
            start_time__lte=reminder_time,
            start_time__gte=timezone.now(),
            check_in_reminder_sent=False,
            checked_in_at__isnull=True
        )
    
    def overdue_checkout(self):
        """Get bookings that are overdue for checkout."""
        overdue_time = timezone.now() - timedelta(minutes=15)
        return self.filter(
            checked_in_at__isnull=False,
            checked_out_at__isnull=True,
            end_time__lt=overdue_time
        )


class ResourceManager(models.Manager):
    """Optimized manager for Resource model."""
    
    def get_queryset(self):
        """Base queryset with common annotations."""
        return super().get_queryset().annotate(
            active_bookings_count=Count(
                'bookings',
                filter=Q(bookings__status__in=['approved', 'pending'])
            ),
            total_bookings_count=Count('bookings'),
            open_issues_count=Count(
                'issues',
                filter=Q(issues__status__in=['open', 'in_progress'])
            )
        )
    
    def active(self):
        """Get active resources."""
        return self.get_queryset().filter(is_active=True, is_closed=False)
    
    def available_for_user(self, user):
        """Get resources available for a specific user."""
        from .models import UserProfile
        
        try:
            user_profile = user.userprofile
        except UserProfile.DoesNotExist:
            return self.none()
        
        queryset = self.active()
        
        # Sysadmin has access to all active resources
        if user_profile.role == 'sysadmin':
            return queryset
        
        # Filter based on user requirements
        if not user_profile.is_inducted:
            queryset = queryset.filter(requires_induction=False)
        
        # Remove training level filtering - now handled by specific training requirements
        # Users can see all resources regardless of training requirements
        
        return queryset
    
    def with_access_info(self):
        """Include access permission information."""
        from .models import ResourceAccess, ResourceResponsible
        
        return self.get_queryset().prefetch_related(
            Prefetch(
                'access_permissions',
                queryset=ResourceAccess.objects.select_related('user', 'granted_by').filter(is_active=True)
            ),
            Prefetch(
                'responsible_persons',
                queryset=ResourceResponsible.objects.select_related('user', 'assigned_by').filter(is_active=True)
            )
        )
    
    def with_training_requirements(self):
        """Include training requirement information."""
        from .models import ResourceTrainingRequirement
        
        return self.get_queryset().prefetch_related(
            Prefetch(
                'training_requirements',
                queryset=ResourceTrainingRequirement.objects.select_related('training_course').order_by('order')
            )
        )
    
    def billable(self):
        """Get billable resources."""
        return self.active().filter(is_billable=True)
    
    def by_type(self, resource_type):
        """Filter resources by type."""
        return self.active().filter(resource_type=resource_type)


class NotificationManager(models.Manager):
    """Optimized manager for Notification model."""
    
    def get_queryset(self):
        """Base queryset with essential select_related."""
        return super().get_queryset().select_related(
            'user',
            'user__userprofile',
            'booking',
            'booking__resource',
            'resource',
            'maintenance',
            'access_request',
            'training_request'
        )
    
    def unread(self):
        """Get unread notifications."""
        return self.get_queryset().exclude(status='read')
    
    def for_user(self, user):
        """Get notifications for a specific user."""
        return self.get_queryset().filter(user=user)
    
    def pending_delivery(self):
        """Get notifications pending delivery."""
        return self.get_queryset().filter(
            status='pending',
            Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=timezone.now())
        )
    
    def failed_retryable(self):
        """Get failed notifications that can be retried."""
        return self.get_queryset().filter(
            status='failed',
            retry_count__lt=F('max_retries'),
            next_retry_at__lte=timezone.now()
        )
    
    def by_type(self, notification_type):
        """Filter notifications by type."""
        return self.get_queryset().filter(notification_type=notification_type)
    
    def recent(self, days=7):
        """Get recent notifications."""
        since = timezone.now() - timedelta(days=days)
        return self.get_queryset().filter(created_at__gte=since)


class AccessRequestManager(models.Manager):
    """Optimized manager for AccessRequest model."""
    
    def get_queryset(self):
        """Base queryset with essential select_related."""
        return super().get_queryset().select_related(
            'resource',
            'user',
            'user__userprofile',
            'user__userprofile__department',
            'reviewed_by',
            'safety_induction_confirmed_by',
            'lab_training_confirmed_by',
            'risk_assessment_confirmed_by'
        )
    
    def pending(self):
        """Get pending access requests."""
        return self.get_queryset().filter(status='pending')
    
    def for_resource(self, resource):
        """Get access requests for a specific resource."""
        return self.get_queryset().filter(resource=resource)
    
    def for_user(self, user):
        """Get access requests for a specific user."""
        return self.get_queryset().filter(user=user)
    
    def awaiting_prerequisites(self):
        """Get requests waiting for prerequisite completion."""
        return self.pending().filter(
            Q(safety_induction_completed=False) |
            Q(lab_training_completed=False) |
            Q(risk_assessment_completed=False)
        )
    
    def ready_for_approval(self):
        """Get requests that have all prerequisites completed."""
        return self.pending().filter(
            safety_induction_completed=True,
            lab_training_completed=True,
            risk_assessment_completed=True
        )


class MaintenanceManager(models.Manager):
    """Optimized manager for Maintenance model."""
    
    def get_queryset(self):
        """Base queryset with essential select_related."""
        return super().get_queryset().select_related(
            'resource',
            'vendor',
            'created_by',
            'assigned_to',
            'approved_by'
        ).prefetch_related(
            'affects_other_resources',
            'prerequisite_maintenances'
        )
    
    def active(self):
        """Get active maintenance tasks."""
        return self.get_queryset().filter(
            status__in=['scheduled', 'in_progress']
        )
    
    def upcoming(self, days=7):
        """Get upcoming maintenance within specified days."""
        end_date = timezone.now() + timedelta(days=days)
        return self.filter(
            status='scheduled',
            start_time__gte=timezone.now(),
            start_time__lte=end_date
        ).order_by('start_time')
    
    def overdue(self):
        """Get overdue maintenance tasks."""
        return self.filter(
            status='scheduled',
            start_time__lt=timezone.now()
        )
    
    def for_resource(self, resource):
        """Get maintenance for a specific resource."""
        return self.get_queryset().filter(
            Q(resource=resource) | Q(affects_other_resources=resource)
        ).distinct()
    
    def requiring_approval(self):
        """Get maintenance tasks requiring approval."""
        return self.filter(
            status='pending',
            approved_by__isnull=True
        )


class BillingRecordManager(models.Manager):
    """Optimized manager for BillingRecord model."""
    
    def get_queryset(self):
        """Base queryset with essential select_related and annotations."""
        return super().get_queryset().select_related(
            'booking',
            'booking__resource',
            'booking__user',
            'billing_period',
            'billing_rate',
            'resource',
            'user',
            'user__userprofile',
            'department',
            'confirmed_by',
            'adjusted_by'
        ).annotate(
            net_charge=F('total_charge') - F('discount_amount')
        )
    
    def for_period(self, billing_period):
        """Get billing records for a specific period."""
        return self.get_queryset().filter(billing_period=billing_period)
    
    def for_user(self, user):
        """Get billing records for a specific user."""
        return self.get_queryset().filter(user=user)
    
    def for_department(self, department):
        """Get billing records for a specific department."""
        return self.get_queryset().filter(department=department)
    
    def unconfirmed(self):
        """Get unconfirmed billing records."""
        return self.get_queryset().filter(
            status='pending',
            confirmed_by__isnull=True
        )
    
    def summary_by_department(self, billing_period):
        """Get billing summary by department for a period."""
        return self.for_period(billing_period).values(
            'department__name'
        ).annotate(
            total_hours=Sum('usage_hours'),
            total_charges=Sum('total_charge'),
            total_discounts=Sum('discount_amount'),
            net_charges=Sum('net_charge'),
            record_count=Count('id')
        ).order_by('-net_charges')
    
    def summary_by_resource(self, billing_period):
        """Get billing summary by resource for a period."""
        return self.for_period(billing_period).values(
            'resource__name'
        ).annotate(
            total_hours=Sum('usage_hours'),
            total_charges=Sum('total_charge'),
            utilization_rate=Avg('usage_hours'),
            booking_count=Count('booking', distinct=True)
        ).order_by('-total_charges')