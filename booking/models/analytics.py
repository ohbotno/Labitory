"""
Analytics models for the Labitory.

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
from .resources import Resource


class UsageAnalytics(models.Model):
    """Aggregated usage analytics for resources."""
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='usage_analytics')
    date = models.DateField()
    
    # Booking statistics
    total_bookings = models.PositiveIntegerField(default=0)
    completed_bookings = models.PositiveIntegerField(default=0)
    no_show_bookings = models.PositiveIntegerField(default=0)
    cancelled_bookings = models.PositiveIntegerField(default=0)
    
    # Time statistics (in minutes)
    total_booked_minutes = models.PositiveIntegerField(default=0)
    total_actual_minutes = models.PositiveIntegerField(default=0)
    total_wasted_minutes = models.PositiveIntegerField(default=0)  # Booked but not used
    
    # Efficiency metrics
    utilization_rate = models.FloatField(default=0.0, help_text="Actual usage / Total available time")
    efficiency_rate = models.FloatField(default=0.0, help_text="Actual usage / Booked time")
    no_show_rate = models.FloatField(default=0.0, help_text="No shows / Total bookings")
    
    # Timing statistics
    avg_early_checkin_minutes = models.FloatField(default=0.0)
    avg_late_checkin_minutes = models.FloatField(default=0.0)
    avg_early_checkout_minutes = models.FloatField(default=0.0)
    avg_late_checkout_minutes = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_usageanalytics'
        unique_together = ['resource', 'date']
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.resource.name} - {self.date} (Utilization: {self.utilization_rate:.1%})"