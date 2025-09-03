# booking/checkin_service.py
"""
Check-in/Check-out service for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q, F, Count, Avg, Sum
from django.db import transaction
from ..models import (
    Booking, CheckInOutEvent, UsageAnalytics, Resource, UserProfile
)
from ..notifications import notification_service

logger = logging.getLogger(__name__)


class CheckInService:
    """Service for managing booking check-ins and check-outs."""
    
    def __init__(self):
        self.notification_service = notification_service
    
    def check_in_booking(
        self, 
        booking_id: int, 
        user, 
        actual_start_time: Optional[datetime] = None,
        notes: str = "",
        ip_address: str = None,
        user_agent: str = None,
        location_data: dict = None
    ) -> Tuple[bool, str]:
        """Check in to a booking."""
        try:
            booking = Booking.objects.get(id=booking_id)
            
            # Verify user permissions
            if not self._can_user_checkin(booking, user):
                return False, "You don't have permission to check in to this booking."
            
            if not booking.can_check_in:
                return False, f"Cannot check in: {self._get_checkin_reason(booking)}"
            
            # Perform check-in
            with transaction.atomic():
                booking.check_in(user, actual_start_time)
                
                # Create detailed event record
                event = CheckInOutEvent.objects.filter(
                    booking=booking, 
                    event_type='check_in'
                ).order_by('-timestamp').first()
                
                if event:
                    event.notes = notes
                    event.ip_address = ip_address
                    event.user_agent = user_agent
                    event.location_data = location_data or {}
                    event.save()
                
                # Send confirmation notification
                self._send_checkin_notification(booking, user)
                
                logger.info(f"User {user.username} checked in to booking {booking.id}")
                return True, "Successfully checked in!"
                
        except Booking.DoesNotExist:
            return False, "Booking not found."
        except Exception as e:
            logger.error(f"Error checking in to booking {booking_id}: {str(e)}")
            return False, f"Check-in failed: {str(e)}"
    
    def check_out_booking(
        self, 
        booking_id: int, 
        user, 
        actual_end_time: Optional[datetime] = None,
        notes: str = "",
        ip_address: str = None,
        user_agent: str = None,
        location_data: dict = None
    ) -> Tuple[bool, str]:
        """Check out of a booking."""
        try:
            booking = Booking.objects.get(id=booking_id)
            
            # Verify user permissions
            if not self._can_user_checkout(booking, user):
                return False, "You don't have permission to check out of this booking."
            
            if not booking.can_check_out:
                return False, "Cannot check out - not currently checked in."
            
            # Perform check-out
            with transaction.atomic():
                booking.check_out(user, actual_end_time)
                
                # Create detailed event record
                event = CheckInOutEvent.objects.filter(
                    booking=booking, 
                    event_type='check_out'
                ).order_by('-timestamp').first()
                
                if event:
                    event.notes = notes
                    event.ip_address = ip_address
                    event.user_agent = user_agent
                    event.location_data = location_data or {}
                    event.save()
                
                # Send confirmation notification
                self._send_checkout_notification(booking, user)
                
                # Update usage analytics
                self._update_usage_analytics(booking)
                
                logger.info(f"User {user.username} checked out of booking {booking.id}")
                return True, "Successfully checked out!"
                
        except Booking.DoesNotExist:
            return False, "Booking not found."
        except Exception as e:
            logger.error(f"Error checking out of booking {booking_id}: {str(e)}")
            return False, f"Check-out failed: {str(e)}"
    
    def mark_no_show(
        self, 
        booking_id: int, 
        user,
        notes: str = ""
    ) -> Tuple[bool, str]:
        """Mark a booking as no-show (admin only)."""
        try:
            booking = Booking.objects.get(id=booking_id)
            
            # Check if user has permission (lab managers/sysadmins only)
            try:
                user_profile = user.userprofile
                if user_profile.role not in ['lab_manager', 'sysadmin']:
                    return False, "Only lab managers can mark bookings as no-show."
            except:
                return False, "User profile not found."
            
            if booking.checked_in_at is not None:
                return False, "Cannot mark as no-show - user already checked in."
            
            # Mark as no-show
            with transaction.atomic():
                booking.mark_no_show(user)
                
                # Add notes to the event
                event = CheckInOutEvent.objects.filter(
                    booking=booking, 
                    event_type='no_show'
                ).order_by('-timestamp').first()
                
                if event:
                    event.notes = notes
                    event.save()
                
                # Send notification to booking owner
                self._send_noshow_notification(booking, user)
                
                # Update usage analytics
                self._update_usage_analytics(booking)
                
                logger.info(f"Booking {booking.id} marked as no-show by {user.username}")
                return True, "Booking marked as no-show."
                
        except Booking.DoesNotExist:
            return False, "Booking not found."
        except Exception as e:
            logger.error(f"Error marking booking {booking_id} as no-show: {str(e)}")
            return False, f"Failed to mark as no-show: {str(e)}"
    
    def get_current_checkins(self, resource: Optional[Resource] = None) -> List[Booking]:
        """Get all current check-ins, optionally filtered by resource."""
        queryset = Booking.objects.filter(
            checked_in_at__isnull=False,
            checked_out_at__isnull=True,
            status__in=['approved', 'confirmed']
        ).select_related('resource', 'user')
        
        if resource:
            queryset = queryset.filter(resource=resource)
        
        return list(queryset.order_by('checked_in_at'))
    
    def get_overdue_checkins(self) -> List[Booking]:
        """Get bookings that are overdue for check-in."""
        overdue_threshold = timezone.now() - timedelta(minutes=15)
        
        return list(Booking.objects.filter(
            start_time__lt=overdue_threshold,
            checked_in_at__isnull=True,
            no_show=False,
            status__in=['approved', 'confirmed']
        ).select_related('resource', 'user'))
    
    def get_overdue_checkouts(self) -> List[Booking]:
        """Get bookings that are overdue for check-out."""
        overdue_threshold = timezone.now() - timedelta(minutes=15)
        
        return list(Booking.objects.filter(
            end_time__lt=overdue_threshold,
            checked_in_at__isnull=False,
            checked_out_at__isnull=True,
            status__in=['approved', 'confirmed']
        ).select_related('resource', 'user'))
    
    def process_automatic_checkouts(self) -> int:
        """Process automatic check-outs for overdue bookings."""
        overdue_bookings = self.get_overdue_checkouts()
        checked_out_count = 0
        
        for booking in overdue_bookings:
            try:
                if booking.auto_check_out():
                    checked_out_count += 1
                    
                    # Send notification
                    self._send_auto_checkout_notification(booking)
                    
                    # Update analytics
                    self._update_usage_analytics(booking)
                    
            except Exception as e:
                logger.error(f"Failed to auto check-out booking {booking.id}: {str(e)}")
        
        if checked_out_count > 0:
            logger.info(f"Auto checked-out {checked_out_count} overdue bookings")
        
        return checked_out_count
    
    def send_checkin_reminders(self) -> int:
        """Send check-in reminders to users who should be checking in soon."""
        # Find bookings starting in the next 10 minutes
        reminder_start = timezone.now() + timedelta(minutes=5)
        reminder_end = timezone.now() + timedelta(minutes=15)
        
        bookings_to_remind = Booking.objects.filter(
            start_time__gte=reminder_start,
            start_time__lte=reminder_end,
            checked_in_at__isnull=True,
            no_show=False,
            check_in_reminder_sent=False,
            status__in=['approved', 'confirmed']
        ).select_related('resource', 'user')
        
        reminded_count = 0
        
        for booking in bookings_to_remind:
            try:
                self._send_checkin_reminder(booking)
                booking.check_in_reminder_sent = True
                booking.save(update_fields=['check_in_reminder_sent'])
                reminded_count += 1
                
            except Exception as e:
                logger.error(f"Failed to send check-in reminder for booking {booking.id}: {str(e)}")
        
        if reminded_count > 0:
            logger.info(f"Sent {reminded_count} check-in reminders")
        
        return reminded_count
    
    def send_checkout_reminders(self) -> int:
        """Send check-out reminders to users approaching their end time."""
        # Find bookings ending in the next 10 minutes
        reminder_start = timezone.now() + timedelta(minutes=5)
        reminder_end = timezone.now() + timedelta(minutes=15)
        
        bookings_to_remind = Booking.objects.filter(
            end_time__gte=reminder_start,
            end_time__lte=reminder_end,
            checked_in_at__isnull=False,
            checked_out_at__isnull=True,
            check_out_reminder_sent=False,
            status__in=['approved', 'confirmed']
        ).select_related('resource', 'user')
        
        reminded_count = 0
        
        for booking in bookings_to_remind:
            try:
                self._send_checkout_reminder(booking)
                booking.check_out_reminder_sent = True
                booking.save(update_fields=['check_out_reminder_sent'])
                reminded_count += 1
                
            except Exception as e:
                logger.error(f"Failed to send check-out reminder for booking {booking.id}: {str(e)}")
        
        if reminded_count > 0:
            logger.info(f"Sent {reminded_count} check-out reminders")
        
        return reminded_count
    
    def get_usage_analytics(
        self, 
        resource: Optional[Resource] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """Get usage analytics for resources."""
        
        queryset = UsageAnalytics.objects.all()
        
        if resource:
            queryset = queryset.filter(resource=resource)
        
        if start_date:
            queryset = queryset.filter(date__gte=start_date.date())
        
        if end_date:
            queryset = queryset.filter(date__lte=end_date.date())
        
        # Aggregate statistics
        stats = queryset.aggregate(
            total_bookings=Sum('total_bookings'),
            completed_bookings=Sum('completed_bookings'),
            no_show_bookings=Sum('no_show_bookings'),
            avg_utilization=Avg('utilization_rate'),
            avg_efficiency=Avg('efficiency_rate'),
            avg_no_show_rate=Avg('no_show_rate'),
            total_booked_minutes=Sum('total_booked_minutes'),
            total_actual_minutes=Sum('total_actual_minutes'),
            total_wasted_minutes=Sum('total_wasted_minutes')
        )
        
        # Add calculated metrics
        if stats['total_bookings']:
            stats['completion_rate'] = (stats['completed_bookings'] / stats['total_bookings']) * 100
        else:
            stats['completion_rate'] = 0
        
        return stats
    
    def _can_user_checkin(self, booking: Booking, user) -> bool:
        """Check if user can check in to this booking."""
        # User is the booking owner
        if booking.user == user:
            return True
        
        # User is an attendee
        if booking.attendees.filter(id=user.id).exists():
            return True
        
        # User is a lab manager/admin
        try:
            user_profile = user.userprofile
            if user_profile.role in ['lab_manager', 'sysadmin']:
                return True
        except:
            pass
        
        return False
    
    def _can_user_checkout(self, booking: Booking, user) -> bool:
        """Check if user can check out of this booking."""
        return self._can_user_checkin(booking, user)
    
    def _get_checkin_reason(self, booking: Booking) -> str:
        """Get reason why check-in is not allowed."""
        if booking.status not in ['approved', 'confirmed']:
            return f"Booking status is {booking.status}"
        
        if booking.checked_in_at is not None:
            return "Already checked in"
        
        now = timezone.now()
        if now < booking.start_time - timedelta(minutes=15):
            return "Too early to check in"
        
        if now > booking.end_time:
            return "Booking time has passed"
        
        return "Unknown reason"
    
    def _send_checkin_notification(self, booking: Booking, user):
        """Send check-in confirmation notification."""
        self.notification_service.create_notification(
            user=booking.user,
            notification_type='booking_reminder',  # Reusing existing type
            title=f'Checked In: {booking.resource.name}',
            message=f'Successfully checked in to {booking.resource.name}. Don\'t forget to check out when you\'re done!',
            priority='medium',
            booking=booking,
            resource=booking.resource
        )
    
    def _send_checkout_notification(self, booking: Booking, user):
        """Send check-out confirmation notification."""
        duration = booking.actual_duration
        duration_str = f"{int(duration.total_seconds() // 3600)}h {int((duration.total_seconds() % 3600) // 60)}m" if duration else "Unknown"
        
        self.notification_service.create_notification(
            user=booking.user,
            notification_type='booking_confirmed',  # Reusing existing type
            title=f'Checked Out: {booking.resource.name}',
            message=f'Successfully checked out of {booking.resource.name}. Usage time: {duration_str}',
            priority='low',
            booking=booking,
            resource=booking.resource
        )
    
    def _send_noshow_notification(self, booking: Booking, admin_user):
        """Send no-show notification to booking owner."""
        self.notification_service.create_notification(
            user=booking.user,
            notification_type='booking_cancelled',  # Reusing existing type
            title=f'No Show: {booking.resource.name}',
            message=f'Your booking for {booking.resource.name} has been marked as a no-show. Please contact the lab if this was an error.',
            priority='high',
            booking=booking,
            resource=booking.resource
        )
    
    def _send_auto_checkout_notification(self, booking: Booking):
        """Send automatic check-out notification."""
        self.notification_service.create_notification(
            user=booking.user,
            notification_type='booking_reminder',  # Reusing existing type
            title=f'Auto Checked Out: {booking.resource.name}',
            message=f'You were automatically checked out of {booking.resource.name} at the end of your booking time.',
            priority='medium',
            booking=booking,
            resource=booking.resource
        )
    
    def _send_checkin_reminder(self, booking: Booking):
        """Send check-in reminder."""
        self.notification_service.create_notification(
            user=booking.user,
            notification_type='booking_reminder',
            title=f'Check-in Reminder: {booking.resource.name}',
            message=f'Your booking for {booking.resource.name} starts in {int((booking.start_time - timezone.now()).total_seconds() // 60)} minutes. Don\'t forget to check in!',
            priority='high',
            booking=booking,
            resource=booking.resource
        )
    
    def _send_checkout_reminder(self, booking: Booking):
        """Send check-out reminder."""
        self.notification_service.create_notification(
            user=booking.user,
            notification_type='booking_reminder',
            title=f'Check-out Reminder: {booking.resource.name}',
            message=f'Your booking for {booking.resource.name} ends in {int((booking.end_time - timezone.now()).total_seconds() // 60)} minutes. Please remember to check out.',
            priority='medium',
            booking=booking,
            resource=booking.resource
        )
    
    def _update_usage_analytics(self, booking: Booking):
        """Update usage analytics for a completed booking."""
        try:
            # Get or create analytics record for today
            analytics, created = UsageAnalytics.objects.get_or_create(
                resource=booking.resource,
                date=timezone.now().date(),
                defaults={}
            )
            
            # Update booking counts
            analytics.total_bookings = F('total_bookings') + 1
            
            if booking.no_show:
                analytics.no_show_bookings = F('no_show_bookings') + 1
            elif booking.checked_out_at:
                analytics.completed_bookings = F('completed_bookings') + 1
            elif booking.status == 'cancelled':
                analytics.cancelled_bookings = F('cancelled_bookings') + 1
            
            # Update time statistics
            booked_minutes = int(booking.duration.total_seconds() // 60)
            analytics.total_booked_minutes = F('total_booked_minutes') + booked_minutes
            
            if booking.actual_duration:
                actual_minutes = int(booking.actual_duration.total_seconds() // 60)
                analytics.total_actual_minutes = F('total_actual_minutes') + actual_minutes
                
                wasted_minutes = max(0, booked_minutes - actual_minutes)
                analytics.total_wasted_minutes = F('total_wasted_minutes') + wasted_minutes
            
            analytics.save()
            
            # Recalculate rates (need to refresh from DB first)
            analytics.refresh_from_db()
            self._recalculate_analytics_rates(analytics)
            
        except Exception as e:
            logger.error(f"Failed to update usage analytics for booking {booking.id}: {str(e)}")
    
    def _recalculate_analytics_rates(self, analytics: UsageAnalytics):
        """Recalculate percentage rates for analytics."""
        try:
            # Calculate utilization rate (actual usage / total available time)
            # Assume 9 hours available per day (9 AM - 6 PM)
            available_minutes_per_day = 9 * 60
            analytics.utilization_rate = min(analytics.total_actual_minutes / available_minutes_per_day, 1.0)
            
            # Calculate efficiency rate (actual usage / booked time)
            if analytics.total_booked_minutes > 0:
                analytics.efficiency_rate = analytics.total_actual_minutes / analytics.total_booked_minutes
            else:
                analytics.efficiency_rate = 0.0
            
            # Calculate no-show rate
            if analytics.total_bookings > 0:
                analytics.no_show_rate = analytics.no_show_bookings / analytics.total_bookings
            else:
                analytics.no_show_rate = 0.0
            
            analytics.save(update_fields=[
                'utilization_rate', 'efficiency_rate', 'no_show_rate', 'updated_at'
            ])
            
        except Exception as e:
            logger.error(f"Failed to recalculate analytics rates: {str(e)}")


# Global service instance
checkin_service = CheckInService()