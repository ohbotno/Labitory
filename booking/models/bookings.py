"""
Booking-related models for the Labitory.

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
from datetime import timedelta


class BookingTemplate(models.Model):
    """Templates for frequently used booking configurations."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='booking_templates')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE)
    title_template = models.CharField(max_length=200)
    description_template = models.TextField(blank=True)
    duration_hours = models.PositiveIntegerField(default=1)
    duration_minutes = models.PositiveIntegerField(default=0)
    preferred_start_time = models.TimeField(null=True, blank=True)
    shared_with_group = models.BooleanField(default=False)
    notes_template = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)  # Visible to other users
    use_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'booking_bookingtemplate'
        ordering = ['-use_count', 'name']
        unique_together = ('user', 'name')

    def __str__(self):
        return f"{self.name} - {self.resource.name}"

    @property
    def duration(self):
        """Return total duration as timedelta."""
        return timedelta(hours=self.duration_hours, minutes=self.duration_minutes)

    def create_booking_from_template(self, start_time, user=None):
        """Create a new booking from this template."""
        booking_user = user or self.user
        end_time = start_time + self.duration
        
        booking = Booking(
            resource=self.resource,
            user=booking_user,
            title=self.title_template,
            description=self.description_template,
            start_time=start_time,
            end_time=end_time,
            shared_with_group=self.shared_with_group,
            notes=self.notes_template,
        )
        
        # Increment use count
        self.use_count += 1
        self.save(update_fields=['use_count'])
        
        return booking

    def is_accessible_by_user(self, user):
        """Check if user can access this template."""
        if self.user == user:
            return True
        if self.is_public:
            return True
        # Check if same group
        try:
            user_profile = user.userprofile
            template_user_profile = self.user.userprofile
            if (user_profile.group and user_profile.group == template_user_profile.group):
                return True
        except:
            pass
        return False


