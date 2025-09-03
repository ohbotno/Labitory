"""
Waiting list models for the Labitory.

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
from .maintenance import Maintenance


class WaitingListEntry(models.Model):
    """Waiting list entries for when resources are unavailable."""
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('notified', 'Notified of Availability'),
        ('booked', 'Successfully Booked'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='waiting_list_entries')
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, related_name='waiting_list_entries')
    
    # Desired booking details
    desired_start_time = models.DateTimeField(help_text="Preferred start time")
    desired_end_time = models.DateTimeField(help_text="Preferred end time")
    title = models.CharField(max_length=200, help_text="Proposed booking title")
    description = models.TextField(blank=True, help_text="Proposed booking description")
    
    # Flexibility options
    flexible_start = models.BooleanField(default=False, help_text="Can start at different time")
    flexible_duration = models.BooleanField(default=False, help_text="Can use shorter duration")
    min_duration_minutes = models.PositiveIntegerField(default=60, help_text="Minimum acceptable duration in minutes")
    max_wait_days = models.PositiveIntegerField(default=7, help_text="Maximum days willing to wait")
    
    # Priority and ordering
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default='normal')
    auto_book = models.BooleanField(default=False, help_text="Automatically book when slot becomes available")
    notification_hours_ahead = models.PositiveIntegerField(default=24, help_text="Hours ahead to notify of availability")
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    position = models.PositiveIntegerField(default=1, help_text="Position in waiting list")
    times_notified = models.PositiveIntegerField(default=0)
    last_notification_sent = models.DateTimeField(null=True, blank=True)
    
    # Booking outcomes
    resulting_booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='waiting_list_entry')
    availability_window_start = models.DateTimeField(null=True, blank=True, help_text="When slot became available")
    availability_window_end = models.DateTimeField(null=True, blank=True, help_text="Until when slot is available")
    response_deadline = models.DateTimeField(null=True, blank=True, help_text="Deadline to respond to availability")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="When this entry expires")
    
    class Meta:
        db_table = 'booking_waitinglistentry'
        ordering = ['priority', 'position', 'created_at']
        indexes = [
            models.Index(fields=['resource', 'status']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['priority', 'position']),
            models.Index(fields=['desired_start_time']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} waiting for {self.resource.name} at {self.desired_start_time}"
    
    def clean(self):
        """Validate waiting list entry."""
        if self.desired_start_time >= self.desired_end_time:
            raise ValidationError("End time must be after start time.")
        
        if self.min_duration_minutes > (self.desired_end_time - self.desired_start_time).total_seconds() / 60:
            raise ValidationError("Minimum duration cannot be longer than desired duration.")
        
        if self.desired_start_time < timezone.now():
            raise ValidationError("Cannot add to waiting list for past time slots.")
    
    def save(self, *args, **kwargs):
        # Set expiration if not already set
        if not self.expires_at:
            self.expires_at = self.desired_start_time + timedelta(days=self.max_wait_days)
        
        # Set position if new entry
        if not self.pk:
            last_position = WaitingListEntry.objects.filter(
                resource=self.resource,
                status='waiting'
            ).aggregate(max_pos=models.Max('position'))['max_pos'] or 0
            self.position = last_position + 1
        
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        """Check if waiting list entry has expired."""
        return self.expires_at and timezone.now() > self.expires_at
    
    @property
    def time_remaining(self):
        """Get time remaining until expiration."""
        if not self.expires_at:
            return None
        remaining = self.expires_at - timezone.now()
        return remaining if remaining.total_seconds() > 0 else timedelta(0)
    
    @property
    def can_auto_book(self):
        """Check if this entry can be auto-booked."""
        return (
            self.auto_book and 
            self.status == 'waiting' and 
            not self.is_expired
        )
    
    def find_available_slots(self, days_ahead=7):
        """Find available time slots that match this waiting list entry."""
        from datetime import datetime, timedelta
        
        search_start = max(self.desired_start_time, timezone.now())
        search_end = search_start + timedelta(days=days_ahead)
        
        slots = []
        current_time = search_start
        desired_duration = self.desired_end_time - self.desired_start_time
        min_duration = timedelta(minutes=self.min_duration_minutes)
        
        while current_time < search_end:
            # Check for conflicts in this time slot
            slot_end = current_time + desired_duration
            
            conflicts = Booking.objects.filter(
                resource=self.resource,
                status__in=['approved', 'pending'],
                start_time__lt=slot_end,
                end_time__gt=current_time
            )
            
            maintenance_conflicts = Maintenance.objects.filter(
                resource=self.resource,
                start_time__lt=slot_end,
                end_time__gt=current_time
            )
            
            if not conflicts.exists() and not maintenance_conflicts.exists():
                # Found available slot
                slots.append({
                    'start_time': current_time,
                    'end_time': slot_end,
                    'duration': desired_duration,
                    'matches_preference': current_time == self.desired_start_time
                })
                
                # If flexible duration, also check for shorter slots
                if self.flexible_duration and desired_duration > min_duration:
                    shorter_end = current_time + min_duration
                    slots.append({
                        'start_time': current_time,
                        'end_time': shorter_end,
                        'duration': min_duration,
                        'matches_preference': False
                    })
            
            # Move to next time slot (increment by 30 minutes)
            current_time += timedelta(minutes=30)
        
        return slots
    
    def notify_of_availability(self, available_slots):
        """Send notification about available slots."""
        self.status = 'notified'
        self.times_notified += 1
        self.last_notification_sent = timezone.now()
        self.response_deadline = timezone.now() + timedelta(hours=self.notification_hours_ahead)
        
        # Store available slots in a temporary field or send in notification
        self.save(update_fields=['status', 'times_notified', 'last_notification_sent', 'response_deadline'])
        
        # Send notification (this would integrate with the notification system)
        from booking.notifications import notification_service
        notification_service.create_notification(
            user=self.user,
            notification_type='waitlist_availability',
            title=f'Resource Available: {self.resource.name}',
            message=f'Your requested resource {self.resource.name} is now available. You have {self.notification_hours_ahead} hours to book.',
            priority='high',
            metadata={
                'waiting_list_entry_id': self.id,
                'available_slots': available_slots,
                'response_deadline': self.response_deadline.isoformat()
            }
        )
    
    def create_booking_from_slot(self, slot):
        """Create a booking from an available slot."""
        if self.status != 'waiting':
            raise ValidationError("Can only create booking from waiting entry")
        
        booking = Booking.objects.create(
            resource=self.resource,
            user=self.user,
            title=self.title,
            description=self.description,
            start_time=slot['start_time'],
            end_time=slot['end_time'],
            status='approved'  # Auto-approve from waiting list
        )
        
        self.resulting_booking = booking
        self.status = 'booked'
        self.save(update_fields=['resulting_booking', 'status'])
        
        # Remove user from waiting list for this resource at this time
        self._reorder_waiting_list()
        
        return booking
    
    def cancel_waiting(self):
        """Cancel this waiting list entry."""
        self.status = 'cancelled'
        self.save(update_fields=['status'])
        self._reorder_waiting_list()
    
    def _reorder_waiting_list(self):
        """Reorder waiting list positions after removal."""
        entries = WaitingListEntry.objects.filter(
            resource=self.resource,
            status='waiting',
            position__gt=self.position
        ).order_by('position')
        
        for i, entry in enumerate(entries):
            entry.position = self.position + i
            entry.save(update_fields=['position'])
    
    @classmethod
    def check_expired_entries(cls):
        """Mark expired waiting list entries and reorder lists."""
        expired_entries = cls.objects.filter(
            status='waiting',
            expires_at__lt=timezone.now()
        )
        
        for entry in expired_entries:
            entry.status = 'expired'
            entry.save(update_fields=['status'])
            entry._reorder_waiting_list()
    
    @classmethod
    def find_opportunities(cls, resource=None):
        """Find booking opportunities for waiting list entries."""
        filters = {'status': 'waiting'}
        if resource:
            filters['resource'] = resource
        
        waiting_entries = cls.objects.filter(**filters).order_by('priority', 'position')
        opportunities = []
        
        for entry in waiting_entries:
            if not entry.is_expired:
                slots = entry.find_available_slots()
                if slots:
                    opportunities.append({
                        'entry': entry,
                        'slots': slots
                    })
        
        return opportunities


class WaitingListNotification(models.Model):
    """Notifications for waiting list availability."""
    waiting_list_entry = models.ForeignKey(WaitingListEntry, on_delete=models.CASCADE, related_name='notifications')
    available_start_time = models.DateTimeField()
    available_end_time = models.DateTimeField()
    
    # Notification details
    sent_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()  # How long user has to respond
    
    # Response tracking
    response_deadline = models.DateTimeField()
    user_response = models.CharField(max_length=20, choices=[
        ('pending', 'Pending Response'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Response Expired'),
    ], default='pending')
    responded_at = models.DateTimeField(null=True, blank=True)
    
    # Auto-booking result
    booking_created = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'booking_waitinglistnotification'
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"Notification for {self.waiting_list_entry.user.username} - {self.available_start_time}"
    
    def save(self, *args, **kwargs):
        if not self.response_deadline:
            # Give user 2 hours to respond by default
            self.response_deadline = self.sent_at + timedelta(hours=2)
        
        if not self.expires_at:
            # Notification expires when the time slot starts
            self.expires_at = self.available_start_time
        
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        """Check if notification has expired."""
        return timezone.now() > self.expires_at
    
    @property
    def response_time_remaining(self):
        """Time remaining to respond."""
        if self.user_response != 'pending':
            return timedelta(0)
        
        remaining = self.response_deadline - timezone.now()
        return remaining if remaining > timedelta(0) else timedelta(0)
    
    def accept_offer(self):
        """User accepts the time slot offer."""
        if self.user_response != 'pending' or self.is_expired:
            return False
        
        self.user_response = 'accepted'
        self.responded_at = timezone.now()
        self.save(update_fields=['user_response', 'responded_at'])
        
        # Mark waiting list entry as fulfilled
        self.waiting_list_entry.mark_as_fulfilled()
        
        return True
    
    def decline_offer(self):
        """User declines the time slot offer."""
        if self.user_response != 'pending':
            return False
        
        self.user_response = 'declined'
        self.responded_at = timezone.now()
        self.save(update_fields=['user_response', 'responded_at'])
        
        return True