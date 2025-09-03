"""
Recurring booking logic for the Labitory.

This module handles the creation and management of recurring bookings,
including pattern validation, conflict detection, and booking generation.
"""

from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrule, DAILY, WEEKLY, MONTHLY, YEARLY
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Booking, Resource


class RecurringBookingPattern:
    """Represents a recurring booking pattern with validation."""
    
    FREQUENCY_CHOICES = {
        'daily': DAILY,
        'weekly': WEEKLY,
        'monthly': MONTHLY,
        'yearly': YEARLY,
    }
    
    def __init__(self, frequency, interval=1, count=None, until=None, 
                 by_weekday=None, by_monthday=None, by_month=None):
        """
        Initialize recurring pattern.
        
        Args:
            frequency: 'daily', 'weekly', 'monthly', or 'yearly'
            interval: How often to repeat (e.g., every 2 weeks)
            count: Maximum number of occurrences
            until: End date for recurrence
            by_weekday: List of weekdays (0=Monday, 6=Sunday) for weekly/monthly
            by_monthday: Day of month for monthly recurrence
            by_month: Month for yearly recurrence
        """
        self.frequency = frequency
        self.interval = interval
        self.count = count
        self.until = until
        self.by_weekday = by_weekday or []
        self.by_monthday = by_monthday
        self.by_month = by_month
        
        self.validate()
    
    def validate(self):
        """Validate the recurring pattern."""
        if self.frequency not in self.FREQUENCY_CHOICES:
            raise ValidationError(f"Invalid frequency: {self.frequency}")
        
        if self.interval < 1:
            raise ValidationError("Interval must be at least 1")
        
        if self.count is not None and self.count < 1:
            raise ValidationError("Count must be at least 1")
        
        if self.count is not None and self.until is not None:
            raise ValidationError("Cannot specify both count and until date")
        
        if self.frequency == 'weekly' and not self.by_weekday:
            raise ValidationError("Weekly recurrence requires weekdays")
        
        if self.frequency == 'monthly' and self.by_monthday:
            if not 1 <= self.by_monthday <= 31:
                raise ValidationError("Month day must be between 1 and 31")
        
        if self.frequency == 'yearly' and self.by_month:
            if not 1 <= self.by_month <= 12:
                raise ValidationError("Month must be between 1 and 12")
    
    def to_dict(self):
        """Convert pattern to dictionary for JSON storage."""
        return {
            'frequency': self.frequency,
            'interval': self.interval,
            'count': self.count,
            'until': self.until.isoformat() if self.until else None,
            'by_weekday': self.by_weekday,
            'by_monthday': self.by_monthday,
            'by_month': self.by_month,
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create pattern from dictionary."""
        until = None
        if data.get('until'):
            until = datetime.fromisoformat(data['until'])
            if timezone.is_naive(until):
                until = timezone.make_aware(until)
        
        return cls(
            frequency=data['frequency'],
            interval=data.get('interval', 1),
            count=data.get('count'),
            until=until,
            by_weekday=data.get('by_weekday', []),
            by_monthday=data.get('by_monthday'),
            by_month=data.get('by_month'),
        )


class RecurringBookingGenerator:
    """Generates recurring bookings based on patterns."""
    
    def __init__(self, base_booking, pattern):
        """
        Initialize generator.
        
        Args:
            base_booking: The original booking to base recurrence on
            pattern: RecurringBookingPattern instance
        """
        self.base_booking = base_booking
        self.pattern = pattern
        self.duration = base_booking.end_time - base_booking.start_time
    
    def generate_dates(self, max_advance_days=90):
        """Generate all recurrence dates."""
        start_date = self.base_booking.start_time
        
        # Calculate until date if not specified
        until_date = self.pattern.until
        if until_date is None:
            until_date = timezone.now() + timedelta(days=max_advance_days)
        
        # Configure rrule parameters
        rrule_kwargs = {
            'freq': self.pattern.FREQUENCY_CHOICES[self.pattern.frequency],
            'interval': self.pattern.interval,
            'dtstart': start_date,
        }
        
        if self.pattern.count:
            rrule_kwargs['count'] = self.pattern.count
        else:
            rrule_kwargs['until'] = until_date
        
        if self.pattern.by_weekday:
            rrule_kwargs['byweekday'] = self.pattern.by_weekday
        
        if self.pattern.by_monthday:
            rrule_kwargs['bymonthday'] = self.pattern.by_monthday
        
        if self.pattern.by_month:
            rrule_kwargs['bymonth'] = self.pattern.by_month
        
        # Generate dates
        rule = rrule(**rrule_kwargs)
        return list(rule)
    
    def check_conflicts(self, dates):
        """Check for booking conflicts on generated dates."""
        conflicts = []
        
        for occurrence_date in dates:
            # Skip the original booking date
            if occurrence_date == self.base_booking.start_time:
                continue
            
            end_time = occurrence_date + self.duration
            
            # Check for conflicts
            conflicting_bookings = Booking.objects.filter(
                resource=self.base_booking.resource,
                status__in=['approved', 'pending'],
                start_time__lt=end_time,
                end_time__gt=occurrence_date
            ).exclude(pk=self.base_booking.pk)
            
            if conflicting_bookings.exists():
                conflicts.append({
                    'date': occurrence_date,
                    'conflicts': list(conflicting_bookings)
                })
        
        return conflicts
    
    def create_recurring_bookings(self, skip_conflicts=False):
        """
        Create recurring bookings.
        
        Args:
            skip_conflicts: If True, skip dates with conflicts
            
        Returns:
            dict with created bookings and conflicts
        """
        dates = self.generate_dates()
        conflicts = self.check_conflicts(dates)
        
        created_bookings = []
        skipped_dates = []
        
        for occurrence_date in dates:
            # Skip the original booking
            if occurrence_date == self.base_booking.start_time:
                continue
            
            # Check if this date has conflicts
            has_conflict = any(c['date'] == occurrence_date for c in conflicts)
            
            if has_conflict and skip_conflicts:
                skipped_dates.append(occurrence_date)
                continue
            elif has_conflict and not skip_conflicts:
                raise ValidationError(
                    f"Booking conflict on {occurrence_date.strftime('%Y-%m-%d %H:%M')}. "
                    "Use skip_conflicts=True to skip conflicting dates."
                )
            
            # Create the recurring booking
            end_time = occurrence_date + self.duration
            
            recurring_booking = Booking.objects.create(
                resource=self.base_booking.resource,
                user=self.base_booking.user,
                title=f"{self.base_booking.title} (Recurring)",
                description=self.base_booking.description,
                start_time=occurrence_date,
                end_time=end_time,
                status=self.base_booking.status,
                is_recurring=True,
                recurring_pattern=self.pattern.to_dict(),
                shared_with_group=self.base_booking.shared_with_group,
                notes=self.base_booking.notes,
            )
            
            # Copy attendees
            for attendee in self.base_booking.attendees.all():
                recurring_booking.attendees.add(attendee)
            
            created_bookings.append(recurring_booking)
        
        return {
            'created_bookings': created_bookings,
            'conflicts': conflicts,
            'skipped_dates': skipped_dates,
            'total_created': len(created_bookings),
        }


class RecurringBookingManager:
    """High-level manager for recurring bookings."""
    
    @staticmethod
    def create_weekly_booking(booking, weekdays, weeks=4, skip_conflicts=True):
        """
        Create weekly recurring booking.
        
        Args:
            booking: Base booking
            weekdays: List of weekdays (0=Monday, 6=Sunday)
            weeks: Number of weeks to repeat
            skip_conflicts: Skip conflicting dates
        """
        pattern = RecurringBookingPattern(
            frequency='weekly',
            interval=1,
            count=weeks,
            by_weekday=weekdays
        )
        
        generator = RecurringBookingGenerator(booking, pattern)
        return generator.create_recurring_bookings(skip_conflicts=skip_conflicts)
    
    @staticmethod
    def create_daily_booking(booking, days=10, skip_conflicts=True):
        """
        Create daily recurring booking.
        
        Args:
            booking: Base booking
            days: Number of days to repeat
            skip_conflicts: Skip conflicting dates
        """
        pattern = RecurringBookingPattern(
            frequency='daily',
            interval=1,
            count=days
        )
        
        generator = RecurringBookingGenerator(booking, pattern)
        return generator.create_recurring_bookings(skip_conflicts=skip_conflicts)
    
    @staticmethod
    def create_monthly_booking(booking, months=3, day_of_month=None, skip_conflicts=True):
        """
        Create monthly recurring booking.
        
        Args:
            booking: Base booking
            months: Number of months to repeat
            day_of_month: Specific day of month (None = same day as original)
            skip_conflicts: Skip conflicting dates
        """
        pattern = RecurringBookingPattern(
            frequency='monthly',
            interval=1,
            count=months,
            by_monthday=day_of_month
        )
        
        generator = RecurringBookingGenerator(booking, pattern)
        return generator.create_recurring_bookings(skip_conflicts=skip_conflicts)
    
    @staticmethod
    def get_recurring_series(booking):
        """Get all bookings in the same recurring series."""
        if not booking.is_recurring or not booking.recurring_pattern:
            return [booking]
        
        # Find bookings with the same pattern and base properties
        series_bookings = Booking.objects.filter(
            resource=booking.resource,
            user=booking.user,
            is_recurring=True,
            recurring_pattern=booking.recurring_pattern
        ).order_by('start_time')
        
        return list(series_bookings)
    
    @staticmethod
    def cancel_recurring_series(booking, cancel_future_only=False):
        """
        Cancel entire recurring series or future bookings only.
        
        Args:
            booking: Any booking in the series
            cancel_future_only: If True, only cancel future bookings
        """
        series = RecurringBookingManager.get_recurring_series(booking)
        
        cancelled_count = 0
        for series_booking in series:
            # If cancel_future_only, skip past bookings
            if cancel_future_only and series_booking.start_time <= timezone.now():
                continue
            
            if series_booking.can_be_cancelled:
                series_booking.status = 'cancelled'
                series_booking.save()
                cancelled_count += 1
        
        return cancelled_count