class Booking(models.Model):
    """Individual booking records."""
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, related_name='bookings')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_recurring = models.BooleanField(default=False)
    recurring_pattern = models.JSONField(null=True, blank=True)
    shared_with_group = models.BooleanField(default=False)
    attendees = models.ManyToManyField(User, through='BookingAttendee', related_name='attending_bookings')
    notes = models.TextField(blank=True)
    template_used = models.ForeignKey(BookingTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings_created')
    
    # Booking dependencies
    prerequisite_bookings = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='dependent_bookings', help_text="Bookings that must be completed before this one")
    dependency_type = models.CharField(max_length=20, choices=[
        ('sequential', 'Sequential (must complete in order)'),
        ('parallel', 'Parallel (can run concurrently after prerequisites)'),
        ('conditional', 'Conditional (depends on outcome of prerequisites)')
    ], default='sequential', help_text="How this booking depends on prerequisites")
    dependency_conditions = models.JSONField(default=dict, blank=True, help_text="Additional dependency conditions")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_bookings')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Check-in/Check-out fields
    checked_in_at = models.DateTimeField(null=True, blank=True, help_text="When user actually checked in")
    checked_out_at = models.DateTimeField(null=True, blank=True, help_text="When user actually checked out")
    actual_start_time = models.DateTimeField(null=True, blank=True, help_text="Actual usage start time")
    actual_end_time = models.DateTimeField(null=True, blank=True, help_text="Actual usage end time")
    no_show = models.BooleanField(default=False, help_text="User did not show up for booking")
    auto_checked_out = models.BooleanField(default=False, help_text="System automatically checked out user")
    check_in_reminder_sent = models.BooleanField(default=False)
    check_out_reminder_sent = models.BooleanField(default=False)

    class Meta:
        db_table = 'booking_booking'
        ordering = ['start_time']
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')),
                name='booking_end_after_start'
            )
        ]

    def __str__(self):
        return f"{self.title} - {self.resource.name} ({self.start_time.strftime('%Y-%m-%d %H:%M')})"

    def clean(self):
        """Validate booking constraints."""
        # Ensure timezone-aware datetimes
        if self.start_time and timezone.is_naive(self.start_time):
            self.start_time = timezone.make_aware(self.start_time)
        if self.end_time and timezone.is_naive(self.end_time):
            self.end_time = timezone.make_aware(self.end_time)
        
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("End time must be after start time.")
            
            # Skip time validation for existing bookings (updates/cancellations)
            if self.pk is not None:
                return
            
            # Check if user is sysadmin - they bypass time restrictions
            is_sysadmin = False
            try:
                if hasattr(self.user, 'userprofile') and self.user.userprofile.role == 'sysadmin':
                    is_sysadmin = True
            except:
                pass
            
            # Only apply time restrictions for non-sysadmin users on new bookings
            if not is_sysadmin:
                # Allow booking up to 5 minutes in the past to account for form submission time
                if self.start_time < timezone.now() - timedelta(minutes=5):
                    raise ValidationError("Cannot book in the past.")
                
                # Check booking window (9 AM - 6 PM) - more lenient check
                if self.start_time.hour < 9 or self.start_time.hour >= 18:
                    raise ValidationError("Booking start time must be between 09:00 and 18:00.")
                    
                if self.end_time.hour > 18 or (self.end_time.hour == 18 and self.end_time.minute > 0):
                    raise ValidationError("Booking must end by 18:00.")
                
                # Check max booking hours if set
                if self.resource and self.resource.max_booking_hours:
                    duration_hours = (self.end_time - self.start_time).total_seconds() / 3600
                    if duration_hours > self.resource.max_booking_hours:
                        raise ValidationError(f"Booking exceeds maximum allowed hours ({self.resource.max_booking_hours}h).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def duration(self):
        """Return booking duration as timedelta."""
        return self.end_time - self.start_time

    @property
    def can_be_cancelled(self):
        """Check if booking can be cancelled."""
        return self.status in ['pending', 'approved'] and self.start_time > timezone.now()
    
    @property
    def is_checked_in(self):
        """Check if user is currently checked in."""
        return self.checked_in_at is not None and self.checked_out_at is None
    
    @property
    def can_check_in(self):
        """Check if user can check in now."""
        if self.status not in ['approved', 'confirmed']:
            return False
        if self.checked_in_at is not None:  # Already checked in
            return False
        
        now = timezone.now()
        # Allow check-in up to 15 minutes before scheduled start and until end time
        early_checkin_buffer = timedelta(minutes=15)
        return (now >= self.start_time - early_checkin_buffer) and (now <= self.end_time)
    
    @property
    def can_check_out(self):
        """Check if user can check out now."""
        return self.is_checked_in
    
    @property
    def is_overdue_checkin(self):
        """Check if user is overdue for check-in."""
        if self.checked_in_at is not None or self.no_show:
            return False
        
        now = timezone.now()
        # Consider overdue if 15 minutes past start time
        overdue_threshold = self.start_time + timedelta(minutes=15)
        return now > overdue_threshold
    
    @property
    def is_overdue_checkout(self):
        """Check if user is overdue for check-out."""
        if not self.is_checked_in:
            return False
        
        now = timezone.now()
        # Consider overdue if 15 minutes past end time
        overdue_threshold = self.end_time + timedelta(minutes=15)
        return now > overdue_threshold
    
    @property
    def actual_duration(self):
        """Get actual usage duration."""
        if self.actual_start_time and self.actual_end_time:
            return self.actual_end_time - self.actual_start_time
        return None
    
    @property
    def checkin_status(self):
        """Get human-readable check-in status."""
        if self.no_show:
            return "No Show"
        elif self.checked_out_at:
            if self.auto_checked_out:
                return "Auto Checked Out"
            else:
                return "Checked Out"
        elif self.checked_in_at:
            return "Checked In"
        elif self.can_check_in:
            return "Ready to Check In"
        elif self.is_overdue_checkin:
            return "Overdue Check In"
        else:
            return "Not Started"
    
    def check_in(self, user=None, actual_start_time=None):
        """Check in to the booking."""
        if not self.can_check_in:
            raise ValueError("Cannot check in at this time")
        
        now = timezone.now()
        self.checked_in_at = now
        self.actual_start_time = actual_start_time or now
        self.save(update_fields=['checked_in_at', 'actual_start_time', 'updated_at'])
        
        # Create check-in event
        CheckInOutEvent.objects.create(
            booking=self,
            event_type='check_in',
            user=user or self.user,
            timestamp=now,
            actual_time=self.actual_start_time
        )
    
    def check_out(self, user=None, actual_end_time=None):
        """Check out of the booking."""
        if not self.can_check_out:
            raise ValueError("Cannot check out - not checked in")
        
        now = timezone.now()
        self.checked_out_at = now
        self.actual_end_time = actual_end_time or now
        
        # Mark as completed if past end time
        if now >= self.end_time:
            self.status = 'completed'
        
        self.save(update_fields=['checked_out_at', 'actual_end_time', 'status', 'updated_at'])
        
        # Create check-out event
        CheckInOutEvent.objects.create(
            booking=self,
            event_type='check_out',
            user=user or self.user,
            timestamp=now,
            actual_time=self.actual_end_time
        )
    
    def mark_no_show(self, user=None):
        """Mark booking as no-show."""
        if self.checked_in_at is not None:
            raise ValueError("Cannot mark as no-show - user already checked in")
        
        self.no_show = True
        self.status = 'completed'  # Mark as completed with no-show
        self.save(update_fields=['no_show', 'status', 'updated_at'])
        
        # Create no-show event
        CheckInOutEvent.objects.create(
            booking=self,
            event_type='no_show',
            user=user or self.user,
            timestamp=timezone.now()
        )
    
    def auto_check_out(self):
        """Automatically check out user at end time."""
        if not self.is_checked_in:
            return False
        
        now = timezone.now()
        self.checked_out_at = now
        self.actual_end_time = self.end_time  # Use scheduled end time for auto checkout
        self.auto_checked_out = True
        self.status = 'completed'
        
        self.save(update_fields=[
            'checked_out_at', 'actual_end_time', 'auto_checked_out', 'status', 'updated_at'
        ])
        
        # Create auto check-out event
        CheckInOutEvent.objects.create(
            booking=self,
            event_type='auto_check_out',
            user=self.user,
            timestamp=now,
            actual_time=self.actual_end_time
        )
        
        return True
    
    def has_conflicts(self):
        """Check for booking conflicts."""
        conflicts = Booking.objects.filter(
            resource=self.resource,
            status__in=['approved', 'pending'],
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).exclude(pk=self.pk)
        
        return conflicts.exists()
    
    @property
    def can_start(self):
        """Check if booking can start based on dependencies."""
        if not self.prerequisite_bookings.exists():
            return True
        
        # Check dependency fulfillment based on type
        if self.dependency_type == 'sequential':
            # All prerequisites must be completed in order
            prerequisites = self.prerequisite_bookings.all().order_by('start_time')
            for prerequisite in prerequisites:
                if prerequisite.status != 'completed':
                    return False
        
        elif self.dependency_type == 'parallel':
            # All prerequisites must be at least approved and started
            for prerequisite in self.prerequisite_bookings.all():
                if prerequisite.status not in ['approved', 'completed'] or not prerequisite.checked_in_at:
                    return False
        
        elif self.dependency_type == 'conditional':
            # Check conditional requirements from dependency_conditions
            conditions = self.dependency_conditions.get('required_outcomes', [])
            for condition in conditions:
                prerequisite_id = condition.get('booking_id')
                required_status = condition.get('status', 'completed')
                try:
                    prerequisite = self.prerequisite_bookings.get(id=prerequisite_id)
                    if prerequisite.status != required_status:
                        return False
                except Booking.DoesNotExist:
                    return False
        
        return True
    
    @property
    def dependency_status(self):
        """Get human-readable dependency status."""
        if not self.prerequisite_bookings.exists():
            return "No dependencies"
        
        if self.can_start:
            return "Dependencies satisfied"
        
        # Count dependency statuses
        prerequisites = self.prerequisite_bookings.all()
        total = prerequisites.count()
        completed = prerequisites.filter(status='completed').count()
        in_progress = prerequisites.filter(
            status='approved',
            checked_in_at__isnull=False,
            checked_out_at__isnull=True
        ).count()
        
        if completed == total:
            return "All dependencies completed"
        elif completed + in_progress == total:
            return f"Dependencies in progress ({completed}/{total} completed)"
        else:
            pending = total - completed - in_progress
            return f"Waiting for dependencies ({completed} completed, {in_progress} in progress, {pending} pending)"
    
    def get_blocking_dependencies(self):
        """Get list of prerequisite bookings that are blocking this one."""
        if self.can_start:
            return []
        
        blocking = []
        for prerequisite in self.prerequisite_bookings.all():
            if self.dependency_type == 'sequential' and prerequisite.status != 'completed':
                blocking.append(prerequisite)
            elif self.dependency_type == 'parallel' and (
                prerequisite.status not in ['approved', 'completed'] or not prerequisite.checked_in_at
            ):
                blocking.append(prerequisite)
            elif self.dependency_type == 'conditional':
                conditions = self.dependency_conditions.get('required_outcomes', [])
                for condition in conditions:
                    if (condition.get('booking_id') == prerequisite.id and 
                        prerequisite.status != condition.get('status', 'completed')):
                        blocking.append(prerequisite)
        
        return blocking
    
    def add_prerequisite(self, prerequisite_booking, dependency_type='sequential', conditions=None):
        """Add a prerequisite booking dependency."""
        if prerequisite_booking == self:
            raise ValidationError("A booking cannot depend on itself")
        
        # Check for circular dependencies
        if self.would_create_circular_dependency(prerequisite_booking):
            raise ValidationError("Adding this prerequisite would create a circular dependency")
        
        # Validate timing for sequential dependencies
        if dependency_type == 'sequential' and self.start_time <= prerequisite_booking.end_time:
            raise ValidationError("Sequential dependencies must start after the prerequisite ends")
        
        self.prerequisite_bookings.add(prerequisite_booking)
        self.dependency_type = dependency_type
        if conditions:
            self.dependency_conditions.update(conditions)
        self.save(update_fields=['dependency_type', 'dependency_conditions'])
    
    def would_create_circular_dependency(self, new_prerequisite):
        """Check if adding a prerequisite would create a circular dependency."""
        def has_dependency_path(booking, target, visited=None):
            if visited is None:
                visited = set()
            
            if booking.id in visited:
                return False  # Already checked this path
            
            visited.add(booking.id)
            
            for dependent in booking.dependent_bookings.all():
                if dependent == target:
                    return True
                if has_dependency_path(dependent, target, visited.copy()):
                    return True
            
            return False
        
        return has_dependency_path(new_prerequisite, self)
    
    def save_as_template(self, template_name, template_description="", is_public=False):
        """Save this booking as a template for future use."""
        template = BookingTemplate.objects.create(
            user=self.user,
            name=template_name,
            description=template_description,
            resource=self.resource,
            title_template=self.title,
            description_template=self.description,
            duration_hours=self.duration.seconds // 3600,
            duration_minutes=(self.duration.seconds % 3600) // 60,
            preferred_start_time=self.start_time.time(),
            shared_with_group=self.shared_with_group,
            notes_template=self.notes,
            is_public=is_public,
        )
        return template


class BookingAttendee(models.Model):
    """Through model for booking attendees."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_primary = models.BooleanField(default=False)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'booking_bookingattendee'
        unique_together = ('booking', 'user')

    def __str__(self):
        return f"{self.user.get_full_name()} attending {self.booking.title}"


class BookingHistory(models.Model):
    """Audit trail for booking changes."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='history')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=50)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'booking_bookinghistory'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} on {self.booking.title} by {self.user.username}"


class CheckInOutEvent(models.Model):
    """Track check-in/check-out events for audit purposes."""
    EVENT_TYPES = [
        ('check_in', 'Check In'),
        ('check_out', 'Check Out'),
        ('no_show', 'No Show'),
        ('auto_check_out', 'Auto Check Out'),
    ]
    
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='checkin_events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    user = models.ForeignKey(User, on_delete=models.CASCADE, help_text="User who performed the action")
    timestamp = models.DateTimeField(help_text="When the event occurred")
    actual_time = models.DateTimeField(null=True, blank=True, help_text="Actual start/end time if different from timestamp")
    notes = models.TextField(blank=True)
    
    # Additional tracking fields
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    location_data = models.JSONField(default=dict, blank=True, help_text="GPS or location data if available")
    
    class Meta:
        db_table = 'booking_checkinoutevent'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['booking', 'event_type']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['user', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.get_event_type_display()} - {self.booking.title} by {self.user.username}"