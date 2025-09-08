"""
Advanced conflict detection tests for Labitory booking system.
Tests complex scenarios and edge cases in booking conflicts.
"""
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta, datetime
from unittest.mock import patch, Mock

from booking.models import Booking, Resource, Maintenance, UserProfile
from booking.conflicts import (
    BookingConflict, ConflictDetector, ConflictResolver,
    get_conflicts_for_booking, detect_maintenance_conflicts
)
from booking.tests.factories import (
    UserFactory, ResourceFactory, BookingFactory, 
    MaintenanceFactory, UserProfileFactory
)


class TestBookingConflictClass(TestCase):
    """Test the BookingConflict class functionality."""
    
    def setUp(self):
        self.user1 = UserFactory()
        self.user2 = UserFactory()
        self.resource = ResourceFactory()
        
        # Create overlapping bookings
        start_time = timezone.now() + timedelta(hours=1)
        self.booking1 = BookingFactory(
            user=self.user1,
            resource=self.resource,
            start_time=start_time,
            end_time=start_time + timedelta(hours=3),
            title="First Booking"
        )
        
        self.booking2 = BookingFactory(
            user=self.user2,
            resource=self.resource,
            start_time=start_time + timedelta(hours=2),
            end_time=start_time + timedelta(hours=4),
            title="Second Booking"
        )
    
    def test_conflict_creation(self):
        """Test creating a BookingConflict object."""
        conflict = BookingConflict(self.booking1, self.booking2)
        
        self.assertEqual(conflict.booking1, self.booking1)
        self.assertEqual(conflict.booking2, self.booking2)
        self.assertEqual(conflict.conflict_type, 'overlap')
        
        # Test overlap calculation
        expected_start = max(self.booking1.start_time, self.booking2.start_time)
        expected_end = min(self.booking1.end_time, self.booking2.end_time)
        
        self.assertEqual(conflict.overlap_start, expected_start)
        self.assertEqual(conflict.overlap_end, expected_end)
        self.assertEqual(conflict.overlap_duration, expected_end - expected_start)
    
    def test_conflict_str_representation(self):
        """Test string representation of conflicts."""
        conflict = BookingConflict(self.booking1, self.booking2)
        str_repr = str(conflict)
        
        self.assertIn("First Booking", str_repr)
        self.assertIn("Second Booking", str_repr)
        self.assertIn("Conflict between", str_repr)
    
    def test_conflict_to_dict(self):
        """Test converting conflict to dictionary."""
        conflict = BookingConflict(self.booking1, self.booking2, 'maintenance')
        conflict_dict = conflict.to_dict()
        
        self.assertIn('booking1', conflict_dict)
        self.assertIn('booking2', conflict_dict)
        self.assertIn('conflict_type', conflict_dict)
        self.assertIn('overlap_start', conflict_dict)
        self.assertIn('overlap_end', conflict_dict)
        
        self.assertEqual(conflict_dict['conflict_type'], 'maintenance')
        self.assertEqual(conflict_dict['booking1']['title'], "First Booking")
        self.assertEqual(conflict_dict['booking2']['title'], "Second Booking")


