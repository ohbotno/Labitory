"""
Booking conflict detection and resolution for the Labitory.

This module handles the detection of booking conflicts and provides
interfaces for resolving them through various strategies.
"""

from datetime import datetime, timedelta
from django.db.models import Q
from django.utils import timezone
from .models import Booking, Resource, Maintenance


class BookingConflict:
    """Represents a booking conflict with details."""
    
    def __init__(self, booking1, booking2, conflict_type='overlap'):
        self.booking1 = booking1
        self.booking2 = booking2
        self.conflict_type = conflict_type
        self.overlap_start = max(booking1.start_time, booking2.start_time)
        self.overlap_end = min(booking1.end_time, booking2.end_time)
        self.overlap_duration = self.overlap_end - self.overlap_start
    
    def __str__(self):
        return (f"Conflict between '{self.booking1.title}' and '{self.booking2.title}' "
                f"from {self.overlap_start} to {self.overlap_end}")
    
    def to_dict(self):
        """Convert conflict to dictionary for JSON serialization."""
        return {
            'booking1': {
                'id': self.booking1.pk,
                'title': self.booking1.title,
                'user': self.booking1.user.get_full_name(),
                'start_time': self.booking1.start_time.isoformat(),
                'end_time': self.booking1.end_time.isoformat(),
                'status': self.booking1.status,
            },
            'booking2': {
                'id': self.booking2.pk,
                'title': self.booking2.title,
                'user': self.booking2.user.get_full_name(),
                'start_time': self.booking2.start_time.isoformat(),
                'end_time': self.booking2.end_time.isoformat(),
                'status': self.booking2.status,
            },
            'conflict_type': self.conflict_type,
            'overlap_start': self.overlap_start.isoformat(),
            'overlap_end': self.overlap_end.isoformat(),
            'overlap_duration_minutes': int(self.overlap_duration.total_seconds() / 60),
        }


class MaintenanceConflict:
    """Represents a conflict between a booking and maintenance."""
    
    def __init__(self, booking, maintenance):
        self.booking = booking
        self.maintenance = maintenance
        self.conflict_type = 'maintenance'
        self.overlap_start = max(booking.start_time, maintenance.start_time)
        self.overlap_end = min(booking.end_time, maintenance.end_time)
        self.overlap_duration = self.overlap_end - self.overlap_start
    
    def __str__(self):
        return (f"Maintenance conflict: '{self.booking.title}' overlaps with "
                f"'{self.maintenance.title}' from {self.overlap_start} to {self.overlap_end}")
    
    def to_dict(self):
        """Convert conflict to dictionary for JSON serialization."""
        return {
            'booking': {
                'id': self.booking.pk,
                'title': self.booking.title,
                'user': self.booking.user.get_full_name(),
                'start_time': self.booking.start_time.isoformat(),
                'end_time': self.booking.end_time.isoformat(),
                'status': self.booking.status,
            },
            'maintenance': {
                'id': self.maintenance.pk,
                'title': self.maintenance.title,
                'start_time': self.maintenance.start_time.isoformat(),
                'end_time': self.maintenance.end_time.isoformat(),
                'maintenance_type': self.maintenance.maintenance_type,
            },
            'conflict_type': self.conflict_type,
            'overlap_start': self.overlap_start.isoformat(),
            'overlap_end': self.overlap_end.isoformat(),
            'overlap_duration_minutes': int(self.overlap_duration.total_seconds() / 60),
        }


