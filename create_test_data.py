#!/usr/bin/env python3
"""
Create test data for booking deletion testing.
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labitory.settings.development')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.contrib.auth.models import User
from booking.models.resources import Resource, ResourceType
from booking.models.bookings import Booking
from booking.models.notifications import Notification
from booking.models.users import UserProfile

def create_test_data():
    print("Creating test data...")
    
    # Create a user
    user, created = User.objects.get_or_create(
        username='testuser',
        defaults={
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'test@example.com'
        }
    )
    if created:
        user.set_password('testpassword')
        user.save()
        print(f"Created user: {user.username}")
        
        # Create user profile
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'phone_number': '+1234567890',
                'role': 'student'
            }
        )
    
    # Create a resource type
    resource_type, created = ResourceType.objects.get_or_create(
        name='Test Equipment',
        defaults={
            'description': 'Test equipment for booking deletion tests',
            'color': '#007bff'
        }
    )
    if created:
        print(f"Created resource type: {resource_type.name}")
    
    # Create a resource
    resource, created = Resource.objects.get_or_create(
        name='Test Machine',
        defaults={
            'resource_type': resource_type,
            'description': 'A test machine for booking tests',
            'location': 'Test Lab',
            'capacity': 1,
            'booking_duration': 60,
            'advance_booking_days': 30,
            'is_active': True
        }
    )
    if created:
        print(f"Created resource: {resource.name}")
    
    # Create a booking
    start_time = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_time = start_time + timedelta(hours=2)
    
    booking, created = Booking.objects.get_or_create(
        user=user,
        resource=resource,
        start_time=start_time,
        end_time=end_time,
        defaults={
            'title': 'Test Booking for Deletion',
            'description': 'A test booking to verify deletion functionality',
            'status': 'cancelled',  # Set to cancelled so it can be deleted
            'booking_type': 'regular'
        }
    )
    if created:
        print(f"Created booking: {booking.title} (ID: {booking.id})")
        
        # Create some related objects to test cascade deletion
        Notification.objects.create(
            user=user,
            booking=booking,
            notification_type='booking_confirmed',
            title='Booking Confirmed',
            message='Your test booking has been confirmed.',
            is_read=False
        )
        
        Notification.objects.create(
            user=user,
            booking=booking,
            notification_type='booking_cancelled',
            title='Booking Cancelled',
            message='Your test booking has been cancelled.',
            is_read=False
        )
        
        print(f"Created 2 notifications for the booking")
    else:
        print(f"Booking already exists: {booking.title} (ID: {booking.id})")
    
    print(f"\nTest data created successfully!")
    print(f"Booking ID {booking.id} is ready for deletion testing")
    
    return booking

if __name__ == "__main__":
    create_test_data()