class TestComplexOverlapScenarios(TestCase):
    """Test complex booking overlap scenarios."""
    
    def setUp(self):
        self.resource = ResourceFactory(capacity=1)
        self.user = UserFactory()
        self.base_time = timezone.now() + timedelta(hours=1)
    
    def test_partial_overlap_start(self):
        """Test partial overlap at the start of existing booking."""
        existing = BookingFactory(
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=2),
            end_time=self.base_time + timedelta(hours=4)
        )
        
        # New booking overlaps at start
        new_start = self.base_time + timedelta(hours=1)
        new_end = self.base_time + timedelta(hours=3)
        
        conflicts = get_conflicts_for_booking(
            self.resource, new_start, new_end, exclude_booking=None
        )
        
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].booking1, existing)
    
    def test_partial_overlap_end(self):
        """Test partial overlap at the end of existing booking."""
        existing = BookingFactory(
            resource=self.resource,
            start_time=self.base_time,
            end_time=self.base_time + timedelta(hours=2)
        )
        
        # New booking overlaps at end
        new_start = self.base_time + timedelta(hours=1)
        new_end = self.base_time + timedelta(hours=3)
        
        conflicts = get_conflicts_for_booking(
            self.resource, new_start, new_end, exclude_booking=None
        )
        
        self.assertEqual(len(conflicts), 1)
    
    def test_complete_containment(self):
        """Test when new booking completely contains existing booking."""
        existing = BookingFactory(
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=2),
            end_time=self.base_time + timedelta(hours=3)
        )
        
        # New booking contains existing
        new_start = self.base_time + timedelta(hours=1)
        new_end = self.base_time + timedelta(hours=4)
        
        conflicts = get_conflicts_for_booking(
            self.resource, new_start, new_end, exclude_booking=None
        )
        
        self.assertEqual(len(conflicts), 1)
    
    def test_multiple_overlapping_bookings(self):
        """Test conflicts with multiple existing bookings."""
        booking1 = BookingFactory(
            resource=self.resource,
            start_time=self.base_time,
            end_time=self.base_time + timedelta(hours=2)
        )
        
        booking2 = BookingFactory(
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=1),
            end_time=self.base_time + timedelta(hours=3)
        )
        
        # New booking overlaps with both
        new_start = self.base_time + timedelta(minutes=30)
        new_end = self.base_time + timedelta(hours=2, minutes=30)
        
        conflicts = get_conflicts_for_booking(
            self.resource, new_start, new_end, exclude_booking=None
        )
        
        self.assertEqual(len(conflicts), 2)
    
    def test_adjacent_bookings_no_conflict(self):
        """Test that adjacent bookings don't conflict."""
        existing = BookingFactory(
            resource=self.resource,
            start_time=self.base_time,
            end_time=self.base_time + timedelta(hours=2)
        )
        
        # New booking starts exactly when existing ends
        new_start = self.base_time + timedelta(hours=2)
        new_end = self.base_time + timedelta(hours=4)
        
        conflicts = get_conflicts_for_booking(
            self.resource, new_start, new_end, exclude_booking=None
        )
        
        self.assertEqual(len(conflicts), 0)
    
    def test_cancelled_bookings_ignored(self):
        """Test that cancelled bookings are ignored in conflict detection."""
        cancelled_booking = BookingFactory(
            resource=self.resource,
            start_time=self.base_time,
            end_time=self.base_time + timedelta(hours=2),
            status='cancelled'
        )
        
        # New booking overlaps with cancelled booking
        new_start = self.base_time + timedelta(hours=1)
        new_end = self.base_time + timedelta(hours=3)
        
        conflicts = get_conflicts_for_booking(
            self.resource, new_start, new_end, exclude_booking=None
        )
        
        self.assertEqual(len(conflicts), 0)


class TestCapacityBasedConflicts(TestCase):
    """Test conflict detection for resources with capacity > 1."""
    
    def setUp(self):
        self.multi_resource = ResourceFactory(capacity=3)
        self.user = UserFactory()
        self.base_time = timezone.now() + timedelta(hours=1)
    
    def test_within_capacity_no_conflict(self):
        """Test that bookings within capacity don't conflict."""
        # Create 2 bookings (within capacity of 3)
        BookingFactory(
            resource=self.multi_resource,
            start_time=self.base_time,
            end_time=self.base_time + timedelta(hours=2)
        )
        
        BookingFactory(
            resource=self.multi_resource,
            start_time=self.base_time + timedelta(minutes=30),
            end_time=self.base_time + timedelta(hours=2, minutes=30)
        )
        
        # Third booking should be allowed
        new_start = self.base_time + timedelta(hours=1)
        new_end = self.base_time + timedelta(hours=3)
        
        conflicts = get_conflicts_for_booking(
            self.multi_resource, new_start, new_end, exclude_booking=None
        )
        
        # Should have no conflicts as we're within capacity
        self.assertEqual(len(conflicts), 0)
    
    def test_exceeding_capacity_creates_conflict(self):
        """Test that exceeding capacity creates conflicts."""
        # Create 3 bookings (at capacity)
        for i in range(3):
            BookingFactory(
                resource=self.multi_resource,
                start_time=self.base_time + timedelta(minutes=i*15),
                end_time=self.base_time + timedelta(hours=2, minutes=i*15)
            )
        
        # Fourth booking should conflict
        new_start = self.base_time + timedelta(hours=1)
        new_end = self.base_time + timedelta(hours=3)
        
        conflicts = get_conflicts_for_booking(
            self.multi_resource, new_start, new_end, exclude_booking=None
        )
        
        # Should have conflicts due to capacity exceeded
        self.assertGreater(len(conflicts), 0)