class ConflictDetector:
    """Detects various types of booking conflicts."""
    
    @staticmethod
    def check_booking_conflicts(booking, exclude_booking_ids=None):
        """
        Check for conflicts with other bookings.
        
        Args:
            booking: Booking instance to check
            exclude_booking_ids: List of booking IDs to exclude from conflict check
            
        Returns:
            List of BookingConflict instances
        """
        conflicts = []
        exclude_ids = exclude_booking_ids or []
        
        # Find overlapping bookings for the same resource
        overlapping_bookings = Booking.objects.filter(
            resource=booking.resource,
            status__in=['approved', 'pending'],
            start_time__lt=booking.end_time,
            end_time__gt=booking.start_time
        ).exclude(pk__in=exclude_ids)
        
        if booking.pk:
            overlapping_bookings = overlapping_bookings.exclude(pk=booking.pk)
        
        for other_booking in overlapping_bookings:
            conflict = BookingConflict(booking, other_booking)
            conflicts.append(conflict)
        
        return conflicts
    
    @staticmethod
    def check_maintenance_conflicts(booking):
        """
        Check for conflicts with maintenance schedules.
        
        Args:
            booking: Booking instance to check
            
        Returns:
            List of MaintenanceConflict instances
        """
        conflicts = []
        
        # Find overlapping maintenance for the same resource
        overlapping_maintenance = Maintenance.objects.filter(
            resource=booking.resource,
            blocks_booking=True,
            start_time__lt=booking.end_time,
            end_time__gt=booking.start_time
        )
        
        for maintenance in overlapping_maintenance:
            conflict = MaintenanceConflict(booking, maintenance)
            conflicts.append(conflict)
        
        return conflicts
    
    @staticmethod
    def check_all_conflicts(booking, exclude_booking_ids=None):
        """
        Check for all types of conflicts.
        
        Args:
            booking: Booking instance to check
            exclude_booking_ids: List of booking IDs to exclude from conflict check
            
        Returns:
            Tuple of (booking_conflicts, maintenance_conflicts)
        """
        booking_conflicts = ConflictDetector.check_booking_conflicts(
            booking, exclude_booking_ids
        )
        maintenance_conflicts = ConflictDetector.check_maintenance_conflicts(booking)
        
        return booking_conflicts, maintenance_conflicts
    
    @staticmethod
    def find_resource_conflicts(resource, start_time, end_time, exclude_booking_ids=None):
        """
        Find all conflicts for a resource in a time range.
        
        Args:
            resource: Resource instance
            start_time: Start of time range
            end_time: End of time range
            exclude_booking_ids: List of booking IDs to exclude
            
        Returns:
            List of all conflicts in the time range
        """
        exclude_ids = exclude_booking_ids or []
        conflicts = []
        
        # Get all bookings in the time range
        bookings = Booking.objects.filter(
            resource=resource,
            status__in=['approved', 'pending'],
            start_time__lt=end_time,
            end_time__gt=start_time
        ).exclude(pk__in=exclude_ids).order_by('start_time')
        
        # Check each booking against all others
        booking_list = list(bookings)
        for i, booking1 in enumerate(booking_list):
            for booking2 in booking_list[i+1:]:
                if (booking1.start_time < booking2.end_time and 
                    booking1.end_time > booking2.start_time):
                    conflict = BookingConflict(booking1, booking2)
                    conflicts.append(conflict)
        
        return conflicts


