# booking/services/booking_service.py
"""
Business logic service for booking operations.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth.models import User

from ..models import Booking, Resource, UserProfile, ApprovalRule
from ..conflicts import ConflictDetector
from ..recurring import RecurringBookingGenerator

logger = logging.getLogger(__name__)


class BookingService:
    """Service class for booking-related business logic."""
    
    def __init__(self):
        self.conflict_detector = ConflictDetector()
    
    def create_booking(
        self, 
        user: User, 
        resource: Resource, 
        start_time: datetime, 
        end_time: datetime, 
        title: str, 
        description: str = "",
        shared_with_group: bool = False,
        override_conflicts: bool = False,
        override_message: str = ""
    ) -> Tuple[bool, str, Optional[Booking]]:
        """
        Create a new booking with validation and conflict checking.
        
        Returns:
            Tuple of (success, message, booking_object)
        """
        try:
            # Validate user has access to resource
            if not self._validate_user_access(user, resource):
                return False, "You don't have access to this resource.", None
            
            # Validate time range
            validation_result = self._validate_time_range(resource, start_time, end_time)
            if not validation_result[0]:
                return False, validation_result[1], None
            
            # Check for conflicts
            conflicts = self.conflict_detector.detect_conflicts(
                resource, start_time, end_time
            )
            
            if conflicts and not override_conflicts:
                conflict_msg = self._format_conflict_message(conflicts)
                return False, f"Time conflict detected: {conflict_msg}", None
            
            # Create the booking
            booking = Booking.objects.create(
                user=user,
                resource=resource,
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                shared_with_group=shared_with_group,
                status='pending'
            )
            
            # Handle conflict overrides if necessary
            if conflicts and override_conflicts:
                self._handle_conflict_override(booking, conflicts, override_message)
            
            # Determine initial approval status
            self._process_approval_rules(booking)
            
            logger.info(f"Booking created: {booking.id} by {user.username}")
            return True, "Booking created successfully.", booking
            
        except Exception as e:
            logger.error(f"Error creating booking: {e}")
            return False, f"Error creating booking: {str(e)}", None
    
    def create_recurring_booking(
        self,
        user: User,
        resource: Resource,
        start_time: datetime,
        end_time: datetime,
        title: str,
        frequency: str,
        end_date: datetime,
        description: str = "",
        shared_with_group: bool = False,
        days_of_week: List[int] = None,
        interval: int = 1,
        max_occurrences: Optional[int] = None
    ) -> Tuple[bool, str, List[Booking]]:
        """
        Create a series of recurring bookings.
        
        Returns:
            Tuple of (success, message, list_of_created_bookings)
        """
        try:
            # Validate user has access to resource
            if not self._validate_user_access(user, resource):
                return False, "You don't have access to this resource.", []
            
            # Generate recurring booking instances
            generator = RecurringBookingGenerator()
            booking_instances = generator.generate_instances(
                start_time=start_time,
                end_time=end_time,
                frequency=frequency,
                end_date=end_date,
                days_of_week=days_of_week,
                interval=interval,
                max_occurrences=max_occurrences
            )
            
            if not booking_instances:
                return False, "No valid booking instances could be generated.", []
            
            created_bookings = []
            conflict_count = 0
            
            for instance in booking_instances:
                # Check for conflicts for each instance
                conflicts = self.conflict_detector.detect_conflicts(
                    resource, instance['start_time'], instance['end_time']
                )
                
                if conflicts:
                    conflict_count += 1
                    logger.warning(
                        f"Skipping recurring booking instance due to conflict: "
                        f"{instance['start_time']} - {instance['end_time']}"
                    )
                    continue
                
                # Create the booking instance
                booking = Booking.objects.create(
                    user=user,
                    resource=resource,
                    title=title,
                    description=description,
                    start_time=instance['start_time'],
                    end_time=instance['end_time'],
                    shared_with_group=shared_with_group,
                    status='pending',
                    is_recurring=True,
                    recurring_pattern={
                        'frequency': frequency,
                        'interval': interval,
                        'days_of_week': days_of_week,
                        'end_date': end_date.isoformat() if end_date else None,
                    }
                )
                
                # Process approval rules
                self._process_approval_rules(booking)
                created_bookings.append(booking)
            
            success_count = len(created_bookings)
            message = f"Created {success_count} recurring bookings."
            if conflict_count > 0:
                message += f" Skipped {conflict_count} instances due to conflicts."
            
            logger.info(f"Recurring bookings created: {success_count} by {user.username}")
            return True, message, created_bookings
            
        except Exception as e:
            logger.error(f"Error creating recurring bookings: {e}")
            return False, f"Error creating recurring bookings: {str(e)}", []
    
    def cancel_booking(
        self, 
        booking: Booking, 
        user: User, 
        reason: str = ""
    ) -> Tuple[bool, str]:
        """
        Cancel a booking with appropriate validation.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # Check if user can cancel this booking
            if not self._can_user_modify_booking(user, booking):
                return False, "You don't have permission to cancel this booking."
            
            # Check if booking can be cancelled
            if not booking.can_be_cancelled:
                return False, "This booking cannot be cancelled."
            
            # Cancel the booking
            booking.status = 'cancelled'
            if reason:
                booking.notes = f"{booking.notes}\n\nCancellation reason: {reason}".strip()
            booking.save()
            
            # Send notifications if needed
            self._send_cancellation_notifications(booking, user, reason)
            
            logger.info(f"Booking cancelled: {booking.id} by {user.username}")
            return True, "Booking cancelled successfully."
            
        except Exception as e:
            logger.error(f"Error cancelling booking: {e}")
            return False, f"Error cancelling booking: {str(e)}"
    
    def modify_booking(
        self, 
        booking: Booking, 
        user: User, 
        **updates
    ) -> Tuple[bool, str]:
        """
        Modify an existing booking with validation.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # Check if user can modify this booking
            if not self._can_user_modify_booking(user, booking):
                return False, "You don't have permission to modify this booking."
            
            # Check if booking can be modified
            if not booking.can_be_modified:
                return False, "This booking cannot be modified."
            
            # If time is being changed, check for conflicts
            if 'start_time' in updates or 'end_time' in updates:
                new_start = updates.get('start_time', booking.start_time)
                new_end = updates.get('end_time', booking.end_time)
                
                # Validate new time range
                validation_result = self._validate_time_range(
                    booking.resource, new_start, new_end
                )
                if not validation_result[0]:
                    return False, validation_result[1]
                
                # Check for conflicts
                conflicts = self.conflict_detector.detect_conflicts(
                    booking.resource, new_start, new_end, exclude_booking=booking
                )
                
                if conflicts:
                    conflict_msg = self._format_conflict_message(conflicts)
                    return False, f"Time conflict detected: {conflict_msg}"
            
            # Apply updates
            for field, value in updates.items():
                if hasattr(booking, field):
                    setattr(booking, field, value)
            
            booking.save()
            
            # Re-process approval if needed
            if 'start_time' in updates or 'end_time' in updates or 'resource' in updates:
                self._process_approval_rules(booking)
            
            logger.info(f"Booking modified: {booking.id} by {user.username}")
            return True, "Booking modified successfully."
            
        except Exception as e:
            logger.error(f"Error modifying booking: {e}")
            return False, f"Error modifying booking: {str(e)}"
    
    def get_user_bookings(
        self, 
        user: User, 
        status_filter: Optional[str] = None,
        date_range: Optional[Tuple[datetime, datetime]] = None
    ) -> List[Booking]:
        """Get bookings for a user with optional filtering."""
        queryset = Booking.objects.filter(
            Q(user=user) | Q(attendees=user)
        ).distinct().select_related('resource', 'user')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if date_range:
            start_date, end_date = date_range
            queryset = queryset.filter(
                start_time__gte=start_date,
                end_time__lte=end_date
            )
        
        return queryset.order_by('-start_time')
    
    def get_resource_bookings(
        self,
        resource: Resource,
        date_range: Optional[Tuple[datetime, datetime]] = None,
        status_filter: Optional[str] = None
    ) -> List[Booking]:
        """Get bookings for a resource with optional filtering."""
        queryset = Booking.objects.filter(
            resource=resource
        ).select_related('user')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if date_range:
            start_date, end_date = date_range
            queryset = queryset.filter(
                start_time__gte=start_date,
                end_time__lte=end_date
            )
        
        return queryset.order_by('start_time')
    
    def get_booking_statistics(self, user: User) -> Dict[str, Any]:
        """Get booking statistics for a user."""
        bookings = Booking.objects.filter(user=user)
        
        return {
            'total_bookings': bookings.count(),
            'pending_bookings': bookings.filter(status='pending').count(),
            'approved_bookings': bookings.filter(status='approved').count(),
            'completed_bookings': bookings.filter(status='completed').count(),
            'cancelled_bookings': bookings.filter(status='cancelled').count(),
            'upcoming_bookings': bookings.filter(
                start_time__gt=timezone.now(),
                status__in=['pending', 'approved']
            ).count(),
        }
    
    # Private helper methods
    
    def _validate_user_access(self, user: User, resource: Resource) -> bool:
        """Validate that user has access to the resource."""
        try:
            user_profile = user.userprofile
            return resource.is_available_for_user(user_profile)
        except UserProfile.DoesNotExist:
            return False
    
    def _validate_time_range(
        self, 
        resource: Resource, 
        start_time: datetime, 
        end_time: datetime
    ) -> Tuple[bool, str]:
        """Validate booking time range."""
        if start_time >= end_time:
            return False, "End time must be after start time."
        
        if start_time < timezone.now():
            return False, "Cannot create bookings in the past."
        
        if resource.max_booking_hours:
            duration = (end_time - start_time).total_seconds() / 3600
            if duration > resource.max_booking_hours:
                return False, (
                    f"Booking duration ({duration:.1f}h) exceeds maximum allowed "
                    f"({resource.max_booking_hours}h) for this resource."
                )
        
        return True, "Valid time range."
    
    def _format_conflict_message(self, conflicts: List[Booking]) -> str:
        """Format conflict message for display."""
        conflict_details = []
        for conflict in conflicts:
            conflict_details.append(
                f"'{conflict.title}' by {conflict.user.get_full_name()} "
                f"({conflict.start_time.strftime('%Y-%m-%d %H:%M')} - "
                f"{conflict.end_time.strftime('%Y-%m-%d %H:%M')})"
            )
        return ", ".join(conflict_details)
    
    def _handle_conflict_override(
        self, 
        booking: Booking, 
        conflicts: List[Booking], 
        override_message: str
    ):
        """Handle conflict override by notifying affected users."""
        # This would typically send notifications to users with conflicted bookings
        # Implementation depends on notification system
        pass
    
    def _process_approval_rules(self, booking: Booking):
        """Process approval rules for a booking."""
        approval_rules = ApprovalRule.objects.filter(
            resource=booking.resource,
            is_active=True
        ).order_by('priority')
        
        # Simple auto-approval logic - can be extended
        if not approval_rules.exists():
            booking.status = 'approved'
            booking.save()
    
    def _can_user_modify_booking(self, user: User, booking: Booking) -> bool:
        """Check if user can modify a booking."""
        if booking.user == user:
            return True
        
        try:
            user_profile = user.userprofile
            return user_profile.role in ['technician', 'sysadmin']
        except UserProfile.DoesNotExist:
            return False
    
    def _send_cancellation_notifications(
        self, 
        booking: Booking, 
        cancelled_by: User, 
        reason: str
    ):
        """Send notifications for booking cancellation."""
        # Implementation would depend on notification system
        pass


# Singleton instance
booking_service = BookingService()