class TestMaintenanceConflicts(TestCase):
    """Test conflicts with maintenance windows."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.user = UserFactory()
        self.base_time = timezone.now() + timedelta(hours=1)
    
    def test_booking_conflicts_with_maintenance(self):
        """Test that bookings conflict with maintenance windows."""
        maintenance = Maintenance.objects.create(
            resource=self.resource,
            title="Routine Maintenance",
            start_time=self.base_time,
            end_time=self.base_time + timedelta(hours=2),
            maintenance_type="scheduled",
            created_by=self.user
        )
        
        # Booking overlaps with maintenance
        conflicts = detect_maintenance_conflicts(
            self.resource,
            self.base_time + timedelta(hours=1),
            self.base_time + timedelta(hours=3)
        )
        
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0], maintenance)
    
    def test_emergency_maintenance_priority(self):
        """Test that emergency maintenance has higher priority."""
        emergency_maintenance = Maintenance.objects.create(
            resource=self.resource,
            title="Emergency Maintenance",
            start_time=self.base_time,
            end_time=self.base_time + timedelta(hours=4),
            maintenance_type="emergency",
            created_by=self.user
        )
        
        existing_booking = BookingFactory(
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=1),
            end_time=self.base_time + timedelta(hours=3)
        )
        
        conflicts = detect_maintenance_conflicts(
            self.resource,
            existing_booking.start_time,
            existing_booking.end_time
        )
        
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].maintenance_type, "emergency")


class TestRecurringBookingConflicts(TestCase):
    """Test conflicts with recurring bookings."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.user = UserFactory()
        self.base_time = timezone.now() + timedelta(hours=1)
    
    def test_recurring_series_conflicts(self):
        """Test conflicts within recurring booking series."""
        # Create recurring booking series
        parent_booking = BookingFactory(
            resource=self.resource,
            start_time=self.base_time,
            end_time=self.base_time + timedelta(hours=1),
            is_recurring_parent=True
        )
        
        # Create instance of recurring series
        recurring_instance = BookingFactory(
            resource=self.resource,
            start_time=self.base_time + timedelta(days=7),
            end_time=self.base_time + timedelta(days=7, hours=1),
            recurring_parent=parent_booking
        )
        
        # Test conflict with recurring instance
        conflicts = get_conflicts_for_booking(
            self.resource,
            self.base_time + timedelta(days=7, minutes=30),
            self.base_time + timedelta(days=7, hours=1, minutes=30),
            exclude_booking=None
        )
        
        self.assertEqual(len(conflicts), 1)
    
    def test_exclude_booking_from_conflicts(self):
        """Test excluding a booking from conflict detection."""
        existing = BookingFactory(
            resource=self.resource,
            start_time=self.base_time,
            end_time=self.base_time + timedelta(hours=2)
        )
        
        # Should find conflict
        conflicts = get_conflicts_for_booking(
            self.resource,
            self.base_time + timedelta(hours=1),
            self.base_time + timedelta(hours=3),
            exclude_booking=None
        )
        self.assertEqual(len(conflicts), 1)
        
        # Should not find conflict when excluding the booking
        conflicts = get_conflicts_for_booking(
            self.resource,
            self.base_time + timedelta(hours=1),
            self.base_time + timedelta(hours=3),
            exclude_booking=existing
        )
        self.assertEqual(len(conflicts), 0)