class ConflictResolver:
    """Provides strategies for resolving booking conflicts."""
    
    @staticmethod
    def suggest_alternative_times(booking, conflicts, buffer_minutes=30):
        """
        Suggest alternative times to avoid conflicts.
        
        Args:
            booking: Booking instance with conflicts
            conflicts: List of conflicts to avoid
            buffer_minutes: Buffer time between bookings
            
        Returns:
            List of suggested time slots
        """
        suggestions = []
        duration = booking.end_time - booking.start_time
        buffer = timedelta(minutes=buffer_minutes)
        
        # Get all conflicting time ranges
        conflict_ranges = []
        for conflict in conflicts:
            if hasattr(conflict, 'booking2'):
                # Booking conflict
                conflict_ranges.append((
                    conflict.booking2.start_time - buffer,
                    conflict.booking2.end_time + buffer
                ))
            else:
                # Maintenance conflict
                conflict_ranges.append((
                    conflict.maintenance.start_time - buffer,
                    conflict.maintenance.end_time + buffer
                ))
        
        # Sort conflict ranges by start time
        conflict_ranges.sort(key=lambda x: x[0])
        
        # Try to fit the booking before the first conflict
        if conflict_ranges:
            earliest_conflict_start = conflict_ranges[0][0]
            suggested_end = earliest_conflict_start
            suggested_start = suggested_end - duration
            
            if suggested_start >= timezone.now():
                suggestions.append({
                    'start_time': suggested_start,
                    'end_time': suggested_end,
                    'reason': 'Before first conflict'
                })
        
        # Try to fit between conflicts
        for i in range(len(conflict_ranges) - 1):
            gap_start = conflict_ranges[i][1]
            gap_end = conflict_ranges[i + 1][0]
            gap_duration = gap_end - gap_start
            
            if gap_duration >= duration:
                suggestions.append({
                    'start_time': gap_start,
                    'end_time': gap_start + duration,
                    'reason': f'Between conflicts {i+1} and {i+2}'
                })
        
        # Try to fit after the last conflict
        if conflict_ranges:
            latest_conflict_end = conflict_ranges[-1][1]
            suggested_start = latest_conflict_end
            suggested_end = suggested_start + duration
            
            suggestions.append({
                'start_time': suggested_start,
                'end_time': suggested_end,
                'reason': 'After last conflict'
            })
        
        # Filter suggestions to business hours (9 AM - 6 PM)
        valid_suggestions = []
        for suggestion in suggestions:
            start_hour = suggestion['start_time'].hour
            end_hour = suggestion['end_time'].hour
            
            if (9 <= start_hour < 18 and 9 < end_hour <= 18 and
                suggestion['start_time'] >= timezone.now()):
                valid_suggestions.append(suggestion)
        
        return valid_suggestions[:5]  # Return top 5 suggestions
    
    @staticmethod
    def suggest_alternative_resources(booking, user_profile):
        """
        Suggest alternative resources for the same time slot.
        
        Args:
            booking: Booking instance
            user_profile: User's profile for permission checking
            
        Returns:
            List of alternative resources
        """
        alternatives = []
        
        # Get similar resources (same type)
        similar_resources = Resource.objects.filter(
            resource_type=booking.resource.resource_type,
            is_active=True
        ).exclude(pk=booking.resource.pk)
        
        for resource in similar_resources:
            # Check if user can access this resource
            if not resource.is_available_for_user(user_profile):
                continue
            
            # Check if resource is available at the requested time
            conflicts = ConflictDetector.check_booking_conflicts(
                type('TempBooking', (), {
                    'resource': resource,
                    'start_time': booking.start_time,
                    'end_time': booking.end_time,
                    'pk': None
                })()
            )
            
            maintenance_conflicts = ConflictDetector.check_maintenance_conflicts(
                type('TempBooking', (), {
                    'resource': resource,
                    'start_time': booking.start_time,
                    'end_time': booking.end_time,
                })()
            )
            
            if not conflicts and not maintenance_conflicts:
                alternatives.append({
                    'resource': resource,
                    'reason': 'Available at requested time',
                    'location': resource.location,
                    'capacity': resource.capacity,
                })
        
        return alternatives
    
    @staticmethod
    def auto_resolve_conflict(conflict, strategy='reschedule_lower_priority'):
        """
        Automatically resolve a conflict using the specified strategy.
        
        Args:
            conflict: BookingConflict instance
            strategy: Resolution strategy
            
        Returns:
            Dict with resolution result
        """
        if strategy == 'reschedule_lower_priority':
            # Determine which booking has lower priority
            booking1 = conflict.booking1
            booking2 = conflict.booking2
            
            # Priority rules: approved > pending, staff > student
            def get_priority_score(booking):
                score = 0
                if booking.status == 'approved':
                    score += 10
                
                try:
                    user_profile = booking.user.userprofile
                    if user_profile.role in ['lecturer', 'lab_manager', 'sysadmin']:
                        score += 5
                except:
                    pass
                
                # Earlier bookings get higher priority
                if booking.created_at:
                    days_old = (timezone.now() - booking.created_at).days
                    score += max(0, 30 - days_old)  # Max 30 points for age
                
                return score
            
            score1 = get_priority_score(booking1)
            score2 = get_priority_score(booking2)
            
            if score1 < score2:
                lower_priority_booking = booking1
                higher_priority_booking = booking2
            else:
                lower_priority_booking = booking2
                higher_priority_booking = booking1
            
            return {
                'strategy': strategy,
                'action': 'reschedule',
                'booking_to_reschedule': lower_priority_booking.pk,
                'booking_to_keep': higher_priority_booking.pk,
                'reason': f'Booking {lower_priority_booking.pk} has lower priority'
            }
        
        return {
            'strategy': strategy,
            'action': 'manual_review',
            'reason': 'Automatic resolution not possible'
        }


