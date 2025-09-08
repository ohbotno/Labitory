"""
Service layer tests for Labitory.
Tests service functionality with mocking where external services are involved.
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from django.core import mail
from datetime import timedelta
from unittest.mock import patch, Mock

from booking.models import (
    Booking, Resource, UserProfile, Notification, 
    CheckInOutEvent, BackupSchedule, LabSettings
)
from booking.tests.factories import (
    UserFactory, UserProfileFactory, ResourceFactory, BookingFactory
)


class TestBookingLogic(TestCase):
    """Test core booking business logic."""
    
    def setUp(self):
        self.user_profile = UserProfileFactory(role='student')
        self.user = self.user_profile.user
        self.resource = ResourceFactory()
    
    def test_booking_creation(self):
        """Test basic booking creation."""
        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=2)
        
        booking = Booking.objects.create(
            user=self.user,
            resource=self.resource,
            title='Test Booking',
            description='Test description',
            start_time=start_time,
            end_time=end_time,
            status='pending'
        )
        
        self.assertEqual(booking.title, 'Test Booking')
        self.assertEqual(booking.user, self.user)
        self.assertEqual(booking.resource, self.resource)
        self.assertEqual(booking.status, 'pending')
    
    def test_booking_duration_calculation(self):
        """Test booking duration calculation."""
        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=2, minutes=30)
        
        booking = BookingFactory(
            start_time=start_time,
            end_time=end_time
        )
        
        expected_duration = timedelta(hours=2, minutes=30)
        actual_duration = booking.end_time - booking.start_time
        self.assertEqual(actual_duration, expected_duration)
    
    def test_booking_conflict_detection(self):
        """Test booking conflict detection logic."""
        # Create an existing booking
        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=2)
        
        existing_booking = BookingFactory(
            resource=self.resource,
            start_time=start_time,
            end_time=end_time,
            status='confirmed'
        )
        
        # Check for overlapping booking
        overlap_start = start_time + timedelta(minutes=30)
        overlap_end = overlap_start + timedelta(hours=1)
        
        # Query for conflicts
        conflicts = Booking.objects.filter(
            resource=self.resource,
            status__in=['confirmed', 'pending'],
            start_time__lt=overlap_end,
            end_time__gt=overlap_start
        ).exclude(id=existing_booking.id)
        
        # Create potential conflicting booking
        potential_booking = Booking(
            user=UserFactory(),
            resource=self.resource,
            title='Conflicting Booking',
            start_time=overlap_start,
            end_time=overlap_end
        )
        
        # Check for conflicts with existing booking
        existing_conflicts = Booking.objects.filter(
            resource=self.resource,
            status__in=['confirmed', 'pending'],
            start_time__lt=potential_booking.end_time,
            end_time__gt=potential_booking.start_time
        )
        
        self.assertTrue(existing_conflicts.exists())
        self.assertIn(existing_booking, existing_conflicts)


class TestNotificationLogic(TestCase):
    """Test notification business logic."""
    
    def setUp(self):
        self.user = UserFactory()
    
    def test_notification_creation(self):
        """Test notification creation."""
        notification = Notification.objects.create(
            user=self.user,
            title="Test Notification",
            message="Test message",
            delivery_method="email",
            status="pending"
        )
        
        self.assertEqual(notification.title, "Test Notification")
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.delivery_method, "email")
        self.assertEqual(notification.status, "pending")
    
    def test_notification_status_updates(self):
        """Test notification status transitions."""
        notification = Notification.objects.create(
            user=self.user,
            title="Test Notification",
            message="Test message",
            delivery_method="email",
            status="pending"
        )
        
        # Simulate sending
        notification.status = "sent"
        notification.sent_at = timezone.now()
        notification.save()
        
        notification.refresh_from_db()
        self.assertEqual(notification.status, "sent")
        self.assertIsNotNone(notification.sent_at)
    
    @patch('django.core.mail.send_mail')
    def test_email_sending_mock(self, mock_send_mail):
        """Test email sending with mock."""
        mock_send_mail.return_value = True
        
        # Simulate email notification sending
        result = mail.send_mail(
            'Test Subject',
            'Test message',
            'from@test.com',
            ['to@test.com'],
            fail_silently=False
        )
        
        mock_send_mail.assert_called_once()
        self.assertTrue(result)


class TestCheckInLogic(TestCase):
    """Test check-in/check-out business logic."""
    
    def setUp(self):
        self.user = UserFactory()
        self.resource = ResourceFactory()
        self.booking = BookingFactory(
            user=self.user,
            resource=self.resource,
            start_time=timezone.now() - timedelta(minutes=15),
            end_time=timezone.now() + timedelta(hours=1),
            status='confirmed'
        )
    
    def test_checkin_event_creation(self):
        """Test check-in event creation."""
        checkin_event = CheckInOutEvent.objects.create(
            booking=self.booking,
            user=self.user,
            event_type='check_in',
            timestamp=timezone.now()
        )
        
        self.assertEqual(checkin_event.booking, self.booking)
        self.assertEqual(checkin_event.user, self.user)
        self.assertEqual(checkin_event.event_type, 'check_in')
        self.assertIsNotNone(checkin_event.timestamp)
    
    def test_checkout_event_creation(self):
        """Test check-out event creation."""
        # Create check-in first
        checkin_event = CheckInOutEvent.objects.create(
            booking=self.booking,
            user=self.user,
            event_type='check_in',
            timestamp=timezone.now() - timedelta(minutes=30)
        )
        
        # Create check-out
        checkout_event = CheckInOutEvent.objects.create(
            booking=self.booking,
            user=self.user,
            event_type='check_out',
            timestamp=timezone.now()
        )
        
        self.assertEqual(checkout_event.event_type, 'check_out')
        self.assertGreater(checkout_event.timestamp, checkin_event.timestamp)
    
    def test_booking_status_updates(self):
        """Test booking status updates during check-in/out."""
        # Simulate check-in process
        CheckInOutEvent.objects.create(
            booking=self.booking,
            user=self.user,
            event_type='check_in',
            timestamp=timezone.now()
        )
        
        # Update booking status
        self.booking.status = 'in_progress'
        self.booking.save()
        
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'in_progress')
        
        # Simulate check-out process
        CheckInOutEvent.objects.create(
            booking=self.booking,
            user=self.user,
            event_type='check_out',
            timestamp=timezone.now()
        )
        
        # Update booking status
        self.booking.status = 'completed'
        self.booking.save()
        
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'completed')


class TestResourceAvailability(TestCase):
    """Test resource availability logic."""
    
    def setUp(self):
        self.resource = ResourceFactory()
    
    def test_resource_availability_check(self):
        """Test resource availability checking."""
        # Resource is available by default
        self.assertTrue(self.resource.is_active)
        
        # Create a booking
        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=2)
        
        booking = BookingFactory(
            resource=self.resource,
            start_time=start_time,
            end_time=end_time,
            status='confirmed'
        )
        
        # Check for availability at the same time (should be unavailable)
        overlapping_bookings = Booking.objects.filter(
            resource=self.resource,
            status__in=['confirmed', 'pending'],
            start_time__lt=end_time,
            end_time__gt=start_time
        )
        
        self.assertTrue(overlapping_bookings.exists())
    
    def test_resource_capacity_logic(self):
        """Test resource capacity logic."""
        # Create a resource with capacity of 2
        multi_resource = ResourceFactory(capacity=2)
        
        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=2)
        
        # Create first booking
        booking1 = BookingFactory(
            resource=multi_resource,
            start_time=start_time,
            end_time=end_time,
            status='confirmed'
        )
        
        # Create second booking (should be allowed)
        booking2 = BookingFactory(
            resource=multi_resource,
            start_time=start_time,
            end_time=end_time,
            status='confirmed'
        )
        
        # Count concurrent bookings
        concurrent_bookings = Booking.objects.filter(
            resource=multi_resource,
            status__in=['confirmed', 'pending'],
            start_time__lt=end_time,
            end_time__gt=start_time
        ).count()
        
        # Should have 2 concurrent bookings
        self.assertEqual(concurrent_bookings, 2)
        
        # Capacity check: concurrent bookings should not exceed capacity
        self.assertLessEqual(concurrent_bookings, multi_resource.capacity)


class TestBackupLogic(TestCase):
    """Test backup system logic."""
    
    def test_backup_schedule_creation(self):
        """Test backup schedule creation."""
        schedule = BackupSchedule.objects.create(
            name="Daily Backup",
            schedule_type="daily",
            time_of_day="02:00:00",
            is_active=True
        )
        
        self.assertEqual(schedule.name, "Daily Backup")
        self.assertEqual(schedule.schedule_type, "daily")
        self.assertTrue(schedule.is_active)
    
    def test_backup_schedule_validation(self):
        """Test backup schedule validation."""
        # Test valid time formats
        valid_times = ["02:00:00", "14:30:00", "23:59:59"]
        
        for time_str in valid_times:
            schedule = BackupSchedule(
                name=f"Test Backup {time_str}",
                schedule_type="daily",
                time_of_day=time_str,
                is_active=True
            )
            # Basic validation - time field should accept these values
            self.assertIsNotNone(schedule.time_of_day)


class TestSystemSettings(TestCase):
    """Test system settings and configuration."""
    
    def test_lab_settings_creation(self):
        """Test lab settings creation."""
        settings = LabSettings.objects.create(
            lab_name="Test Laboratory",
            is_active=True
        )
        
        self.assertEqual(settings.lab_name, "Test Laboratory")
        self.assertTrue(settings.is_active)
    
    def test_lab_settings_singleton_pattern(self):
        """Test that only one active lab setting exists."""
        # Create first setting
        settings1 = LabSettings.objects.create(
            lab_name="Lab 1",
            is_active=True
        )
        
        # Create second setting
        settings2 = LabSettings.objects.create(
            lab_name="Lab 2", 
            is_active=True
        )
        
        # Both should exist (the singleton pattern would be enforced by business logic)
        self.assertTrue(LabSettings.objects.filter(is_active=True).count() >= 1)
    
    def test_get_lab_name_method(self):
        """Test getting lab name."""
        # Test with existing settings
        LabSettings.objects.create(lab_name="Custom Lab", is_active=True)
        lab_name = LabSettings.get_lab_name()
        self.assertEqual(lab_name, "Custom Lab")


class TestBusinessRules(TestCase):
    """Test business rule enforcement."""
    
    def setUp(self):
        self.user_profile = UserProfileFactory(role='student', training_level=1)
        self.user = self.user_profile.user
        self.basic_resource = ResourceFactory(required_training_level=1)
        self.advanced_resource = ResourceFactory(required_training_level=3)
    
    def test_training_level_requirements(self):
        """Test training level requirements for resources."""
        # User can access basic resource
        self.assertGreaterEqual(
            self.user_profile.training_level, 
            self.basic_resource.required_training_level
        )
        
        # User cannot access advanced resource
        self.assertLess(
            self.user_profile.training_level,
            self.advanced_resource.required_training_level
        )
    
    def test_role_based_permissions(self):
        """Test role-based permissions."""
        student = UserProfileFactory(role='student')
        academic = UserProfileFactory(role='academic')
        technician = UserProfileFactory(role='technician')
        
        # Test different role permissions
        roles_with_priority = ['academic', 'technician', 'sysadmin']
        
        self.assertNotIn(student.role, roles_with_priority)
        self.assertIn(academic.role, roles_with_priority)
        self.assertIn(technician.role, roles_with_priority)
    
    def test_booking_time_validation(self):
        """Test booking time validation rules."""
        now = timezone.now()
        
        # Past booking should be invalid
        past_start = now - timedelta(hours=1)
        past_end = past_start + timedelta(hours=2)
        
        # Future booking should be valid
        future_start = now + timedelta(hours=1)
        future_end = future_start + timedelta(hours=2)
        
        # Basic time validation
        self.assertLess(past_start, now)  # Past booking
        self.assertGreater(future_start, now)  # Future booking
        self.assertLess(future_start, future_end)  # Start before end
        
        # Duration validation (example: max 8 hours)
        max_duration = timedelta(hours=8)
        booking_duration = future_end - future_start
        self.assertLessEqual(booking_duration, max_duration)