class TestConflictDetectorClass(TestCase):
    """Test the ConflictDetector class."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.detector = ConflictDetector()
    
    def test_detector_initialization(self):
        """Test ConflictDetector initialization."""
        self.assertIsInstance(self.detector, ConflictDetector)
    
    def test_detector_with_time_zones(self):
        """Test conflict detection across different time zones."""
        # Create booking in UTC
        utc_time = timezone.now()
        booking1 = BookingFactory(
            resource=self.resource,
            start_time=utc_time,
            end_time=utc_time + timedelta(hours=2)
        )
        
        # Test conflict detection with timezone-aware datetime
        new_start = utc_time + timedelta(hours=1)
        new_end = utc_time + timedelta(hours=3)
        
        conflicts = self.detector.detect_conflicts(
            self.resource, new_start, new_end
        )
        
        self.assertEqual(len(conflicts), 1)
    
    def test_detector_performance_with_many_bookings(self):
        """Test detector performance with many existing bookings."""
        # Create many non-conflicting bookings
        base_time = timezone.now() + timedelta(hours=1)
        for i in range(50):
            BookingFactory(
                resource=self.resource,
                start_time=base_time + timedelta(days=i),
                end_time=base_time + timedelta(days=i, hours=1)
            )
        
        # Test conflict detection
        test_start = base_time + timedelta(days=25, hours=0.5)
        test_end = base_time + timedelta(days=25, hours=1.5)
        
        conflicts = self.detector.detect_conflicts(
            self.resource, test_start, test_end
        )
        
        self.assertEqual(len(conflicts), 1)


class TestConflictResolver(TestCase):
    """Test conflict resolution strategies."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.user1 = UserFactory()
        self.user2 = UserFactory()
        self.resolver = ConflictResolver()
        
        # Create user profiles with different priorities
        self.user1_profile = UserProfileFactory(
            user=self.user1, 
            role='academic',
            priority_level=2
        )
        self.user2_profile = UserProfileFactory(
            user=self.user2, 
            role='student',
            priority_level=1
        )
    
    def test_priority_based_resolution(self):
        """Test resolving conflicts based on user priority."""
        base_time = timezone.now() + timedelta(hours=1)
        
        existing_booking = BookingFactory(
            resource=self.resource,
            user=self.user2,  # Lower priority user
            start_time=base_time,
            end_time=base_time + timedelta(hours=2)
        )
        
        new_booking = BookingFactory(
            resource=self.resource,
            user=self.user1,  # Higher priority user
            start_time=base_time + timedelta(hours=1),
            end_time=base_time + timedelta(hours=3)
        )
        
        conflict = BookingConflict(existing_booking, new_booking)
        resolution = self.resolver.resolve_by_priority(conflict)
        
        self.assertIsNotNone(resolution)
        self.assertEqual(resolution['winner'], new_booking)
        self.assertEqual(resolution['action'], 'override')
    
    def test_first_come_first_served_resolution(self):
        """Test resolving conflicts by creation time."""
        base_time = timezone.now() + timedelta(hours=1)
        
        first_booking = BookingFactory(
            resource=self.resource,
            start_time=base_time,
            end_time=base_time + timedelta(hours=2)
        )
        
        # Wait a moment then create second booking
        import time
        time.sleep(0.01)
        
        second_booking = BookingFactory(
            resource=self.resource,
            start_time=base_time + timedelta(hours=1),
            end_time=base_time + timedelta(hours=3)
        )
        
        conflict = BookingConflict(first_booking, second_booking)
        resolution = self.resolver.resolve_by_timestamp(conflict)
        
        self.assertEqual(resolution['winner'], first_booking)
        self.assertEqual(resolution['action'], 'reject_new')