class ConflictManager:
    """High-level manager for booking conflicts."""
    
    @staticmethod
    def get_resource_conflicts_report(resource, days_ahead=30):
        """
        Generate a comprehensive conflict report for a resource.
        
        Args:
            resource: Resource instance
            days_ahead: Number of days to look ahead
            
        Returns:
            Dict with conflict summary and details
        """
        start_time = timezone.now()
        end_time = start_time + timedelta(days=days_ahead)
        
        conflicts = ConflictDetector.find_resource_conflicts(
            resource, start_time, end_time
        )
        
        # Group conflicts by day
        conflicts_by_day = {}
        for conflict in conflicts:
            day = conflict.overlap_start.date()
            if day not in conflicts_by_day:
                conflicts_by_day[day] = []
            conflicts_by_day[day].append(conflict)
        
        return {
            'resource': {
                'id': resource.pk,
                'name': resource.name,
                'type': resource.get_resource_type_display(),
            },
            'period': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'days': days_ahead,
            },
            'summary': {
                'total_conflicts': len(conflicts),
                'days_with_conflicts': len(conflicts_by_day),
                'avg_conflicts_per_day': len(conflicts) / max(1, len(conflicts_by_day)),
            },
            'conflicts_by_day': {
                day.isoformat(): [c.to_dict() for c in day_conflicts]
                for day, day_conflicts in conflicts_by_day.items()
            },
            'all_conflicts': [c.to_dict() for c in conflicts],
        }
    
    @staticmethod
    def bulk_resolve_conflicts(conflicts, strategy='suggest_alternatives'):
        """
        Resolve multiple conflicts using a bulk strategy.
        
        Args:
            conflicts: List of conflict instances
            strategy: Resolution strategy
            
        Returns:
            Dict with resolution results
        """
        results = []
        
        for conflict in conflicts:
            if strategy == 'suggest_alternatives':
                # For each conflict, suggest alternatives for the lower priority booking
                resolution = ConflictResolver.auto_resolve_conflict(conflict)
                
                if resolution['action'] == 'reschedule':
                    booking_to_reschedule_id = resolution['booking_to_reschedule']
                    booking_to_reschedule = (conflict.booking1 if conflict.booking1.pk == booking_to_reschedule_id 
                                           else conflict.booking2)
                    
                    try:
                        user_profile = booking_to_reschedule.user.userprofile
                        time_suggestions = ConflictResolver.suggest_alternative_times(
                            booking_to_reschedule, [conflict]
                        )
                        resource_suggestions = ConflictResolver.suggest_alternative_resources(
                            booking_to_reschedule, user_profile
                        )
                        
                        results.append({
                            'conflict': conflict.to_dict(),
                            'resolution': resolution,
                            'suggestions': {
                                'alternative_times': time_suggestions,
                                'alternative_resources': resource_suggestions,
                            }
                        })
                    except:
                        results.append({
                            'conflict': conflict.to_dict(),
                            'resolution': resolution,
                            'error': 'Could not generate suggestions'
                        })
                else:
                    results.append({
                        'conflict': conflict.to_dict(),
                        'resolution': resolution,
                    })
        
        return {
            'strategy': strategy,
            'total_conflicts': len(conflicts),
            'results': results,
            'summary': {
                'auto_resolvable': len([r for r in results if r.get('resolution', {}).get('action') == 'reschedule']),
                'manual_review': len([r for r in results if r.get('resolution', {}).get('action') == 'manual_review']),
            }
        }