#!/usr/bin/env python3
"""
Debug script to check what's preventing booking deletion.
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labitory.settings.development')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

from booking.models import Booking
from django.db import connection

def debug_booking_deletion():
    print("Debugging booking deletion issue...")
    
    # Find any booking to test with
    booking = Booking.objects.first()
    if not booking:
        print("No bookings found. Creating a minimal test booking...")
        
        # Create minimal test data
        from django.contrib.auth.models import User
        from booking.models.resources import Resource
        from booking.models.core import UserProfile
        from django.utils import timezone
        from datetime import timedelta
        
        # Use existing user or create one
        user = User.objects.first()
        if not user:
            user = User.objects.create_user('test', 'test@test.com', 'test123')
            UserProfile.objects.create(user=user, role='student')
        
        # Use existing resource or create one
        resource = Resource.objects.first()
        if not resource:
            resource = Resource.objects.create(
                name='Test',
                resource_type='equipment',
                description='Test',
                location='Lab',
                capacity=1,
                max_booking_hours=8,
                is_active=True
            )
        
        # Create minimal booking during business hours
        start_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        
        booking = Booking.objects.create(
            user=user,
            resource=resource,
            start_time=start_time,
            end_time=end_time,
            title='Test Deletion',
            status='cancelled'
        )
        print(f"Created test booking: {booking.title} (ID: {booking.id})")
        
    print(f"Testing with booking: {booking} (Status: {booking.status}, ID: {booking.id})")
    
    print(f"User: {booking.user}")
    print(f"Resource: {booking.resource}")
    print(f"Start time: {booking.start_time}")
    print(f"End time: {booking.end_time}")
    
    # Check all related objects
    print("\n--- Related Objects ---")
    
    # BookingAttendee
    attendees = booking.bookingattendee_set.all()
    print(f"BookingAttendees: {len(attendees)}")
    
    # BookingHistory  
    history = booking.history.all()
    print(f"BookingHistory records: {len(history)}")
    
    # CheckInOutEvent
    checkin_events = booking.checkin_events.all()
    print(f"CheckInOutEvent records: {len(checkin_events)}")
    
    # Notifications
    notifications = booking.notification_set.all()
    print(f"Notifications: {len(notifications)}")
    
    # ChecklistResponse
    checklist_responses = booking.checklist_responses.all()
    print(f"ChecklistResponse records: {len(checklist_responses)}")
    
    # WaitingListEntry (resulting_booking)
    waiting_list_entries = booking.waiting_list_entry.all()
    print(f"WaitingListEntry records: {len(waiting_list_entries)}")
    
    # GoogleCalendarSyncLog
    try:
        from booking.models.calendar import GoogleCalendarSyncLog
        calendar_sync_logs = GoogleCalendarSyncLog.objects.filter(booking=booking)
        print(f"GoogleCalendarSyncLog records: {len(calendar_sync_logs)}")
    except ImportError:
        print("GoogleCalendarSyncLog model not found")
    
    # BillingRecord (OneToOne)
    try:
        billing_record = booking.billing_record
        print(f"BillingRecord: Yes")
    except:
        print(f"BillingRecord: No")
    
    # WaitingListNotification
    try:
        from booking.models.waiting_list import WaitingListNotification
        waiting_notifications = WaitingListNotification.objects.filter(booking_created=booking)
        print(f"WaitingListNotification records: {len(waiting_notifications)}")
    except ImportError:
        print("WaitingListNotification model not found")
    
    # ResourceIssue (related_booking)  
    resource_issues = booking.reported_issues.all()
    print(f"ResourceIssue records: {len(resource_issues)}")
    
    # Many-to-many relationships
    prerequisite_count = booking.prerequisite_bookings.count()
    dependent_count = booking.dependent_bookings.count()
    print(f"Prerequisite bookings: {prerequisite_count}")
    print(f"Dependent bookings: {dependent_count}")
    
    print(f"\n--- Attempting Safe Deletion ---")
    
    # Try to delete with the same method as the view
    try:
        from django.db import transaction
        
        print("Starting safe deletion process...")
        
        # Disable foreign keys for the entire connection
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF;")
        print(f"DEBUG: Disabled foreign keys for entire connection")
        
        # Delete related objects manually to avoid foreign key constraints
        
        # Delete notifications first
        deleted_notifications = booking.notification_set.all().delete()
        print(f"Deleted notifications: {deleted_notifications}")
        
        # Delete booking history
        deleted_history = booking.history.all().delete()
        print(f"Deleted booking history: {deleted_history}")
        
        # Delete booking attendees
        deleted_attendees = booking.bookingattendee_set.all().delete()
        print(f"Deleted booking attendees: {deleted_attendees}")
        
        # Delete checkin/checkout events
        deleted_events = booking.checkin_events.all().delete()
        print(f"Deleted checkin events: {deleted_events}")
        
        # Delete checklist responses
        deleted_responses = booking.checklist_responses.all().delete()
        print(f"Deleted checklist responses: {deleted_responses}")
        
        # Delete billing record (OneToOne)
        try:
            if hasattr(booking, 'billing_record'):
                booking.billing_record.delete()
                print("Deleted billing record: Yes")
            else:
                print("Deleted billing record: No billing record found")
        except Exception as e:
            print(f"Billing record deletion error: {e}")
        
        # Delete Google Calendar sync logs
        try:
            from booking.models.calendar import GoogleCalendarSyncLog
            deleted_sync_logs = GoogleCalendarSyncLog.objects.filter(booking=booking).delete()
            print(f"Deleted Google Calendar sync logs: {deleted_sync_logs}")
        except ImportError:
            print("Google Calendar sync logs: Import error")
        
        # Delete waiting list notifications related to this booking
        try:
            from booking.models.waiting_list import WaitingListNotification
            deleted_waiting_notifications = WaitingListNotification.objects.filter(booking_created=booking).delete()
            print(f"Deleted waiting list notifications: {deleted_waiting_notifications}")
        except ImportError:
            print("Waiting list notifications: Import error")
        
        # Set waiting list entries to null (should happen automatically)
        updated_waitlist = booking.waiting_list_entry.update(resulting_booking=None)
        print(f"Updated waiting list entries: {updated_waitlist}")
        
        # Set resource issues to null (should happen automatically)
        updated_issues = booking.reported_issues.update(related_booking=None)
        print(f"Updated resource issues: {updated_issues}")
        
        # Clear many-to-many relationships
        prerequisite_count = booking.prerequisite_bookings.count()
        dependent_count = booking.dependent_bookings.count()
        booking.prerequisite_bookings.clear()
        print(f"Cleared prerequisite bookings: {prerequisite_count}")
        
        # Handle dependent bookings (remove this booking as prerequisite)
        for dependent in booking.dependent_bookings.all():
            dependent.prerequisite_bookings.remove(booking)
        print(f"Removed from dependent bookings: {dependent_count}")
        
        # Finally delete the booking
        print("Deleting the booking...")
        booking.delete()
        
        # Re-enable foreign key checks
        cursor.execute("PRAGMA foreign_keys = ON;")
        print(f"DEBUG: Re-enabled foreign keys after deletion")
        
        print("SUCCESS: Booking deleted successfully!")
            
    except Exception as e:
        print(f"ERROR: {e}")
        print(f"Error type: {type(e).__name__}")
        
        # Get more detailed error info
        import traceback
        print(f"\nFull traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    debug_booking_deletion()