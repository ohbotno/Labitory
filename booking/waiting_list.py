# booking/waiting_list.py
"""
Waiting list service for the Labitory.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q
from django.db import transaction
from .models import (
    WaitingListEntry, WaitingListNotification, Booking, 
    Resource, UserProfile
)
from .notifications import notification_service

logger = logging.getLogger(__name__)


class WaitingListService:
    """Service for managing waiting lists and availability notifications."""
    
    def __init__(self):
        self.notification_service = notification_service
    
    def add_to_waiting_list(
        self,
        user,
        resource: Resource,
        preferred_start: datetime,
        preferred_end: datetime,
        **options
    ) -> WaitingListEntry:
        """Add a user to the waiting list for a resource."""
        
        # Check if user already has an active entry for this resource and time
        existing_entry = WaitingListEntry.objects.filter(
            user=user,
            resource=resource,
            preferred_start_time=preferred_start,
            status='active'
        ).first()
        
        if existing_entry:
            raise ValueError("User already has an active waiting list entry for this resource and time")
        
        # Create new waiting list entry
        entry = WaitingListEntry.objects.create(
            user=user,
            resource=resource,
            preferred_start_time=preferred_start,
            preferred_end_time=preferred_end,
            min_duration_minutes=options.get('min_duration_minutes', 60),
            max_duration_minutes=options.get('max_duration_minutes', 240),
            flexible_start_time=options.get('flexible_start_time', True),
            flexible_duration=options.get('flexible_duration', True),
            max_days_advance=options.get('max_days_advance', 14),
            notify_immediately=options.get('notify_immediately', True),
            notification_advance_hours=options.get('notification_advance_hours', 24),
            priority=options.get('priority', 'normal'),
            auto_book=options.get('auto_book', False),
            notes=options.get('notes', '')
        )
        
        logger.info(f"Added {user.username} to waiting list for {resource.name}")
        
        # Send confirmation notification
        self.notification_service.create_notification(
            user=user,
            notification_type='waitlist_joined',
            title=f'Added to Waiting List: {resource.name}',
            message=f'You have been added to the waiting list for {resource.name}. You will be notified when a suitable time slot becomes available.',
            priority='medium',
            resource=resource,
            metadata={
                'waiting_list_entry_id': entry.id,
                'preferred_start': preferred_start.isoformat(),
                'preferred_end': preferred_end.isoformat(),
            }
        )
        
        return entry
    
    def check_availability_for_waiting_list(self, resource: Resource) -> List[Tuple[datetime, datetime]]:
        """Find available time slots for a resource."""
        now = timezone.now()
        future_limit = now + timedelta(days=30)  # Look 30 days ahead
        
        # Get all confirmed bookings for this resource
        existing_bookings = Booking.objects.filter(
            resource=resource,
            status__in=['confirmed', 'approved'],
            start_time__gte=now,
            start_time__lte=future_limit
        ).order_by('start_time')
        
        # Get maintenance windows
        from .models import Maintenance
        maintenance_windows = Maintenance.objects.filter(
            resource=resource,
            blocks_booking=True,
            start_time__gte=now,
            start_time__lte=future_limit
        ).order_by('start_time')
        
        # Combine and sort all blocked time periods
        blocked_periods = []
        
        for booking in existing_bookings:
            blocked_periods.append((booking.start_time, booking.end_time))
        
        for maintenance in maintenance_windows:
            blocked_periods.append((maintenance.start_time, maintenance.end_time))
        
        blocked_periods.sort(key=lambda x: x[0])
        
        # Find gaps between blocked periods
        available_slots = []
        current_time = now.replace(hour=9, minute=0, second=0, microsecond=0)  # Start at 9 AM
        
        # If current time is past 9 AM, start from next day
        if now.hour >= 18:
            current_time = current_time + timedelta(days=1)
        elif now.hour < 9:
            pass  # Use current day at 9 AM
        else:
            # Start from next hour, rounded up
            current_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        
        while current_time < future_limit:
            # Check if this is a valid working day and time
            if current_time.weekday() < 5:  # Monday to Friday
                day_start = current_time.replace(hour=9, minute=0, second=0, microsecond=0)
                day_end = current_time.replace(hour=18, minute=0, second=0, microsecond=0)
                
                # Find available slots for this day
                self._find_daily_availability(
                    day_start, day_end, blocked_periods, available_slots
                )
            
            current_time = current_time + timedelta(days=1)
        
        return available_slots
    
    def _find_daily_availability(
        self, 
        day_start: datetime, 
        day_end: datetime, 
        blocked_periods: List[Tuple[datetime, datetime]], 
        available_slots: List[Tuple[datetime, datetime]]
    ):
        """Find available slots within a single day."""
        current_time = day_start
        
        for block_start, block_end in blocked_periods:
            # If block is not on this day, skip
            if block_start.date() != day_start.date():
                continue
            
            # If there's a gap before this block, add it as available
            if current_time < block_start:
                gap_duration = block_start - current_time
                if gap_duration >= timedelta(minutes=30):  # Minimum 30-minute slots
                    available_slots.append((current_time, block_start))
            
            # Move current time to end of block
            if block_end > current_time:
                current_time = block_end
        
        # Check if there's time left at the end of the day
        if current_time < day_end:
            remaining_duration = day_end - current_time
            if remaining_duration >= timedelta(minutes=30):
                available_slots.append((current_time, day_end))
    
    def process_waiting_list_for_resource(self, resource: Resource) -> int:
        """Process waiting list entries for a specific resource when availability changes."""
        available_slots = self.check_availability_for_waiting_list(resource)
        
        if not available_slots:
            return 0
        
        # Get active waiting list entries for this resource, ordered by priority and creation time
        waiting_entries = WaitingListEntry.objects.filter(
            resource=resource,
            status='active'
        ).order_by('priority', 'created_at')
        
        notifications_sent = 0
        
        for entry in waiting_entries:
            if entry.is_expired:
                entry.status = 'expired'
                entry.save(update_fields=['status', 'updated_at'])
                continue
            
            # Find matching available slots
            matching_slots = []
            for slot_start, slot_end in available_slots:
                if entry.check_availability_match(slot_start, slot_end):
                    matching_slots.append((slot_start, slot_end))
            
            if matching_slots:
                # Use the first (earliest) matching slot
                slot_start, slot_end = matching_slots[0]
                
                # Create notification
                notification = WaitingListNotification.objects.create(
                    waiting_list_entry=entry,
                    available_start_time=slot_start,
                    available_end_time=slot_end
                )
                
                # Send notification to user
                self._send_availability_notification(entry, slot_start, slot_end, notification)
                
                # Mark entry as notified
                entry.mark_as_notified()
                
                # If auto-booking is enabled, create the booking
                if entry.auto_book:
                    booking = self._create_auto_booking(entry, slot_start, slot_end)
                    if booking:
                        notification.booking_created = booking
                        notification.user_response = 'accepted'
                        notification.responded_at = timezone.now()
                        notification.save(update_fields=['booking_created', 'user_response', 'responded_at'])
                        
                        entry.mark_as_fulfilled()
                
                notifications_sent += 1
                
                # Remove this slot from available slots to prevent double-booking
                available_slots = [slot for slot in available_slots if slot != (slot_start, slot_end)]
        
        logger.info(f"Processed waiting list for {resource.name}: {notifications_sent} notifications sent")
        return notifications_sent
    
    def _send_availability_notification(
        self, 
        entry: WaitingListEntry, 
        slot_start: datetime, 
        slot_end: datetime,
        notification: WaitingListNotification
    ):
        """Send availability notification to user."""
        duration = slot_end - slot_start
        
        self.notification_service.create_notification(
            user=entry.user,
            notification_type='waitlist_availability',
            title=f'Time Slot Available: {entry.resource.name}',
            message=f'A time slot is now available for {entry.resource.name} on {slot_start.strftime("%B %d, %Y")} from {slot_start.strftime("%I:%M %p")} to {slot_end.strftime("%I:%M %p")} ({int(duration.total_seconds() / 60)} minutes).',
            priority='high',
            resource=entry.resource,
            metadata={
                'waiting_list_entry_id': entry.id,
                'notification_id': notification.id,
                'available_start': slot_start.isoformat(),
                'available_end': slot_end.isoformat(),
                'response_deadline': notification.response_deadline.isoformat(),
            }
        )
    
    @transaction.atomic
    def _create_auto_booking(
        self, 
        entry: WaitingListEntry, 
        slot_start: datetime, 
        slot_end: datetime
    ) -> Optional[Booking]:
        """Create automatic booking for user."""
        try:
            booking = Booking.objects.create(
                resource=entry.resource,
                user=entry.user,
                title=f"Auto-booked: {entry.resource.name}",
                description=f"Automatically booked from waiting list. Original request: {entry.notes}",
                start_time=slot_start,
                end_time=slot_end,
                status='confirmed',  # Auto-bookings are automatically confirmed
                notes=f"Auto-booked from waiting list entry created on {entry.created_at.strftime('%Y-%m-%d')}"
            )
            
            logger.info(f"Auto-booked {entry.resource.name} for {entry.user.username} from {slot_start} to {slot_end}")
            return booking
            
        except Exception as e:
            logger.error(f"Failed to create auto-booking for {entry.user.username}: {str(e)}")
            return None
    
    def accept_availability_offer(self, notification_id: int, user) -> Tuple[bool, str]:
        """User accepts an availability offer."""
        try:
            notification = WaitingListNotification.objects.get(
                id=notification_id,
                waiting_list_entry__user=user
            )
            
            if notification.accept_offer():
                # Create booking
                booking = self._create_auto_booking(
                    notification.waiting_list_entry,
                    notification.available_start_time,
                    notification.available_end_time
                )
                
                if booking:
                    notification.booking_created = booking
                    notification.save(update_fields=['booking_created'])
                    return True, "Booking created successfully!"
                else:
                    return False, "Failed to create booking. Please try manual booking."
            else:
                return False, "Offer has expired or already been responded to."
                
        except WaitingListNotification.DoesNotExist:
            return False, "Notification not found."
        except Exception as e:
            logger.error(f"Error accepting availability offer: {str(e)}")
            return False, "An error occurred while processing your request."
    
    def decline_availability_offer(self, notification_id: int, user) -> Tuple[bool, str]:
        """User declines an availability offer."""
        try:
            notification = WaitingListNotification.objects.get(
                id=notification_id,
                waiting_list_entry__user=user
            )
            
            if notification.decline_offer():
                return True, "Offer declined. You remain on the waiting list."
            else:
                return False, "Offer has already been responded to."
                
        except WaitingListNotification.DoesNotExist:
            return False, "Notification not found."
    
    def get_user_waiting_list_entries(self, user) -> List[WaitingListEntry]:
        """Get all waiting list entries for a user."""
        return WaitingListEntry.objects.filter(
            user=user,
            status__in=['active', 'notified']
        ).select_related('resource').order_by('-created_at')
    
    def get_resource_waiting_list(self, resource: Resource) -> List[WaitingListEntry]:
        """Get waiting list for a specific resource."""
        return WaitingListEntry.objects.filter(
            resource=resource,
            status='active'
        ).select_related('user').order_by('priority', 'created_at')
    
    def cancel_waiting_list_entry(self, entry_id: int, user) -> Tuple[bool, str]:
        """Cancel a waiting list entry."""
        try:
            entry = WaitingListEntry.objects.get(
                id=entry_id,
                user=user,
                status__in=['active', 'notified']
            )
            
            entry.cancel()
            
            # Send cancellation notification
            self.notification_service.create_notification(
                user=user,
                notification_type='waitlist_cancelled',
                title=f'Removed from Waiting List: {entry.resource.name}',
                message=f'You have been removed from the waiting list for {entry.resource.name}.',
                priority='low',
                resource=entry.resource,
                metadata={
                    'waiting_list_entry_id': entry.id,
                }
            )
            
            return True, "Successfully removed from waiting list."
            
        except WaitingListEntry.DoesNotExist:
            return False, "Waiting list entry not found."
    
    def cleanup_expired_entries(self) -> int:
        """Clean up expired waiting list entries."""
        expired_count = WaitingListEntry.objects.filter(
            status='active',
            expires_at__lt=timezone.now()
        ).update(status='expired', updated_at=timezone.now())
        
        if expired_count > 0:
            logger.info(f"Marked {expired_count} waiting list entries as expired")
        
        return expired_count
    
    def get_waiting_list_statistics(self, resource: Resource = None) -> Dict:
        """Get waiting list statistics."""
        base_query = WaitingListEntry.objects
        
        if resource:
            base_query = base_query.filter(resource=resource)
        
        stats = {
            'total_active': base_query.filter(status='active').count(),
            'total_notified': base_query.filter(status='notified').count(),
            'total_fulfilled': base_query.filter(status='fulfilled').count(),
            'total_expired': base_query.filter(status='expired').count(),
            'total_cancelled': base_query.filter(status='cancelled').count(),
        }
        
        # Average wait time for fulfilled entries
        fulfilled_entries = base_query.filter(
            status='fulfilled',
            fulfilled_at__isnull=False
        )
        
        if fulfilled_entries.exists():
            wait_times = [
                (entry.fulfilled_at - entry.created_at).total_seconds() / 3600  # hours
                for entry in fulfilled_entries
            ]
            stats['avg_wait_time_hours'] = sum(wait_times) / len(wait_times)
        else:
            stats['avg_wait_time_hours'] = 0
        
        return stats


# Global service instance
waiting_list_service = WaitingListService()