class TestEdgeCasesAndValidation(TestCase):
    """Test edge cases and validation in conflict detection."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.user = UserFactory()
    
    def test_same_start_and_end_time(self):
        """Test booking with same start and end time."""
        base_time = timezone.now() + timedelta(hours=1)
        
        # Create zero-duration booking
        zero_booking = BookingFactory(
            resource=self.resource,
            start_time=base_time,
            end_time=base_time  # Same as start
        )
        
        conflicts = get_conflicts_for_booking(
            self.resource,
            base_time,
            base_time + timedelta(hours=1),
            exclude_booking=None
        )
        
        # Zero-duration bookings should not conflict
        self.assertEqual(len(conflicts), 0)
    
    def test_negative_duration_booking(self):
        """Test handling of invalid bookings with end before start."""
        base_time = timezone.now() + timedelta(hours=1)
        
        try:
            invalid_booking = Booking(
                resource=self.resource,
                user=self.user,
                title="Invalid Booking",
                start_time=base_time + timedelta(hours=1),
                end_time=base_time  # End before start
            )
            invalid_booking.full_clean()
            self.fail("Should have raised validation error")
        except ValidationError:
            pass  # Expected
    
    def test_far_future_bookings(self):
        """Test conflict detection with bookings far in the future."""
        far_future = timezone.now() + timedelta(days=365)
        
        future_booking = BookingFactory(
            resource=self.resource,
            start_time=far_future,
            end_time=far_future + timedelta(hours=2)
        )
        
        conflicts = get_conflicts_for_booking(
            self.resource,
            far_future + timedelta(hours=1),
            far_future + timedelta(hours=3),
            exclude_booking=None
        )
        
        self.assertEqual(len(conflicts), 1)
    
    def test_null_resource_handling(self):
        """Test handling of null resource in conflict detection."""
        try:
            conflicts = get_conflicts_for_booking(
                None,  # Null resource
                timezone.now(),
                timezone.now() + timedelta(hours=1),
                exclude_booking=None
            )
            self.fail("Should have raised an error for null resource")
        except (AttributeError, ValueError):
            pass  # Expected


class TestConflictNotifications(TestCase):
    """Test conflict notification functionality."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.user1 = UserFactory()
        self.user2 = UserFactory()
    
    @patch('booking.conflicts.send_conflict_notification')
    def test_conflict_notification_sent(self, mock_send):
        """Test that conflict notifications are sent."""
        base_time = timezone.now() + timedelta(hours=1)
        
        existing = BookingFactory(
            resource=self.resource,
            user=self.user1,
            start_time=base_time,
            end_time=base_time + timedelta(hours=2)
        )
        
        new_booking = BookingFactory(
            resource=self.resource,
            user=self.user2,
            start_time=base_time + timedelta(hours=1),
            end_time=base_time + timedelta(hours=3)
        )
        
        conflict = BookingConflict(existing, new_booking)
        
        # Simulate conflict notification
        from booking.conflicts import notify_conflict_stakeholders
        notify_conflict_stakeholders(conflict)
        
        # Check if notification was attempted
        mock_send.assert_called()
    
    def test_conflict_logging(self):
        """Test that conflicts are properly logged."""
        base_time = timezone.now() + timedelta(hours=1)
        
        existing = BookingFactory(
            resource=self.resource,
            start_time=base_time,
            end_time=base_time + timedelta(hours=2)
        )
        
        conflicts = get_conflicts_for_booking(
            self.resource,
            base_time + timedelta(hours=1),
            base_time + timedelta(hours=3),
            exclude_booking=None
        )
        
        self.assertEqual(len(conflicts), 1)
        
        # Test that conflict can be converted to string for logging
        conflict_str = str(conflicts[0])
        self.assertIsInstance(conflict_str, str)
        self.assertIn("Conflict", conflict_str)