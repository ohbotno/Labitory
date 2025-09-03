"""
Calendar integration models for the Labitory.

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
from datetime import timedelta
from .bookings import Booking


class GoogleCalendarIntegration(models.Model):
    """Store Google Calendar OAuth integration settings for users."""
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE,
        related_name='google_calendar_integration'
    )
    google_calendar_id = models.CharField(
        max_length=255, 
        blank=True,
        help_text="Google Calendar ID where events will be synced"
    )
    access_token = models.TextField(
        help_text="Google OAuth access token (encrypted)"
    )
    refresh_token = models.TextField(
        help_text="Google OAuth refresh token (encrypted)"
    )
    token_expires_at = models.DateTimeField(
        help_text="When the access token expires"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the integration is active"
    )
    sync_enabled = models.BooleanField(
        default=True,
        help_text="Whether automatic syncing is enabled"
    )
    sync_direction = models.CharField(
        max_length=20,
        choices=[
            ('one_way', 'One-way (Labitory → Google)'),
            ('two_way', 'Two-way sync'),
        ],
        default='one_way',
        help_text="Direction of calendar synchronization"
    )
    last_sync = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Last successful sync timestamp"
    )
    sync_error_count = models.IntegerField(
        default=0,
        help_text="Number of consecutive sync errors"
    )
    last_error = models.TextField(
        blank=True,
        help_text="Last sync error message"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Google Calendar Integration"
        verbose_name_plural = "Google Calendar Integrations"

    def __str__(self):
        return f"Google Calendar for {self.user.get_full_name() or self.user.username}"

    def is_token_expired(self):
        """Check if the access token is expired."""
        return timezone.now() >= self.token_expires_at

    def needs_refresh(self):
        """Check if token needs refresh (expires within 5 minutes)."""
        return timezone.now() >= (self.token_expires_at - timedelta(minutes=5))

    def can_sync(self):
        """Check if integration can perform sync operations."""
        return self.is_active and self.sync_enabled and not self.is_token_expired()

    def get_status_display(self):
        """Get human-readable status."""
        if not self.is_active:
            return "Disabled"
        elif self.is_token_expired():
            return "Token Expired"
        elif self.sync_error_count > 0:
            return f"Sync Issues ({self.sync_error_count} errors)"
        elif self.last_sync:
            return f"Active (last sync: {self.last_sync.strftime('%Y-%m-%d %H:%M')})"
        else:
            return "Connected"


class GoogleCalendarSyncLog(models.Model):
    """Log of Google Calendar sync operations."""
    
    ACTION_CHOICES = [
        ('created', 'Event Created'),
        ('updated', 'Event Updated'), 
        ('deleted', 'Event Deleted'),
        ('full_sync', 'Full Sync'),
        ('token_refresh', 'Token Refresh'),
    ]
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
        ('skipped', 'Skipped'),
    ]
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        help_text="User whose calendar was synced"
    )
    booking = models.ForeignKey(
        'Booking', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Booking that was synced (if applicable)"
    )
    google_event_id = models.CharField(
        max_length=255, 
        blank=True,
        help_text="Google Calendar event ID"
    )
    action = models.CharField(
        max_length=20, 
        choices=ACTION_CHOICES,
        help_text="Type of sync operation performed"
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='success',
        help_text="Result of the sync operation"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if sync failed"
    )
    request_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Request data sent to Google Calendar API"
    )
    response_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Response data from Google Calendar API"
    )
    duration_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Duration of API call in milliseconds"
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Google Calendar Sync Log"
        verbose_name_plural = "Google Calendar Sync Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['booking', 'action']),
            models.Index(fields=['status', 'timestamp']),
        ]

    def __str__(self):
        booking_info = f" (Booking #{self.booking.id})" if self.booking else ""
        return f"{self.get_action_display()} - {self.get_status_display()}{booking_info}"

    def get_status_color(self):
        """Get Bootstrap color class for status."""
        colors = {
            'success': 'success',
            'error': 'danger', 
            'skipped': 'warning',
        }
        return colors.get(self.status, 'secondary')


class CalendarSyncPreferences(models.Model):
    """User preferences for calendar sync behavior."""
    
    SYNC_TIMING_CHOICES = [
        ('immediate', 'Immediately'),
        ('hourly', 'Every hour'),
        ('daily', 'Daily'),
        ('manual', 'Manual only'),
    ]
    
    CONFLICT_RESOLUTION_CHOICES = [
        ('aperture_wins', 'Labitory wins'),
        ('google_wins', 'Google Calendar wins'),
        ('ask_user', 'Ask user each time'),
        ('skip', 'Skip conflicting events'),
    ]
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='calendar_sync_preferences'
    )
    
    # Sync timing preferences
    auto_sync_timing = models.CharField(
        max_length=20,
        choices=SYNC_TIMING_CHOICES,
        default='hourly',
        help_text="How often to automatically sync with Google Calendar"
    )
    
    # What to sync
    sync_future_bookings_only = models.BooleanField(
        default=True,
        help_text="Only sync future bookings (ignore past bookings)"
    )
    sync_cancelled_bookings = models.BooleanField(
        default=False,
        help_text="Include cancelled bookings in calendar sync"
    )
    sync_pending_bookings = models.BooleanField(
        default=True,
        help_text="Include pending approval bookings in calendar sync"
    )
    
    # Conflict resolution
    conflict_resolution = models.CharField(
        max_length=20,
        choices=CONFLICT_RESOLUTION_CHOICES,
        default='skip',
        help_text="How to handle conflicts between Labitory and Google Calendar"
    )
    
    # Calendar appearance
    event_prefix = models.CharField(
        max_length=50,
        blank=True,
        default="[Lab] ",
        help_text="Prefix to add to Google Calendar event titles"
    )
    include_resource_in_title = models.BooleanField(
        default=True,
        help_text="Include resource name in Google Calendar event title"
    )
    include_description = models.BooleanField(
        default=True,
        help_text="Include booking description in Google Calendar event"
    )
    set_event_location = models.BooleanField(
        default=True,
        help_text="Set resource location as Google Calendar event location"
    )
    
    # Notifications
    notify_sync_errors = models.BooleanField(
        default=True,
        help_text="Send notifications when calendar sync fails"
    )
    notify_sync_success = models.BooleanField(
        default=False,
        help_text="Send notifications when calendar sync succeeds"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Calendar Sync Preferences"
        verbose_name_plural = "Calendar Sync Preferences"

    def __str__(self):
        return f"Calendar preferences for {self.user.get_full_name() or self.user.username}"